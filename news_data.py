import re
import logging
from collections import Counter
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from config import TradingConfig, CONFIG, ALPHA_VANTAGE_KEY
from utils import safe_float, parse_time_published, build_session

logger = logging.getLogger(__name__)
SESSION = build_session()

_EMPTY_RESULT: Dict[str, Any] = {
    "events": [],
    "aggregate_score": 0.0,
    "sentiment_bias": "NEUTRAL",
    "top_event_types": [],
    "key_catalysts": [],
}


# ------------------------------------------------------------
# 직접 관련 판별
# ------------------------------------------------------------
def get_direct_relevance_reason(ticker: str, title: str, summary: str = "") -> Optional[str]:
    ticker_l = ticker.lower()
    title_l = (title or "").lower()
    summary_l = (summary or "").lower()

    negative_patterns = [rf"like {ticker_l}", rf"the {ticker_l} of", rf"{ticker_l} of "]
    if any(re.search(pattern, title_l) for pattern in negative_patterns):
        return None

    if re.search(rf"\b{ticker_l}\b", title_l):
        return f"제목에 {ticker}가 직접 포함되어 있어 종목 관련성이 매우 높습니다."

    if re.search(rf"\b{ticker_l}\b", summary_l):
        return f"요약에서 {ticker} 관련성이 확인됩니다."

    return None


# ------------------------------------------------------------
# 이벤트 분류 (패턴 미리 컴파일)
# ------------------------------------------------------------
_EVENT_RULES_RAW = [
    (
        "AI",
        [
            r"\bai\b", r"artificial intelligence", r"autopilot", r"fsd",
            r"full self[- ]driving", r"robotaxi", r"robot", r"humanoid",
            r"dojo", r"self-driving",
        ],
    ),
    (
        "PRODUCT",
        [
            r"launch", r"release", r"unveil", r"rollout", r"model y",
            r"model 3", r"cybertruck", r"software update", r"feature",
            r"product", r"service",
        ],
    ),
    (
        "EARNINGS",
        [
            r"earnings", r"guidance", r"revenue", r"\beps\b", r"profit",
            r"loss", r"quarter", r"q1", r"q2", r"q3", r"q4",
            r"margin", r"outlook", r"financial results",
        ],
    ),
    (
        "REGULATION",
        [
            r"regulation", r"regulatory", r"approval", r"approved",
            r"lawsuit", r"legal", r"court", r"investigation",
            r"\bsec\b", r"\bnhtsa\b", r"recall", r"compliance",
        ],
    ),
    (
        "RATING",
        [
            r"upgrade", r"downgrade", r"rating", r"analyst", r"price target",
            r"reiterated", r"initiated", r"neutral", r"buy rating", r"sell rating",
        ],
    ),
]

_COMPILED_EVENT_RULES: List[tuple] = [
    (event_type, [re.compile(p) for p in patterns])
    for event_type, patterns in _EVENT_RULES_RAW
]


def classify_event(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    for event_type, compiled_patterns in _COMPILED_EVENT_RULES:
        for pattern in compiled_patterns:
            if pattern.search(text):
                return event_type
    return "GENERAL"


# ------------------------------------------------------------
# why_it_matters 생성
# ------------------------------------------------------------
def build_why_it_matters(event_type: str, title: str, summary: str) -> str:
    title_l = (title or "").lower()
    summary_l = (summary or "").lower()

    if event_type == "AI":
        if any(k in title_l or k in summary_l for k in ["robotaxi", "autopilot", "fsd", "self-driving", "robot", "humanoid"]):
            return "자율주행·로봇·AI 플랫폼 기대치가 장기 밸류에이션과 성장 서사를 직접 바꿀 수 있습니다."
        return "AI 관련 기대는 소프트웨어·플랫폼 가치와 미래 성장 프리미엄에 영향을 줍니다."

    if event_type == "PRODUCT":
        if any(k in title_l or k in summary_l for k in ["cybertruck", "model y", "model 3", "software update", "launch", "release"]):
            return "신차·기능·소프트웨어 출시가 인도량, 제품 믹스, 전환율에 직접 영향을 줄 수 있습니다."
        return "제품 관련 뉴스는 출하 속도, 기능 채택, 수요 기대를 흔들 수 있어 단기 주가에 민감합니다."

    if event_type == "EARNINGS":
        if any(k in title_l or k in summary_l for k in ["guidance", "outlook", "margin", "revenue", "eps", "profit", "loss"]):
            return "실적·가이던스·마진 변화는 밸류에이션 재평가에 가장 직접적인 재료입니다."
        return "실적 뉴스는 분기 실적 기대와 다음 분기 전망을 바꾸므로 주가 반응이 크게 나타날 수 있습니다."

    if event_type == "REGULATION":
        if any(k in title_l or k in summary_l for k in ["sec", "nhtsa", "recall", "lawsuit", "approval", "investigation", "court"]):
            return "규제·소송·리콜 이슈는 생산, 출하, 승인 일정과 법적 비용을 바꿀 수 있습니다."
        return "규제 뉴스는 운영 리스크와 일정 지연 가능성을 키우거나 줄이는 변수로 작용합니다."

    if event_type == "RATING":
        if any(k in title_l or k in summary_l for k in ["price target", "upgrade", "downgrade", "analyst", "rating"]):
            return "애널리스트 등급·목표가 변경은 단기 수급과 시장 기대치를 빠르게 재조정합니다."
        return "레이팅 변화는 기관의 시각 변화로 해석되기 쉬워 단기 모멘텀에 영향을 줄 수 있습니다."

    return "시장 심리와 종목 해석에 참고할 수 있지만, 직접적 영향은 상대적으로 제한적일 수 있습니다."


# ------------------------------------------------------------
# key_catalysts 구성
# ------------------------------------------------------------
def build_key_catalysts(events: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}

    for event in events:
        event_type = event.get("event_type", "GENERAL")
        if event_type == "GENERAL":
            continue

        bucket = buckets.setdefault(
            event_type,
            {"event_type": event_type, "count": 0, "net_weighted_score": 0.0, "examples": []},
        )

        bucket["count"] += 1
        bucket["net_weighted_score"] += float(event.get("weighted_score", 0.0))

        title = event.get("title", "")
        summary = event.get("summary", "")
        reason = event.get("direct_relevance_reason")

        if len(bucket["examples"]) < 2 and reason:
            bucket["examples"].append({
                "title": title,
                "why_it_matters": build_why_it_matters(event_type, title, summary),
            })

    ranked = sorted(
        buckets.values(),
        key=lambda x: (abs(x["net_weighted_score"]), x["count"]),
        reverse=True,
    )

    return [
        {
            "event_type": item["event_type"],
            "count": int(item["count"]),
            "net_weighted_score": round(float(item["net_weighted_score"]), 4),
            "examples": item["examples"],
        }
        for item in ranked[:top_n]
    ]


# ------------------------------------------------------------
# 뉴스 수집
# ------------------------------------------------------------
def _parse_feed_item(item: Dict[str, Any], ticker: str, now: datetime) -> Optional[Dict[str, Any]]:
    title = item.get("title", "")
    summary = item.get("summary", "")
    published_at = parse_time_published(item.get("time_published"))

    matching = next(
        (x for x in item.get("ticker_sentiment", []) if x.get("ticker") == ticker),
        None,
    )
    if not matching:
        return None

    score = safe_float(matching.get("ticker_sentiment_score"))
    if score is None:
        return None

    relevance = safe_float(matching.get("relevance_score")) or 0.0

    age_hours = None
    recency_weight = 1.0
    if published_at:
        age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
        recency_weight = max(0.25, 1.0 - (age_hours / 72.0))

    direct_reason = get_direct_relevance_reason(ticker, title, summary)

    return {
        "title": title,
        "summary": summary[:280],
        "event_type": classify_event(title, summary),
        "sentiment_label": matching.get("ticker_sentiment_label", "neutral"),
        "score": round(score, 4),
        "relevance_score": round(relevance, 4),
        "published_at": published_at.isoformat() if published_at else item.get("time_published") or "unknown",
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "recency_weight": round(recency_weight, 3),
        "weighted_score": round(score * recency_weight * (0.5 + relevance), 4),
        "source": item.get("source", "unknown"),
        "direct_relevance": direct_reason is not None,
        "direct_relevance_reason": direct_reason,
    }


def get_news_events(ticker: str, config: TradingConfig = CONFIG) -> Dict[str, Any]:
    url = (
        "https://www.alphavantage.co/query"
        f"?function=NEWS_SENTIMENT&tickers={ticker}&apikey={ALPHA_VANTAGE_KEY}&limit={config.news_limit}"
    )

    try:
        response = SESSION.get(url, timeout=config.request_timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning("Alpha Vantage API 요청 실패: %s", e)
        return dict(_EMPTY_RESULT)

    # rate limit / API 오류 감지 (Alpha Vantage는 200 OK로 오류 메시지를 반환함)
    if not isinstance(data, dict):
        logger.warning("Alpha Vantage 응답 형식 오류")
        return dict(_EMPTY_RESULT)

    api_message = data.get("Information") or data.get("Note")
    if api_message:
        logger.warning("Alpha Vantage API 제한: %s", api_message)
        return dict(_EMPTY_RESULT)

    feed = data.get("feed", [])
    now = datetime.now(timezone.utc)

    events = [
        parsed for item in feed
        if (parsed := _parse_feed_item(item, ticker, now)) is not None
    ]

    if not events:
        return dict(_EMPTY_RESULT)

    scores = [e["weighted_score"] for e in events]
    aggregate_score = sum(scores) / len(scores)

    if aggregate_score >= 0.1:
        sentiment_bias = "BULLISH"
    elif aggregate_score <= -0.1:
        sentiment_bias = "BEARISH"
    else:
        sentiment_bias = "NEUTRAL"

    top_event_types = [
        {"event_type": k, "count": v}
        for k, v in Counter(e["event_type"] for e in events).most_common(5)
    ]

    return {
        "events": events,
        "aggregate_score": round(aggregate_score, 4),
        "sentiment_bias": sentiment_bias,
        "top_event_types": top_event_types,
        "key_catalysts": build_key_catalysts(events, top_n=3),
    }
