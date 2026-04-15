from typing import Any, Optional
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, (float, int, np.floating, np.integer)):
            if pd.isna(value):
                return None
            return float(value)
        if hasattr(value, "item"):
            value = value.item()
            if pd.isna(value):
                return None
            return float(value)
        value = float(value)
        if pd.isna(value):
            return None
        return value
    except Exception:
        return None


def normalize_yfinance_df(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    return df


def parse_time_published(value: Optional[str]) -> Optional[datetime]:
    if not value or value == "unknown":
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    try:
        return numerator / denominator
    except Exception:
        return None


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session