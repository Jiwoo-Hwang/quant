from typing import Any, Dict, Optional
import pandas as pd
import numpy as np
import yfinance as yf

from config import TradingConfig, CONFIG
from utils import safe_float, normalize_yfinance_df, safe_ratio


def get_market_data(ticker: str, config: TradingConfig = CONFIG) -> Optional[Dict[str, Any]]:
    try:
        df = yf.download(
            ticker,
            period=config.yf_period,
            interval=config.yf_interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception:
        return None

    if df is None or df.empty:
        return None

    df = normalize_yfinance_df(df.copy())

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    if any(col not in df.columns for col in required_cols):
        return None

    df = df.dropna(subset=required_cols).copy()
    if len(df) < 70:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    df["MA20"] = close.rolling(20).mean()
    df["MA60"] = close.rolling(60).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()

    latest = df.iloc[-1]
    ref_idx = -5 if len(df) >= 5 else 0

    current_price = safe_float(latest["Close"])
    ma20 = safe_float(latest["MA20"])
    ma60 = safe_float(latest["MA60"])
    rsi = safe_float(latest["RSI"])
    atr = safe_float(latest["ATR"])

    if any(v is None for v in [current_price, ma20, ma60, rsi, atr]):
        return None

    recent_10_high = safe_float(high.tail(10).max())
    recent_10_low = safe_float(low.tail(10).min())
    recent_20_high = safe_float(high.tail(20).max())
    recent_20_low = safe_float(low.tail(20).min())
    recent_60_high = safe_float(high.tail(60).max())
    recent_60_low = safe_float(low.tail(60).min())

    volume_today = safe_float(volume.iloc[-1])
    volume_avg_20 = safe_float(volume.tail(20).mean())
    volume_ratio = safe_ratio(volume_today, volume_avg_20)

    ma20_slope = safe_float(df["MA20"].iloc[-1] - df["MA20"].iloc[ref_idx]) if len(df) >= 5 else None
    ma60_slope = safe_float(df["MA60"].iloc[-1] - df["MA60"].iloc[ref_idx]) if len(df) >= 5 else None

    distance_to_ma20_pct = safe_ratio(current_price - ma20, ma20) * 100.0 if ma20 else 0.0
    distance_to_ma60_pct = safe_ratio(current_price - ma60, ma60) * 100.0 if ma60 else 0.0

    return {
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "rsi": round(rsi, 2),
        "atr": round(atr, 2),
        "recent_10_high": round(recent_10_high, 2) if recent_10_high is not None else None,
        "recent_10_low": round(recent_10_low, 2) if recent_10_low is not None else None,
        "recent_20_high": round(recent_20_high, 2) if recent_20_high is not None else None,
        "recent_20_low": round(recent_20_low, 2) if recent_20_low is not None else None,
        "recent_60_high": round(recent_60_high, 2) if recent_60_high is not None else None,
        "recent_60_low": round(recent_60_low, 2) if recent_60_low is not None else None,
        "volume_today": round(volume_today, 0) if volume_today is not None else None,
        "volume_avg_20": round(volume_avg_20, 0) if volume_avg_20 is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "ma20_slope": round(ma20_slope, 2) if ma20_slope is not None else None,
        "ma60_slope": round(ma60_slope, 2) if ma60_slope is not None else None,
        "distance_to_ma20_pct": round(distance_to_ma20_pct, 2),
        "distance_to_ma60_pct": round(distance_to_ma60_pct, 2),
        "last_close_date": str(df.index[-1].date()),
        "bars": int(len(df)),
    }