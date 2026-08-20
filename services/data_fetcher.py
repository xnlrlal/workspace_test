"""
주가 데이터 수집 모듈
- 국내 종목(6자리 숫자 코드, 예: 005930)은 FinanceDataReader(KRX)로 조회
- 해외 종목(티커, 예: AAPL)은 yfinance(Yahoo Finance)로 조회
"""
import re
from datetime import datetime, timedelta

import pandas as pd

_KR_TICKER_RE = re.compile(r"^\d{6}$")


def is_kr_ticker(ticker: str) -> bool:
    """국내 종목코드(6자리 숫자) 여부 판별"""
    return bool(_KR_TICKER_RE.fullmatch(ticker.strip()))


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """FDR / yfinance 컬럼명을 Open/High/Low/Close/Volume 으로 통일"""
    df = df.rename(columns=lambda c: str(c).strip().title())
    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[keep].copy()
    df.index.name = "Date"
    return df


def fetch_history(ticker: str, period_days: int = 365):
    """
    종목의 과거 OHLCV 데이터를 조회한다.

    Returns:
        (DataFrame[Open, High, Low, Close, Volume] indexed by Date, market: 'KR'|'US', name: str)
    """
    ticker = ticker.strip()
    start = datetime.today() - timedelta(days=period_days)

    if is_kr_ticker(ticker):
        import FinanceDataReader as fdr

        df = fdr.DataReader(ticker, start=start)
        if df is None or df.empty:
            return None, "KR", ticker
        df = _normalize_columns(df)

        name = ticker
        try:
            listing = fdr.StockListing("KRX")
            match = listing[listing["Code"] == ticker]
            if not match.empty:
                name = match.iloc[0]["Name"]
        except Exception:
            pass  # 종목명 조회 실패해도 코드로 진행

        return df.dropna(subset=["Close"]), "KR", name

    else:
        import yfinance as yf

        yt = yf.Ticker(ticker)
        df = yt.history(period=f"{period_days}d", auto_adjust=True)
        if df is None or df.empty:
            return None, "US", ticker
        df = _normalize_columns(df)
        df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index

        name = ticker
        try:
            info = yt.get_info()
            name = info.get("shortName") or info.get("longName") or ticker
        except Exception:
            pass

        return df.dropna(subset=["Close"]), "US", name
