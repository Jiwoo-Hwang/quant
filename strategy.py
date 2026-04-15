from typing import Any, Dict, List, Optional

from config import TradingConfig, CONFIG
from utils import clamp
from llm_commentary import generate_llm_commentary


# ============================================================
# 추세 / 트리거
# ============================================================
def compute_trend_score(data: Dict[str, Any]) -> float:
    price = data["current_price"]
    ma20 = data["ma20"]
    ma60 = data["ma60"]
    ma20_slope = data.get("ma20_slope") or 0.0
    ma60_slope = data.get("ma60_slope") or 0.0
    distance_to_ma20_pct = data.get("distance_to_ma20_pct") or 0.0
    distance_to_ma60_pct = data.get("distance_to_ma60_pct") or 0.0

    score = 0.0
    score += 1.0 if price > ma20 else -1.0
    score += 1.0 if price > ma60 else -1.0
    score += 1.0 if ma20 > ma60 else -1.0

    if ma20_slope > 0:
        score += 0.5
    elif ma20_slope < 0:
        score -= 0.5

    if ma60_slope > 0:
        score += 0.5
    elif ma60_slope < 0:
        score -= 0.5

    if abs(distance_to_ma20_pct) < 2.0:
        score += 0.25
    if abs(distance_to_ma60_pct) < 4.0:
        score += 0.25

    return round(score, 2)


def trend_state(data: Dict[str, Any], config: TradingConfig = CONFIG) -> str:
    score = compute_trend_score(data)

    if score >= config.bullish_trend_threshold:
        return "BULLISH"
    if score <= config.bearish_trend_threshold:
        return "BEARISH"
    if score >= config.mixed_bullish_threshold:
        return "MIXED_BULLISH"
    if score <= config.mixed_bearish_threshold:
        return "MIXED_BEARISH"
    return "NEUTRAL"


def detect_entry_trigger(data: Dict[str, Any]) -> str:
    price = data["current_price"]
    ma20 = data["ma20"]
    recent_20_high = data.get("recent_20_high")
    recent_20_low = data.get("recent_20_low")

    if recent_20_high is not None and price >= recent_20_high * 0.995:
        return "BREAKOUT_UP"
    if recent_20_low is not None and price <= recent_20_low * 1.005:
        return "BREAKDOWN_DOWN"
    if ma20 and abs(price - ma20) / ma20 <= 0.01:
        return "PULLBACK_MA20"
    if price > ma20:
        return "ABOVE_MA20"
    if price < ma20:
        return "BELOW_MA20"
    return "NONE"


# ============================================================
# 스윙 세팅
# ============================================================
def build_setup(data: Dict[str, Any], side: str, trigger: Optional[str] = None) -> Dict[str, Any]:
    price = data["current_price"]
    atr = data["atr"]
    ma20 = data["ma20"]
    recent_20_high = data.get("recent_20_high") or price
    recent_20_low = data.get("recent_20_low") or price
    recent_60_high = data.get("recent_60_high") or price
    recent_60_low = data.get("recent_60_low") or price

    if atr is None or atr <= 0:
        return {
            "side": "NO_TRADE",
            "entry_range": None,
            "target_price": None,
            "stop_loss": None,
            "risk_reward_ratio": None,
            "target_basis": None,
            "stop_basis": None,
        }

    trigger = trigger or detect_entry_trigger(data)

    if side == "BUY":
        if trigger == "BREAKOUT_UP":
            entry_anchor = max(price, recent_20_high)
            target_basis = "breakout_or_atr_cap"
        elif trigger == "PULLBACK_MA20":
            entry_anchor = ma20
            target_basis = "pullback_or_atr_cap"
        else:
            entry_anchor = price
            target_basis = "structure_or_atr_cap"

        stop_candidates = [
            entry_anchor - 1.5 * atr,
            recent_20_low,
            recent_60_low,
            ma20 - 1.0 * atr,
        ]
        stop = round(min(stop_candidates), 2)

        atr_target = entry_anchor + (2.5 * atr)
        structure_target = min(
            [x for x in [recent_20_high, recent_60_high] if x > entry_anchor],
            default=entry_anchor + (2.0 * atr),
        )
        target = round(min(structure_target, atr_target), 2)
        entry_range = f"{round(entry_anchor - 0.25 * atr, 2)} - {round(entry_anchor + 0.25 * atr, 2)}"
        stop_basis = "structure_or_atr_floor"
        rr = abs(target - entry_anchor) / max(abs(entry_anchor - stop), 0.01)

    elif side == "SELL":
        if trigger == "BREAKDOWN_DOWN":
            entry_anchor = min(price, recent_20_low)
            target_basis = "breakdown_or_atr_floor"
        elif trigger == "PULLBACK_MA20":
            entry_anchor = ma20
            target_basis = "pullback_or_atr_floor"
        else:
            entry_anchor = price
            target_basis = "structure_or_atr_floor"

        stop_candidates = [
            entry_anchor + 1.5 * atr,
            recent_20_high,
            recent_60_high,
            ma20 + 1.0 * atr,
        ]
        stop = round(max(stop_candidates), 2)

        atr_target = entry_anchor - (2.5 * atr)
        structure_target = max(
            [x for x in [recent_20_low, recent_60_low] if x < entry_anchor],
            default=entry_anchor - (2.0 * atr),
        )
        target = round(max(structure_target, atr_target), 2)
        entry_range = f"{round(entry_anchor - 0.25 * atr, 2)} - {round(entry_anchor + 0.25 * atr, 2)}"
        stop_basis = "structure_or_atr_cap"
        rr = abs(target - entry_anchor) / max(abs(entry_anchor - stop), 0.01)

    else:
        return {
            "side": "NO_TRADE",
            "entry_range": None,
            "target_price": None,
            "stop_loss": None,
            "risk_reward_ratio": None,
            "target_basis": None,
            "stop_basis": None,
        }

    return {
        "side": side,
        "entry_range": entry_range,
        "target_price": round(target, 2),
        "stop_loss": round(stop, 2),
        "risk_reward_ratio": round(rr, 2),
        "target_basis": target_basis,
        "stop_basis": stop_basis,
        "entry_anchor": round(entry_anchor, 2),
        "trigger": trigger,
    }


# ============================================================
# 점수화 / 차단
# ============================================================
def soft_penalty(data: Dict[str, Any], news: Dict[str, Any], config: TradingConfig = CONFIG) -> float:
    penalty = 0.0
    rsi = data["rsi"]
    volume_ratio = data.get("volume_ratio")
    aggregate_score = news.get("aggregate_score", 0.0)

    if config.rsi_neutral_low <= rsi <= config.rsi_neutral_high:
        penalty -= 0.5

    if volume_ratio is None:
        penalty -= 0.25
    elif volume_ratio < 0.8:
        penalty -= 0.5

    if abs(aggregate_score) < 0.05:
        penalty -= 0.25

    return round(penalty, 2)


def make_block_reason(
    component: str,
    code: str,
    message: str,
    severity: str = "hard",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reason = {
        "component": component,
        "code": code,
        "severity": severity,
        "message": message,
    }
    if details:
        reason["details"] = details
    return reason


def hard_block_reasons(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    reasons: List[Dict[str, Any]] = []
    critical_fields = ["current_price", "ma20", "ma60", "rsi", "atr"]

    missing_fields = [k for k in critical_fields if data.get(k) is None]
    if missing_fields:
        reasons.append(
            make_block_reason(
                component="technical",
                code="MISSING_FIELDS",
                message="핵심 기술 지표가 부족함",
                severity="hard",
                details={"missing_fields": missing_fields},
            )
        )

    if data.get("atr") is not None and data["atr"] <= 0:
        reasons.append(
            make_block_reason(
                component="volatility",
                code="INVALID_ATR",
                message="ATR이 유효하지 않음",
                severity="hard",
                details={"atr": data.get("atr")},
            )
        )

    return reasons


def summarize_block_reasons(block_reasons: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not block_reasons:
        return {
            "total": 0,
            "hard_count": 0,
            "soft_count": 0,
            "by_component": [],
        }

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for reason in block_reasons:
        grouped.setdefault(reason["component"], []).append(reason)

    hard_count = sum(1 for r in block_reasons if r["severity"] == "hard")
    soft_count = sum(1 for r in block_reasons if r["severity"] == "soft")

    by_component = []
    for component, items in grouped.items():
        by_component.append(
            {
                "component": component,
                "count": len(items),
                "codes": [x["code"] for x in items],
                "messages": [x["message"] for x in items],
                "severity": "hard" if any(x["severity"] == "hard" for x in items) else "soft",
            }
        )

    return {
        "total": len(block_reasons),
        "hard_count": hard_count,
        "soft_count": soft_count,
        "by_component": sorted(by_component, key=lambda x: x["count"], reverse=True),
    }


def score_side(data: Dict[str, Any], news: Dict[str, Any], side: str, config: TradingConfig = CONFIG) -> Dict[str, Any]:
    trend_score = compute_trend_score(data)
    trigger = detect_entry_trigger(data)
    setup = build_setup(data, side, trigger)
    rr = setup.get("risk_reward_ratio") or 0.0

    rsi = data["rsi"]
    volume_ratio = data.get("volume_ratio")
    aggregate_score = news.get("aggregate_score", 0.0)
    sentiment_bias = news.get("sentiment_bias", "NEUTRAL")
    penalty = soft_penalty(data, news, config)

    raw_score = 0.0
    reasons: List[str] = []
    block_reasons: List[Dict[str, Any]] = []

    if side == "BUY":
        raw_score += trend_score
        reasons.append(f"trend_score={trend_score}")
    else:
        raw_score -= trend_score
        reasons.append(f"inverse_trend_score={-trend_score}")

    if side == "BUY":
        if trigger in {"BREAKOUT_UP", "PULLBACK_MA20", "ABOVE_MA20"}:
            raw_score += 1.5
            reasons.append(f"entry trigger supports BUY: {trigger}")
        elif trigger == "BREAKDOWN_DOWN":
            raw_score -= 1.0
            reasons.append("trigger warns against BUY: BREAKDOWN_DOWN")
    else:
        if trigger in {"BREAKDOWN_DOWN", "PULLBACK_MA20", "BELOW_MA20"}:
            raw_score += 1.5
            reasons.append(f"entry trigger supports SELL: {trigger}")
        elif trigger == "BREAKOUT_UP":
            raw_score -= 1.0
            reasons.append("trigger warns against SELL: BREAKOUT_UP")

    if side == "BUY":
        if 45 <= rsi <= 65:
            raw_score += 0.75
            reasons.append("RSI is acceptable for BUY")
        elif rsi < 40:
            raw_score -= 0.75
            reasons.append("RSI is too weak for BUY")
        elif rsi > 70:
            raw_score -= 0.5
            reasons.append("RSI is too extended for BUY")
    else:
        if 35 <= rsi <= 55:
            raw_score += 0.75
            reasons.append("RSI is acceptable for SELL")
        elif rsi > 60:
            raw_score -= 0.75
            reasons.append("RSI is too strong for SELL")
        elif rsi < 30:
            raw_score -= 0.5
            reasons.append("RSI is too weak for SELL")

    if volume_ratio is not None:
        if volume_ratio >= 1.2:
            raw_score += 0.75
            reasons.append("volume expansion")
        elif volume_ratio < 0.8:
            raw_score -= 0.5
            reasons.append("volume is soft")
    else:
        reasons.append("volume_ratio unavailable; treated as neutral")

    news_component = clamp(aggregate_score * config.news_weight, -config.news_score_clip, config.news_score_clip)
    if side == "BUY":
        raw_score += news_component
        reasons.append(f"news_component={round(news_component, 2)}")
        if sentiment_bias == "BULLISH":
            reasons.append("news bias supports upside")
        elif sentiment_bias == "BEARISH":
            reasons.append("news bias opposes upside")
    else:
        raw_score -= news_component
        reasons.append(f"news_component={round(-news_component, 2)}")
        if sentiment_bias == "BEARISH":
            reasons.append("news bias supports downside")
        elif sentiment_bias == "BULLISH":
            reasons.append("news bias opposes downside")

    if rr >= config.min_rr:
        raw_score += 1.0
        reasons.append(f"risk-reward >= {config.min_rr}")
    else:
        raw_score -= 1.5
        reasons.append(f"risk-reward below {config.min_rr}")
        block_reasons.append(
            make_block_reason(
                component="risk_reward",
                code="RR_BELOW_MIN",
                message=f"RR below threshold: {round(rr, 2)}",
                severity="hard",
                details={"rr": round(rr, 2), "min_rr": config.min_rr},
            )
        )

    raw_score += penalty
    if penalty < 0:
        reasons.append(f"soft penalty={penalty}")

    if setup.get("stop_loss") is None or setup.get("target_price") is None:
        block_reasons.append(
            make_block_reason(
                component="setup",
                code="INVALID_LEVELS",
                message="setup levels are not valid",
                severity="hard",
            )
        )

    blocked = len(block_reasons) > 0
    final_score = -999.0 if blocked else round(raw_score, 2)

    return {
        "side": side,
        "raw_score": round(raw_score, 2),
        "score": final_score,
        "reasons": reasons,
        "setup": setup,
        "rr": round(rr, 2),
        "trigger": trigger,
        "blocked": blocked,
        "block_reasons": block_reasons,
    }


# ============================================================
# confidence
# ============================================================
def build_confidence(
    best_score: float,
    second_best_score: float,
    chosen_side: str,
    eligible_count: int,
    blocked_count: int,
    config: TradingConfig = CONFIG,
) -> Dict[str, Any]:
    gap = max(0.0, best_score - second_best_score)

    if chosen_side == "NO_TRADE":
        value = 3.0 + max(0.0, 2.0 - best_score) * 1.5 + gap * 0.5 + blocked_count * 0.25
        value = int(clamp(value, 1, 10))

        if value >= 8:
            label = "HIGH_NO_TRADE_CONFIDENCE"
        elif value >= 5:
            label = "MEDIUM_NO_TRADE_CONFIDENCE"
        else:
            label = "LOW_NO_TRADE_CONFIDENCE"

        interpretation = (
            "진입하지 않는 판단의 신뢰도입니다. "
            "점수가 높을수록 현재 구간에서 관망이 더 적절하다는 의미입니다."
        )
    else:
        value = 5.0 + best_score * 0.5 + gap * 0.75
        value = int(clamp(value, 1, 10))

        if value >= 8:
            label = "HIGH_TRADE_CONFIDENCE"
        elif value >= 5:
            label = "MEDIUM_TRADE_CONFIDENCE"
        else:
            label = "LOW_TRADE_CONFIDENCE"

        interpretation = (
            "진입 판단의 신뢰도입니다. "
            "점수가 높을수록 현재 설정이 구조적으로 더 유리하다는 의미입니다."
        )

    return {
        "value": value,
        "label": label,
        "basis": {
            "best_score": round(best_score, 2),
            "second_best_score": round(second_best_score, 2),
            "score_gap": round(gap, 2),
            "eligible_count": eligible_count,
            "blocked_count": blocked_count,
        },
        "interpretation": interpretation,
    }


# ============================================================
# key catalysts 활용용 문장 생성
# ============================================================
def _format_catalyst_example(example: Any) -> str:
    if isinstance(example, dict):
        title = example.get("title", "")
        why = example.get("why_it_matters", "")
        if title and why:
            return f"{title} — {why}"
        return title or why
    return str(example)


def build_catalyst_context(key_catalysts: List[Dict[str, Any]], top_n: int = 3) -> Dict[str, Any]:
    ordered = sorted(
        key_catalysts or [],
        key=lambda x: abs(float(x.get("net_weighted_score", 0.0))),
        reverse=True,
    )
    top = ordered[:top_n]

    positive = [c for c in ordered if float(c.get("net_weighted_score", 0.0)) > 0]
    negative = [c for c in ordered if float(c.get("net_weighted_score", 0.0)) < 0]

    prompt_lines: List[str] = []
    for cat in top:
        examples = cat.get("examples", []) or []
        example_texts = [_format_catalyst_example(ex) for ex in examples[:2] if ex]
        example_block = " / ".join(example_texts) if example_texts else "직접 예시 없음"

        prompt_lines.append(
            f"- {cat.get('event_type')} | count={cat.get('count', 0)} | "
            f"net={float(cat.get('net_weighted_score', 0.0)):+.2f} | {example_block}"
        )

    return {
        "all_catalysts": ordered,
        "top_catalysts": top,
        "positive_catalysts": positive,
        "negative_catalysts": negative,
        "prompt_block": "\n".join(prompt_lines),
    }


def build_case_drafts(
    data: Dict[str, Any],
    trend_state_value: str,
    catalyst_context: Dict[str, Any],
    chosen_side: str,
) -> Dict[str, str]:
    current_price = data["current_price"]
    ma20 = data["ma20"]
    ma60 = data["ma60"]
    rsi = data["rsi"]
    volume_ratio = data.get("volume_ratio")

    positives = catalyst_context.get("positive_catalysts", [])
    negatives = catalyst_context.get("negative_catalysts", [])

    top_positive = positives[0] if positives else None
    top_negative = negatives[0] if negatives else None

    if top_positive:
        pos_title = top_positive.get("event_type", "CATALYST")
        pos_score = float(top_positive.get("net_weighted_score", 0.0))
        pos_example = top_positive.get("examples", [])
        pos_example_text = ""
        if pos_example:
            first_example = pos_example[0]
            if isinstance(first_example, dict):
                pos_example_text = first_example.get("why_it_matters", "")
        bull_core = (
            f"{pos_title} 촉매가 우호적이며(net {pos_score:+.2f}), "
            f"장기 서사 측면에서는 긍정적입니다."
        )
        if pos_example_text:
            bull_core += f" {pos_example_text}"
    else:
        bull_core = "뚜렷한 우호 촉매는 제한적이지만, 중립적 뉴스 흐름이 급락 압력을 완화할 수 있습니다."

    if top_negative:
        neg_title = top_negative.get("event_type", "CATALYST")
        neg_score = float(top_negative.get("net_weighted_score", 0.0))
        neg_example = top_negative.get("examples", [])
        neg_example_text = ""
        if neg_example:
            first_example = neg_example[0]
            if isinstance(first_example, dict):
                neg_example_text = first_example.get("why_it_matters", "")
        bear_core = (
            f"{neg_title} 촉매가 부담이며(net {neg_score:+.2f}), "
            f"단기 주가에는 역풍이 될 수 있습니다."
        )
        if neg_example_text:
            bear_core += f" {neg_example_text}"
    else:
        bear_core = "명확한 악재형 촉매는 제한적이지만, 기술적 추세 약세와 낮은 거래량이 여전히 부담입니다."

    technical_bull_tail = []
    if current_price < ma20:
        technical_bull_tail.append(f"가격이 MA20({ma20}) 아래라서 추세 확인이 더 필요합니다.")
    if rsi < 45:
        technical_bull_tail.append(f"RSI({rsi})가 아직 강하지 않아 반등은 확인이 필요합니다.")
    if volume_ratio is not None and volume_ratio < 1.0:
        technical_bull_tail.append(f"거래량({volume_ratio})이 강하지 않아 추세 전환 신뢰도가 낮습니다.")

    technical_bear_tail = []
    if current_price < ma20:
        technical_bear_tail.append(f"가격이 MA20({ma20}) 아래라 약세 추세가 유지되고 있습니다.")
    if ma20 < ma60:
        technical_bear_tail.append(f"MA20({ma20})이 MA60({ma60}) 아래라 중기 구조도 약세입니다.")
    if volume_ratio is not None and volume_ratio < 1.0:
        technical_bear_tail.append(f"거래량({volume_ratio})이 약해 추세 추종 매매의 힘이 부족합니다.")
    if rsi < 45:
        technical_bear_tail.append(f"RSI({rsi})도 과열이 아니라 하락 여지가 남아 있습니다.")

    bull_case_draft = " ".join([bull_core] + technical_bull_tail[:2])
    bear_case_draft = " ".join([bear_core] + technical_bear_tail[:2])

    if chosen_side == "NO_TRADE":
        bull_case_draft = f"{bull_case_draft} 다만 현재는 진입할 만큼의 구조적 우위가 충분하지 않습니다."
        bear_case_draft = f"{bear_case_draft} 그래서 방향성은 약세지만, 손익비가 기준에 못 미쳐 진입은 보류하는 편이 낫습니다."

    return {
        "bull_case_draft": bull_case_draft,
        "bear_case_draft": bear_case_draft,
    }


def build_side_explanation(assessment: Dict[str, Any]) -> Dict[str, Any]:
    reasons = assessment.get("reasons", [])
    block_reasons = assessment.get("block_reasons", [])

    positives = []
    headwinds = []

    for reason in reasons:
        lower = reason.lower()
        if any(word in lower for word in ["below", "too", "soft", "warns", "invalid", "risk-reward below"]):
            headwinds.append(reason)
        else:
            positives.append(reason)

    stance = "롱" if assessment["side"] == "BUY" else "숏"

    headline_parts = [f"{stance} 후보"]
    if assessment.get("blocked"):
        headline_parts.append("는 현재 진입 불가")
    else:
        headline_parts.append("는 진입 가능")

    if assessment.get("rr") is not None:
        headline_parts.append(f"(RR={assessment['rr']})")

    return {
        "side": assessment["side"],
        "status": "BLOCKED" if assessment.get("blocked") else "ACTIVE",
        "headline": " ".join(headline_parts),
        "raw_score": assessment.get("raw_score"),
        "rr": assessment.get("rr"),
        "trigger": assessment.get("trigger"),
        "supporting_factors": positives[:4],
        "headwinds": headwinds[:5],
        "block_reasons": block_reasons,
    }


def build_why_not_other_side(
    buy_assessment: Dict[str, Any],
    sell_assessment: Dict[str, Any],
    chosen_side: str,
) -> Dict[str, Any]:
    if chosen_side == "BUY":
        summary = (
            f"BUY가 선택되었고 SELL은 탈락했다. "
            f"SELL은 raw_score가 {sell_assessment['raw_score']}였지만 "
            f"block_reasons={len(sell_assessment.get('block_reasons', []))}개로 진입 불가였다."
        )
        selected = buy_assessment
        rejected = sell_assessment
    elif chosen_side == "SELL":
        summary = (
            f"SELL이 선택되었고 BUY는 탈락했다. "
            f"BUY는 raw_score가 {buy_assessment['raw_score']}였지만 "
            f"block_reasons={len(buy_assessment.get('block_reasons', []))}개로 진입 불가였다."
        )
        selected = sell_assessment
        rejected = buy_assessment
    else:
        selected = None
        rejected = None
        better = buy_assessment if buy_assessment["raw_score"] >= sell_assessment["raw_score"] else sell_assessment
        summary = (
            "NO_TRADE가 선택되었다. "
            f"BUY(raw_score={buy_assessment['raw_score']}, RR={buy_assessment['rr']})와 "
            f"SELL(raw_score={sell_assessment['raw_score']}, RR={sell_assessment['rr']}) 모두 "
            "기준을 통과하지 못했다. "
            f"상대적으로는 {better['side']} 쪽이 덜 나빴지만, 여전히 진입 기준에는 못 미쳤다."
        )

    return {
        "summary": summary,
        "chosen_side": chosen_side,
        "selected_side": build_side_explanation(selected) if selected else None,
        "rejected_side": build_side_explanation(rejected) if rejected else None,
        "BUY": build_side_explanation(buy_assessment),
        "SELL": build_side_explanation(sell_assessment),
    }


# ============================================================
# 최종 판단
# ============================================================
def determine_final_decision(data: Dict[str, Any], news: Dict[str, Any], config: TradingConfig = CONFIG) -> Dict[str, Any]:
    state = trend_state(data, config)
    global_block_reasons = hard_block_reasons(data)

    buy_assessment = score_side(data, news, "BUY", config)
    sell_assessment = score_side(data, news, "SELL", config)

    all_assessments = [buy_assessment, sell_assessment]
    eligible_assessments = [a for a in all_assessments if not a["blocked"]]

    chosen_side = "NO_TRADE"
    chosen_assessment = None

    if not global_block_reasons and eligible_assessments:
        best = max(eligible_assessments, key=lambda x: x["raw_score"])
        second_best = max(
            [a for a in eligible_assessments if a["side"] != best["side"]],
            key=lambda x: x["raw_score"],
            default=None,
        )

        best_score = best["raw_score"]
        second_score = second_best["raw_score"] if second_best else -999.0

        if best_score >= config.score_threshold and (best_score - second_score) >= config.score_gap_threshold:
            chosen_side = best["side"]
            chosen_assessment = best

    if chosen_side == "NO_TRADE":
        if eligible_assessments:
            best_score = max(a["raw_score"] for a in eligible_assessments)
            second_score = max(
                [a["raw_score"] for a in eligible_assessments if a["raw_score"] != best_score],
                default=best_score,
            )
        else:
            best_score = max(buy_assessment["raw_score"], sell_assessment["raw_score"])
            second_score = min(buy_assessment["raw_score"], sell_assessment["raw_score"])

        confidence = build_confidence(
            best_score=best_score,
            second_best_score=second_score,
            chosen_side=chosen_side,
            eligible_count=len(eligible_assessments),
            blocked_count=len(all_assessments) - len(eligible_assessments),
            config=config,
        )
    else:
        second_score = max(
            [a["raw_score"] for a in eligible_assessments if a["side"] != chosen_side],
            default=chosen_assessment["raw_score"],
        )
        confidence = build_confidence(
            best_score=chosen_assessment["raw_score"],
            second_best_score=second_score,
            chosen_side=chosen_side,
            eligible_count=len(eligible_assessments),
            blocked_count=len(all_assessments) - len(eligible_assessments),
            config=config,
        )

    catalyst_context = build_catalyst_context(news.get("key_catalysts", []), top_n=3)
    case_drafts = build_case_drafts(data, state, catalyst_context, chosen_side)

    packet = {
        "ticker": config.ticker,
        "trading_style": config.trading_style,
        "trend_state": state,
        "allowed_actions": ["BUY", "SELL", "NO_TRADE"],
        "technical": data,
        "news": {
            "aggregate_score": news.get("aggregate_score"),
            "sentiment_bias": news.get("sentiment_bias"),
            "top_event_types": news.get("top_event_types"),
            "key_catalysts": news.get("key_catalysts", []),
            "events": news.get("events", [])[:8],
        },
        "catalyst_context": catalyst_context,
        "case_drafts": case_drafts,
        "assessments": {
            "BUY": {
                "score": buy_assessment["score"],
                "raw_score": buy_assessment["raw_score"],
                "rr": buy_assessment["rr"],
                "trigger": buy_assessment["trigger"],
                "reasons": buy_assessment["reasons"],
                "blocked": buy_assessment["blocked"],
                "block_reasons": buy_assessment["block_reasons"],
                "setup": buy_assessment["setup"],
            },
            "SELL": {
                "score": sell_assessment["score"],
                "raw_score": sell_assessment["raw_score"],
                "rr": sell_assessment["rr"],
                "trigger": sell_assessment["trigger"],
                "reasons": sell_assessment["reasons"],
                "blocked": sell_assessment["blocked"],
                "block_reasons": sell_assessment["block_reasons"],
                "setup": sell_assessment["setup"],
            },
        },
        "block_reasons": summarize_block_reasons(global_block_reasons),
    }

    commentary = generate_llm_commentary(packet, chosen_side)
    why_not_other_side = build_why_not_other_side(buy_assessment, sell_assessment, chosen_side)

    selected_setup = chosen_assessment["setup"] if chosen_assessment else {
        "side": "NO_TRADE",
        "entry_range": None,
        "target_price": None,
        "stop_loss": None,
        "risk_reward_ratio": None,
        "target_basis": None,
        "stop_basis": None,
    }

    return {
        "setup": {
            "ticker": config.ticker,
            "trading_style": config.trading_style,
            "trend_state": state,
            "allowed_actions": ["BUY", "SELL", "NO_TRADE"],
            "decision": chosen_side,
            "conviction_score": confidence["value"],
            "confidence_label": confidence["label"],
            "decision_source": "RULE_ENGINE_V2",
        },
        "analysis": {
            "technical_summary": (
                f"Price={data['current_price']}, MA20={data['ma20']}, MA60={data['ma60']}, "
                f"RSI={data['rsi']}, ATR={data['atr']}, VolumeRatio={data.get('volume_ratio')}, "
                f"20D High={data.get('recent_20_high')}, 20D Low={data.get('recent_20_low')}"
            ),
            "sentiment_summary": (
                f"NewsBias={news.get('sentiment_bias')}, AggregateScore={news.get('aggregate_score')}, "
                f"TopEventTypes={news.get('top_event_types')}"
            ),
            "confidence": confidence,
            "bull_case": commentary.get("bull_case", case_drafts["bull_case_draft"]),
            "bear_case": commentary.get("bear_case", case_drafts["bear_case_draft"]),
            "block_reasons": summarize_block_reasons(global_block_reasons),
            "decision_rationale": commentary.get("llm_summary", ""),
            "why_not_other_side": why_not_other_side,
            "macro_influence": "None provided for this run",
        },
        "execution_plan": {
            "side": selected_setup.get("side"),
            "entry_range": selected_setup.get("entry_range"),
            "entry_anchor": selected_setup.get("entry_anchor"),
            "trigger": selected_setup.get("trigger"),
            "target_price": selected_setup.get("target_price"),
            "stop_loss": selected_setup.get("stop_loss"),
            "risk_reward_ratio": selected_setup.get("risk_reward_ratio"),
            "target_basis": selected_setup.get("target_basis"),
            "stop_basis": selected_setup.get("stop_basis"),
        },
        "rejected_actions": {
            "BUY": {
                "score": buy_assessment["score"],
                "raw_score": buy_assessment["raw_score"],
                "rr": buy_assessment["rr"],
                "trigger": buy_assessment["trigger"],
                "reasons": buy_assessment["reasons"],
                "blocked": buy_assessment["blocked"],
                "block_reasons": buy_assessment["block_reasons"],
                "status": "SELECTED" if chosen_side == "BUY" else ("BLOCKED" if buy_assessment["blocked"] else "REJECTED"),
            },
            "SELL": {
                "score": sell_assessment["score"],
                "raw_score": sell_assessment["raw_score"],
                "rr": sell_assessment["rr"],
                "trigger": sell_assessment["trigger"],
                "reasons": sell_assessment["reasons"],
                "blocked": sell_assessment["blocked"],
                "block_reasons": sell_assessment["block_reasons"],
                "status": "SELECTED" if chosen_side == "SELL" else ("BLOCKED" if sell_assessment["blocked"] else "REJECTED"),
            },
        },
        "key_catalysts": news.get("key_catalysts", []),
        "news_events": news.get("events", [])[:5],
        "scores": {
            "buy": buy_assessment["raw_score"],
            "sell": sell_assessment["raw_score"],
        },
    }


def determine_final_decision_v2(data: Dict[str, Any], news: Dict[str, Any]) -> Dict[str, Any]:
    return determine_final_decision(data, news, CONFIG)