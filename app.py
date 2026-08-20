"""
주가 과거 데이터 기반 예측 대시보드 - Flask 백엔드
"""
import time

import pandas as pd
from flask import Flask, jsonify, render_template, request

from services.analog import find_analogs
from services.data_fetcher import fetch_history
from services.predictor import compute_indicators, forecast_prices

app = Flask(__name__)

# ARIMA 그리드서치가 비용이 커서(Render 무료 티어에서는 수십 초 단위), 같은
# (종목, 기간) 조합을 짧은 시간 안에 반복 요청하면(새로고침, 모바일 재방문 등)
# 재계산하지 않고 캐시된 응답을 돌려준다. 워커 프로세스 메모리에만 유지되는
# 캐시라 재배포/재시작 시 비워지는 건 감수한다.
_RESPONSE_CACHE = {}
_CACHE_TTL_SEC = 600
_CACHE_MAX_ENTRIES = 30


def _get_cached_response(key):
    entry = _RESPONSE_CACHE.get(key)
    if entry is None:
        return None
    cached_at, payload = entry
    if time.monotonic() - cached_at > _CACHE_TTL_SEC:
        del _RESPONSE_CACHE[key]
        return None
    return payload


def _set_cached_response(key, payload):
    if len(_RESPONSE_CACHE) >= _CACHE_MAX_ENTRIES:
        oldest_key = min(_RESPONSE_CACHE, key=lambda k: _RESPONSE_CACHE[k][0])
        del _RESPONSE_CACHE[oldest_key]
    _RESPONSE_CACHE[key] = (time.monotonic(), payload)


def _col_to_list(df: pd.DataFrame, col: str):
    """NaN을 JSON-safe한 None으로 바꿔서 리스트로 변환 (float64 Series는 None을 다시
    NaN으로 되돌리는 경우가 있어, 명시적으로 파이썬 리스트를 순회하며 변환한다)"""
    return [None if pd.isna(v) else round(float(v), 2) for v in df[col]]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stock/<ticker>")
def api_stock(ticker):
    days = int(request.args.get("days", 365))
    horizon = int(request.args.get("horizon", 30))
    horizon = max(5, min(horizon, 90))  # 5~90일 범위로 제한

    cache_key = (ticker, days, horizon)
    cached = _get_cached_response(cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        df, market, name = fetch_history(ticker, period_days=days)
    except Exception as e:
        return jsonify({"error": f"데이터 조회 중 오류가 발생했습니다: {e}"}), 502

    if df is None or df.empty:
        return jsonify({"error": f'"{ticker}" 종목 데이터를 찾을 수 없습니다.'}), 404

    try:
        df = compute_indicators(df)
    except Exception as e:
        app.logger.exception("지표 계산 실패")
        return jsonify({"error": f"지표 계산 중 오류가 발생했습니다: {e}"}), 500

    try:
        forecast = forecast_prices(df, horizon=horizon)
    except Exception as e:
        app.logger.exception("예측 계산 실패")
        return jsonify({"error": f"예측 계산 중 오류가 발생했습니다: {e}"}), 500

    try:
        analog = find_analogs(df, window=20, forward=horizon)
    except Exception as e:
        app.logger.exception("유사 패턴 분석 실패")
        return jsonify({"error": f"유사 패턴 분석 중 오류가 발생했습니다: {e}"}), 500

    history = {
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "open": _col_to_list(df, "Open"),
        "high": _col_to_list(df, "High"),
        "low": _col_to_list(df, "Low"),
        "close": _col_to_list(df, "Close"),
        "volume": df["Volume"].fillna(0).astype(int).tolist(),
        "sma20": _col_to_list(df, "SMA20"),
        "sma60": _col_to_list(df, "SMA60"),
        "rsi": _col_to_list(df, "RSI"),
        "macd": _col_to_list(df, "MACD"),
        "macd_signal": _col_to_list(df, "MACD_SIGNAL"),
        "bb_upper": _col_to_list(df, "BB_UPPER"),
        "bb_lower": _col_to_list(df, "BB_LOWER"),
    }

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else last_close
    change_pct = round((last_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    payload = {
        "ticker": ticker,
        "name": name,
        "market": market,
        "last_close": round(last_close, 2),
        "change_pct": change_pct,
        "history": history,
        "forecast": forecast,
        "analog": analog,
    }
    _set_cached_response(cache_key, payload)
    return jsonify(payload)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
