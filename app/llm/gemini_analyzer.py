from __future__ import annotations

import json
import logging

from app.config import settings

log = logging.getLogger(__name__)


def analyze_with_gemini(top_scores: list[dict], recent_trades: list[dict]) -> str:
    if not settings.enable_gemini or not settings.gemini_api_key:
        return "Gemini 分析未启用。"

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        prompt = f"""
你是一个证券披露情报分析助手。请基于以下已经发生且公开披露的交易记录做非个性化研究分析。
不要给出具体买入金额、仓位、保证收益或个性化交易指令。
请输出：
1. 今日最值得关注的多头/空头披露信号
2. 哪些可能是真正高信念交易，哪些可能只是薪酬、期权、税务或例行行为
3. 多个内部人/类别共振的股票
4. 主要风险和数据滞后限制

Top scores JSON:
{json.dumps(top_scores[:20], ensure_ascii=False, default=str)}

Recent trades JSON:
{json.dumps(recent_trades[:80], ensure_ascii=False, default=str)}
"""
        response = model.generate_content(prompt)
        return response.text or "Gemini 没有返回分析内容。"
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini analysis failed: %s", exc)
        return f"Gemini 分析失败：{exc}"
