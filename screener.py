import time
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from config import CONFIG, TradingConfig
from market_data import get_market_data
from news_data import get_news_events
from strategy import compute_trend_score, detect_entry_trigger, trend_state
from watchlist import ALL_TICKERS, WATCHLIST

_TICKER_TO_SECTOR: Dict[str, str] = {
    ticker: sector
    for sector, tickers in WATCHLIST.items()
    for ticker in tickers
}

_MIN_DAILY_TURNOVER = 50_000_000   # $50M 일평균 거래대금
_MIN_ATR_PCT = 2.0                  # ATR / Price >= 2% (RR 2.0 달성 여건)
_MIN_PRICE = 10.0                   # penny stock 제외
_NEWS_FETCH_DELAY_SEC = 13          # Alpha Vantage 무료 티어: 5 req/min

_TRIGGER_BONUS: Dict[str, float] = {
    "BREAKOUT_UP":    2.0,
    "BREAKDOWN_DOWN": 2.0,
    "PULLBACK_MA20":  1.5,
    "ABOVE_MA20":     0.5,
    "BELOW_MA20":     0.5,
    "NONE":           0.0,
}

_BUY_STATES  = {"BULLISH", "MIXED_BULLISH"}
_SELL_STATES = {"BEARISH", "MIXED_BEARISH"}


# ============================================================
# 필터
# ============================================================
def _passes_filters(data: Dict[str, Any]) -> Tuple[bool, str]:
    price = data.get("current_price")
    atr   = data.get("atr")
    volume_avg_20 = data.get("volume_avg_20")

    if not price or price < _MIN_PRICE:
        return False, f"price too low (${price})"

    atr_pct = (atr / price * 100) if atr and price else 0.0
    if atr_pct < _MIN_ATR_PCT:
        return False, f"ATR% {atr_pct:.1f}% < {_MIN_ATR_PCT}%"

    if volume_avg_20 is not None:
        daily_turnover = volume_avg_20 * price
        if daily_turnover < _MIN_DAILY_TURNOVER:
            return False, f"turnover ${daily_turnover/1e6:.0f}M < $50M"

    return True, "ok"


def _candidate_side(state: str) -> Optional[str]:
    if state in _BUY_STATES:
        return "BUY"
    if state in _SELL_STATES:
        return "SELL"
    return None


def _trigger_aligned(trigger: str, side: str) -> bool:
    if side == "BUY":
        return trigger in {"BREAKOUT_UP", "PULLBACK_MA20", "ABOVE_MA20"}
    if side == "SELL":
        return trigger in {"BREAKDOWN_DOWN", "PULLBACK_MA20", "BELOW_MA20"}
    return False


# ============================================================
# 준비도 점수
# ============================================================
def compute_readiness_score(data: Dict[str, Any], state: str, trigger: str, side: str) -> float:
    base = abs(compute_trend_score(data))

    bonus = _TRIGGER_BONUS.get(trigger, 0.0)
    if not _trigger_aligned(trigger, side):
        bonus = max(0.0, bonus - 1.5)

    price   = data["current_price"]
    atr     = data["atr"]
    atr_pct = (atr / price * 100) if atr and price else 0.0
    atr_bonus = min((atr_pct - _MIN_ATR_PCT) * 0.3, 1.5)

    volume_ratio  = data.get("volume_ratio")
    volume_bonus  = 0.5 if volume_ratio is not None and volume_ratio >= 1.2 else 0.0

    return round(base + bonus + atr_bonus + volume_bonus, 2)


# ============================================================
# 메인 스크리닝
# ============================================================
def screen_watchlist(
    top_n: int = 5,
    fetch_news: bool = True,
    config: TradingConfig = CONFIG,
) -> Dict[str, Any]:
    total = len(ALL_TICKERS)
    passed: List[Dict[str, Any]] = []
    failed_data   = 0
    failed_filter = 0

    print(f"  워치리스트 {total}개 종목 스캔 중...\n")

    for i, ticker in enumerate(ALL_TICKERS, 1):
        print(f"  [{i:>2}/{total}] {ticker:<6}", end=" | ", flush=True)

        data = get_market_data(ticker, config)
        if data is None:
            print("데이터 없음")
            failed_data += 1
            continue

        ok, reason = _passes_filters(data)
        if not ok:
            print(f"필터 탈락: {reason}")
            failed_filter += 1
            continue

        state = trend_state(data, config)
        side  = _candidate_side(state)
        if side is None:
            print("NEUTRAL 추세 → 탈락")
            failed_filter += 1
            continue

        trigger   = detect_entry_trigger(data)
        readiness = compute_readiness_score(data, state, trigger, side)

        price        = data["current_price"]
        atr          = data["atr"]
        atr_pct      = round(atr / price * 100, 2) if atr and price else None
        volume_avg_20 = data.get("volume_avg_20")
        daily_turnover = volume_avg_20 * price if volume_avg_20 else None

        print(f"통과  side={side:<4}  trigger={trigger:<16}  readiness={readiness}")

        passed.append({
            "ticker":           ticker,
            "sector":           _TICKER_TO_SECTOR.get(ticker, "UNKNOWN"),
            "candidate_side":   side,
            "trend_state":      state,
            "trigger":          trigger,
            "readiness_score":  readiness,
            "atr_pct":          atr_pct,
            "daily_turnover_m": round(daily_turnover / 1e6, 1) if daily_turnover else None,
            "volume_ratio":     data.get("volume_ratio"),
            "rsi":              data.get("rsi"),
            "current_price":    price,
            "atr":              atr,
            "news":             None,
        })

    passed.sort(key=lambda x: x["readiness_score"], reverse=True)
    top = passed[:top_n]

    if fetch_news and top:
        print(f"\n  상위 {len(top)}개 종목 뉴스 조회 중 (Alpha Vantage)...\n")
        for idx, candidate in enumerate(top):
            ticker = candidate["ticker"]
            print(f"  뉴스: {ticker}", end=" ... ", flush=True)
            try:
                candidate["news"] = get_news_events(ticker, config)
                bias  = candidate["news"]["sentiment_bias"]
                score = candidate["news"]["aggregate_score"]
                print(f"{bias} (score={score:+.3f})")
            except Exception as e:
                print(f"실패 ({e})")
                candidate["news"] = None
            if idx < len(top) - 1:
                time.sleep(_NEWS_FETCH_DELAY_SEC)

    return {
        "total_scanned":  total,
        "total_passed":   len(passed),
        "failed_data":    failed_data,
        "failed_filter":  failed_filter,
        "top_candidates": top,
        "all_passed":     passed,
    }
