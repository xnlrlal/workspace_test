"""
기술적 지표 계산 + ARIMA 기반 단기 가격 예측
"""
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


def _select_order(series: pd.Series):
    """AIC 기준으로 (p,d,q) 조합 중 가장 적합한 것을 간단히 탐색"""
    best_aic = np.inf
    best_order = (1, 1, 0)
    for p, d, q in product(range(0, 4), range(0, 2), range(0, 3)):
        if p == 0 and q == 0:
            continue
        try:
            fitted = ARIMA(series, order=(p, d, q)).fit()
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

    fitted = ARIMA(log_close, order=order).fit()
    result = fitted.get_forecast(steps=horizon)

    mean_fc = np.exp(result.predicted_mean)
    conf = np.exp(result.conf_int(alpha=0.20))  # 80% 신뢰구간

    last_date = df.index[-1]
    future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=horizon)

    lower_col, upper_col = conf.columns[0], conf.columns[1]

    return {
        "order": list(order),
        "dates": [d.strftime("%Y-%m-%d") for d in future_dates],
        "mean": [round(v, 2) for v in mean_fc.tolist()],
        "lower": [round(v, 2) for v in conf[lower_col].tolist()],
        "upper": [round(v, 2) for v in conf[upper_col].tolist()],
    }
