import os
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. .env 또는 환경변수를 확인하세요.")
if not ALPHA_VANTAGE_KEY:
    raise RuntimeError("ALPHA_VANTAGE_KEY가 설정되지 않았습니다. .env 또는 환경변수를 확인하세요.")


@dataclass(frozen=True)
class TradingConfig:
    ticker: str = "TSLA"
    trading_style: str = "Swing (5-20 days)"
    yf_period: str = "1y"
    yf_interval: str = "1d"
    news_limit: int = 10
    request_timeout: int = 15

    min_rr: float = 2.0
    score_threshold: float = 3.0
    score_gap_threshold: float = 1.0

    rsi_neutral_low: float = 45.0
    rsi_neutral_high: float = 55.0

    news_weight: float = 2.0
    news_score_clip: float = 2.0

    bullish_trend_threshold: float = 3.0
    bearish_trend_threshold: float = -3.0
    mixed_bullish_threshold: float = 1.0
    mixed_bearish_threshold: float = -1.0


CONFIG = TradingConfig()


def get_openai_client() -> OpenAI:
    return OpenAI(api_key=OPENAI_API_KEY)