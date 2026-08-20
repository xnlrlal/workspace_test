"""
기술적 지표 계산 + ARIMA 기반 단기 가격 예측
"""
import time
import warnings
from itertools import product

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings("ignore", module="statsmodels")


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """이동평균 / RSI / MACD / 볼린저밴드 계산"""
    df = df.copy()
    close = df["Close"]

    df["SMA20"] = close.rolling(20).mean()
    df["SMA60"] = close.rolling(60).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    std20 = close.rolling(20).std()
    df["BB_UPPER"] = df["SMA20"] + 2 * std20
    df["BB_LOWER"] = df["SMA20"] - 2 * std20

    return df


_GRID_SEARCH_TIME_BUDGET_SEC = 20  # 그리드서치 전체에 허용하는 최대 시간(벽시계 기준)


def _fit_kwargs():
    # statsmodels가 fit() 내부에서 method_kwargs 딕셔너리를 직접 변형하므로,
    # 호출마다 새 딕셔너리를 만들어야 한다 (공유 객체를 재사용하면 두 번째
    # 호출부터 이전 fit이 채워넣은 키와 충돌해 ValueError가 난다).
    return dict(method_kwargs={"maxiter": 30}, low_memory=True)


def _select_order(series: pd.Series):
    """AIC 기준으로 (p,d,q) 조합 중 가장 적합한 것을 간단히 탐색

    order 후보를 비교하는 단계에서는 정확한 신뢰구간이 필요 없으므로, 반복
    최적화(L-BFGS + 매 반복마다 수치 미분)를 도는 기본 MLE 대신 한 번에 바로
    계수를 추정하는 hannan_rissanen을 쓴다. 로컬 벤치마크 기준 조합당 3배 이상
    빠르면서도 선택되는 order/AIC는 거의 동일함. 이렇게 해도 여전히 예산을
    넘기면(느린 CPU 등) 그 시점까지 찾은 최선의 order로 즉시 중단한다.
    """
    best_aic = np.inf
    best_order = (1, 1, 0)
    deadline = time.monotonic() + _GRID_SEARCH_TIME_BUDGET_SEC
    for p, d, q in product(range(0, 3), range(0, 2), range(0, 3)):
        if p == 0 and q == 0:
            continue
        if time.monotonic() >= deadline:
            break
        try:
            with warnings.catch_warnings():
                # d>0일 때 hannan_rissanen이 차분 사실을 알리는 무해한 경고를 내는데,
                # module="statsmodels" 필터는 stacklevel 때문에 이 경고를 못 잡는다.
                warnings.simplefilter("ignore")
                fitted = ARIMA(series, order=(p, d, q)).fit(method="hannan_rissanen", low_memory=True)
            if fitted.aic < best_aic:
                best_aic = fitted.aic
                best_order = (p, d, q)
        except Exception:
            continue
    return best_order


def forecast_prices(df: pd.DataFrame, horizon: int = 30) -> dict:
    """
    종가 시계열에 ARIMA를 적합시켜 향후 horizon 영업일을 예측한다.
    변동성 안정화를 위해 로그 변환 후 예측하고 다시 지수 변환한다.
    """
    close = df["Close"].astype(float)
    if len(close) < 40:
        raise ValueError("예측을 위해서는 최소 40거래일 이상의 데이터가 필요합니다.")

    log_close = np.log(close)
    order = _select_order(log_close)

    fitted = ARIMA(log_close, order=order).fit(**_fit_kwargs())
    result = fitted.get_forecast(steps=horizon)

    mean_fc = np.exp(result.predicted_mean)
    conf = np.exp(result.conf_int(alpha=0.20))  # 80% 신뢰구간

    last_date = df.index[-1]
    future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=horizon)

    lower_col, upper_col = conf.columns[0], conf.columns[1]

    def _safe_round(values):
        # NaN/inf는 표준 JSON에 없는 값이라 브라우저 JSON.parse가 실패한다
        # (jsonify가 기본적으로 파이썬의 NaN 리터럴을 그대로 직렬화하기 때문).
        return [None if not np.isfinite(v) else round(float(v), 2) for v in values]

    return {
        "order": list(order),
        "dates": [d.strftime("%Y-%m-%d") for d in future_dates],
        "mean": _safe_round(mean_fc.tolist()),
        "lower": _safe_round(conf[lower_col].tolist()),
        "upper": _safe_round(conf[upper_col].tolist()),
    }
