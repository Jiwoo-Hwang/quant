import json
import logging
from typing import Dict, Any

from config import get_openai_client

logger = logging.getLogger(__name__)
client = get_openai_client()


def generate_llm_commentary(packet: Dict[str, Any], final_decision: str) -> Dict[str, str]:
    system_prompt = (
        "You are a swing-trading explanation assistant. "
        "You do not decide the trade. "
        "You explain the code-based decision in concise Korean. "
        "Use key catalysts and the draft case statements as the main basis. "
        "Keep bull_case and bear_case each to one or two sentences. "
        "For NO_TRADE, explain why both directions are unattractive despite any positive catalysts."
    )

    catalyst_block = packet.get("catalyst_context", {}).get("prompt_block", "")
    bull_draft = packet.get("case_drafts", {}).get("bull_case_draft", "")
    bear_draft = packet.get("case_drafts", {}).get("bear_case_draft", "")

    user_prompt = f"""
Decision packet:
{json.dumps(packet, ensure_ascii=False, indent=2)}

Key catalyst summary:
{catalyst_block}

Draft bull case:
{bull_draft}

Draft bear case:
{bear_draft}

Final decision:
{final_decision}

Return JSON only:
{{
  "llm_summary": "한 문단 요약",
  "bull_case": "롱 관점 한두 문장",
  "bear_case": "숏 관점 한두 문장",
  "why_not_other_side": "반대 포지션이 왜 탈락했는지",
  "confidence_comment": "confidence를 어떻게 이해해야 하는지"
}}
"""

    fallback = {
        "llm_summary": "LLM commentary unavailable.",
        "bull_case": bull_draft,
        "bear_case": bear_draft,
        "why_not_other_side": "",
        "confidence_comment": "",
    }

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        if not isinstance(parsed, dict):
            return fallback

        return {
            "llm_summary": str(parsed.get("llm_summary", fallback["llm_summary"])),
            "bull_case": str(parsed.get("bull_case", bull_draft)),
            "bear_case": str(parsed.get("bear_case", bear_draft)),
            "why_not_other_side": str(parsed.get("why_not_other_side", "")),
            "confidence_comment": str(parsed.get("confidence_comment", "")),
        }
    except Exception as e:
        logger.exception("LLM commentary 생성 실패: %s", e)
        fallback["llm_summary"] = f"LLM commentary failed: {str(e)}"
        return fallback