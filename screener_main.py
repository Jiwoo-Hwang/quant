import sys
from datetime import date
from typing import Any, Dict, Optional

from screener import screen_watchlist
from watchlist import ALL_TICKERS


def _fmt_turnover(turnover_m: Optional[float]) -> str:
    if turnover_m is None:
        return "N/A"
    if turnover_m >= 1000:
        return f"${turnover_m / 1000:.1f}B"
    return f"${turnover_m:.0f}M"


def _bar(width: int = 56) -> str:
    return "━" * width


def render_screener_report(result: Dict[str, Any]) -> str:
    lines = []
    today   = date.today().strftime("%Y-%m-%d")
    total   = result["total_scanned"]
    passed  = result["total_passed"]
    top     = result["top_candidates"]

    lines.append(f"\n{'=' * 56}")
    lines.append(f"  종목 스크리닝 결과  |  {today}")
    lines.append(f"  스캔 {total}개  →  통과 {passed}개  →  상위 {len(top)}개 출력")
    lines.append(f"{'=' * 56}")

    if not top:
        lines.append("\n  현재 조건을 통과한 종목이 없습니다.")
        lines.append("  시장 추세가 불명확하거나 변동성이 낮은 구간일 수 있습니다.")
        lines.append(f"{'=' * 56}\n")
        return "\n".join(lines)

    for rank, c in enumerate(top, 1):
        news       = c.get("news")
        news_bias  = news["sentiment_bias"]  if news else "조회 안함"
        news_score = news["aggregate_score"] if news else None
        news_types = (
            ", ".join(x["event_type"] for x in (news.get("top_event_types") or [])[:3])
            if news else "—"
        )

        side_label = "📈 BUY 후보" if c["candidate_side"] == "BUY" else "📉 SELL 후보"

        lines.append(f"\n{_bar()}")
        lines.append(f"  #{rank}  {c['ticker']:<6}  |  {side_label}  |  준비도 {c['readiness_score']}")
        lines.append(_bar())
        lines.append(f"  섹터     : {c['sector']}")
        lines.append(f"  추세     : {c['trend_state']:<15}  트리거: {c['trigger']}")
        lines.append(
            f"  가격     : ${c['current_price']:<8}  RSI: {c['rsi']:<6}  ATR%: {c['atr_pct']}%"
        )
        lines.append(
            f"  거래대금 : {_fmt_turnover(c['daily_turnover_m']):<10}  거래량비: {c['volume_ratio']}"
        )

        if news:
            score_str = f"{news_score:+.3f}" if news_score is not None else "N/A"
            lines.append(f"  뉴스심리 : {news_bias} (score={score_str})  |  {news_types}")
        else:
            lines.append(f"  뉴스심리 : {news_bias}")

        lines.append(f"  → 상세 분석: python main.py {c['ticker']}")

    lines.append(f"\n{'=' * 56}")
    lines.append("  ※ 스크리닝은 1차 필터입니다.")
    lines.append("     반드시 python main.py <TICKER> 로 상세 분석 후 매매 결정하세요.")
    lines.append(f"{'=' * 56}\n")

    return "\n".join(lines)


def main() -> None:
    fetch_news = "--no-news" not in sys.argv
    top_n_arg  = next((int(a) for a in sys.argv[1:] if a.isdigit()), 5)

    print(f"\n🔍 종목 스크리너 시작  (상위 {top_n_arg}개, 뉴스={'ON' if fetch_news else 'OFF'})\n")

    try:
        result = screen_watchlist(top_n=top_n_arg, fetch_news=fetch_news)
        print(render_screener_report(result))
    except Exception as e:
        print(f"\n[ERROR] {e}")


if __name__ == "__main__":
    main()
