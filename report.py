from typing import Any, Dict, List


def _fmt(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    return str(value)


def _fmt_float(value: Any, digits: int = 2, default: str = "-") -> str:
    try:
        if value is None:
            return default
        return f"{float(value):.{digits}f}"
    except Exception:
        return default


def _fmt_catalyst_examples(examples: List[Dict[str, Any]]) -> str:
    if not examples:
        return "  - 예시 없음"

    lines = []
    for ex in examples[:2]:
        title = ex.get("title", "-")
        why = ex.get("why_it_matters", "-")
        lines.append(f"  - {title}\n    ↳ {why}")
    return "\n".join(lines)


def _fmt_block_reasons(block_reasons: Dict[str, Any]) -> str:
    if not block_reasons or block_reasons.get("total", 0) == 0:
        return "  - 없음"

    lines = []
    for item in block_reasons.get("by_component", []):
        component = item.get("component", "-")
        severity = item.get("severity", "-")
        messages = item.get("messages", [])
        lines.append(f"  - [{severity.upper()}] {component}: {', '.join(messages)}")
    return "\n".join(lines) if lines else "  - 없음"


def _fmt_side(side_data: Dict[str, Any]) -> str:
    status = side_data.get("status", "-")
    raw_score = side_data.get("raw_score", "-")
    rr = side_data.get("rr", "-")
    trigger = side_data.get("trigger", "-")
    headline = side_data.get("headline", "-")
    factors = side_data.get("supporting_factors", [])
    headwinds = side_data.get("headwinds", [])

    lines = [
        f"  상태: {status}",
        f"  한줄평: {headline}",
        f"  raw_score: {raw_score}",
        f"  RR: {_fmt_float(rr)}",
        f"  trigger: {trigger}",
        "  지지 요인:",
    ]

    if factors:
        lines.extend([f"    - {x}" for x in factors[:4]])
    else:
        lines.append("    - 없음")

    lines.append("  부담 요인:")
    if headwinds:
        lines.extend([f"    - {x}" for x in headwinds[:4]])
    else:
        lines.append("    - 없음")

    return "\n".join(lines)


def render_final_report(result: Dict[str, Any]) -> str:
    setup = result.get("setup", {})
    analysis = result.get("analysis", {})
    execution = result.get("execution_plan", {})
    rejected = result.get("rejected_actions", {})
    key_catalysts = result.get("key_catalysts", [])
    news_events = result.get("news_events", [])
    scores = result.get("scores", {})
    confidence = analysis.get("confidence", {})
    why_not = analysis.get("why_not_other_side", {})

    ticker = setup.get("ticker", "-")
    decision = setup.get("decision", "-")
    trend_state = setup.get("trend_state", "-")
    label = setup.get("confidence_label", "-")
    conviction = setup.get("conviction_score", "-")

    tech = analysis.get("technical_summary", "-")
    sentiment = analysis.get("sentiment_summary", "-")
    bull_case = analysis.get("bull_case", "-")
    bear_case = analysis.get("bear_case", "-")
    rationale = analysis.get("decision_rationale", "-")

    lines = []
    lines.append("=" * 72)
    lines.append(f"TSLA 스윙매매 리포트")
    lines.append("=" * 72)
    lines.append(f"종목: {ticker}")
    lines.append(f"최종 판단: {decision}")
    lines.append(f"추세 상태: {trend_state}")
    lines.append(f"신뢰도: {conviction} / 10 ({label})")
    lines.append("")

    lines.append("[핵심 요약]")
    lines.append(f"- 기술적 요약: {tech}")
    lines.append(f"- 뉴스 요약: {sentiment}")
    lines.append(f"- 판단 요지: {rationale}")
    lines.append("")

    lines.append("[상방 시나리오]")
    lines.append(f"- {bull_case}")
    lines.append("")

    lines.append("[하방 시나리오]")
    lines.append(f"- {bear_case}")
    lines.append("")

    lines.append("[실행 계획]")
    lines.append(f"- side: {_fmt(execution.get('side'))}")
    lines.append(f"- entry_range: {_fmt(execution.get('entry_range'))}")
    lines.append(f"- entry_anchor: {_fmt(execution.get('entry_anchor'))}")
    lines.append(f"- trigger: {_fmt(execution.get('trigger'))}")
    lines.append(f"- target_price: {_fmt(execution.get('target_price'))}")
    lines.append(f"- stop_loss: {_fmt(execution.get('stop_loss'))}")
    lines.append(f"- risk_reward_ratio: {_fmt(execution.get('risk_reward_ratio'))}")
    lines.append(f"- target_basis: {_fmt(execution.get('target_basis'))}")
    lines.append(f"- stop_basis: {_fmt(execution.get('stop_basis'))}")
    lines.append("")

    lines.append("[왜 다른 선택지가 탈락했나]")
    if why_not:
        lines.append(f"- {why_not.get('summary', '-')}")
        lines.append("")
        lines.append("  BUY:")
        lines.append(_fmt_side(why_not.get("BUY", {})))
        lines.append("")
        lines.append("  SELL:")
        lines.append(_fmt_side(why_not.get("SELL", {})))
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("[차단 사유]")
    lines.append(_fmt_block_reasons(analysis.get("block_reasons", {})))
    lines.append("")

    lines.append("[신뢰도 근거]")
    if confidence:
        basis = confidence.get("basis", {})
        lines.append(f"- value: {confidence.get('value', '-')}")
        lines.append(f"- label: {confidence.get('label', '-')}")
        lines.append(f"- best_score: {_fmt_float(basis.get('best_score'))}")
        lines.append(f"- second_best_score: {_fmt_float(basis.get('second_best_score'))}")
        lines.append(f"- score_gap: {_fmt_float(basis.get('score_gap'))}")
        lines.append(f"- eligible_count: {_fmt(basis.get('eligible_count'))}")
        lines.append(f"- blocked_count: {_fmt(basis.get('blocked_count'))}")
        lines.append(f"- interpretation: {confidence.get('interpretation', '-')}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("[핵심 촉매]")
    if key_catalysts:
        for cat in key_catalysts[:3]:
            event_type = cat.get("event_type", "-")
            count = cat.get("count", "-")
            net = cat.get("net_weighted_score", "-")
            lines.append(f"- {event_type} | count={count} | net={net}")
            lines.append(_fmt_catalyst_examples(cat.get("examples", [])))
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("[주요 뉴스 5개]")
    if news_events:
        for item in news_events[:5]:
            title = item.get("title", "-")
            event_type = item.get("event_type", "-")
            label_ = item.get("sentiment_label", "-")
            score_ = item.get("score", "-")
            direct_reason = item.get("direct_relevance_reason")
            lines.append(f"- [{event_type}] {title}")
            lines.append(f"  sentiment={label_}, score={score_}")
            if direct_reason:
                lines.append(f"  why_direct: {direct_reason}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("[점수]")
    lines.append(f"- BUY: {_fmt(scores.get('buy'))}")
    lines.append(f"- SELL: {_fmt(scores.get('sell'))}")
    lines.append("=" * 72)

    return "\n".join(lines)