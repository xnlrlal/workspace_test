"""
과거 유사 패턴(analog) 탐색
- 최근 `window`거래일 동안의 등락률 곡선과 가장 비슷한 모양이었던 과거 구간들을 찾고,
  그 구간들 이후 `forward`거래일 동안 실제로 얼마나 움직였는지를 통계로 보여준다.
- ARIMA와 달리 모델을 적합시키지 않고, 순수하게 과거 사례를 찾아 참고 통계를 낸다.
"""
import numpy as np
import pandas as pd


def _shape(seg: np.ndarray) -> np.ndarray:
    """구간 시작값 대비 등락률 곡선으로 정규화 (가격 스케일 무관하게 비교 가능)"""
    return seg / seg[0] - 1.0


def find_analogs(df: pd.DataFrame, window: int = 20, forward: int = 30, top_k: int = 8) -> dict:
    close = df["Close"].astype(float).to_numpy()
    n = len(close)

    last_start = n - window - forward
    if last_start < 1:
        return {
            "available": False,
            "reason": "과거 데이터가 부족해 유사 패턴을 찾을 수 없습니다 (조회 기간을 늘려보세요).",
        }

    recent = _shape(close[n - window :])

    candidates = []
    for start in range(0, last_start):
        end = start + window
        seg_shape = _shape(close[start:end])
        diff = float(np.sqrt(np.mean((seg_shape - recent) ** 2)))
        fwd_return = float(close[end - 1 + forward] / close[end - 1] - 1.0)
        candidates.append((diff, start, end, fwd_return))

    candidates.sort(key=lambda c: c[0])
    top = candidates[:top_k]

    dates = df.index
    matches = [
        {
            "start_date": dates[start].strftime("%Y-%m-%d"),
            "end_date": dates[end - 1].strftime("%Y-%m-%d"),
            "pattern_diff_pct": round(diff * 100, 2),
            "forward_return_pct": round(fwd_return * 100, 2),
        }
        for diff, start, end, fwd_return in top
    ]

    fwd_returns = [c[3] for c in top]
    up = sum(1 for r in fwd_returns if r > 0)

    return {
        "available": True,
        "window": window,
        "forward": forward,
        "sample_size": len(top),
        "up_ratio_pct": round(up / len(top) * 100, 1),
        "avg_return_pct": round(float(np.mean(fwd_returns)) * 100, 2),
        "median_return_pct": round(float(np.median(fwd_returns)) * 100, 2),
        "matches": matches,
    }
