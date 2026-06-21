from __future__ import annotations

import json
import logging

from app.config import settings

log = logging.getLogger(__name__)


SYSTEM_INSTRUCTIONS = """
你是一个证券披露情报分析助手，专门分析 SEC Form 4、13F、13D/13G、国会交易和其它公开披露记录。
你的任务是把结构化披露数据转化为非个性化研究报告。

硬性规则：
- 只基于已经发生且公开披露的交易行为和权威来源分析。
- 不要编造未提供的数据。
- 不要给出个性化证券投资建议、保证收益、具体仓位、买入金额或精确买卖指令。
- 可以输出观察名单、信号强弱、风险、数据滞后、需要二次验证的事项。
- 明确区分主动买入/主动卖出、期权/授予/税务/薪酬/10b5-1 等可能非主动交易。
- 当只有卖出/减持而没有买入时，不要把所有减持都解释为看空；优先提醒可能是 10b5-1、薪酬、税务、分散化或家族信托减持。
"""


def _generate_with_google_genai(prompt: str) -> str:
    """Use current google-genai SDK: pip package google-genai; import path from google import genai."""
    from google import genai  # type: ignore

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
    )
    return getattr(response, "text", None) or "Gemini 没有返回分析内容。"


def _generate_with_legacy_google_generativeai(prompt: str) -> str:
    """Fallback for older environments that installed google-generativeai instead."""
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    response = model.generate_content(prompt)
    return getattr(response, "text", None) or "Gemini 没有返回分析内容。"


def analyze_with_gemini(top_scores: list[dict], recent_trades: list[dict]) -> str:
    if not settings.enable_gemini or not settings.gemini_api_key:
        return "Gemini 分析未启用。"

    if not top_scores and not recent_trades:
        return (
            "本次扫描没有可供 Gemini 深度分析的新增或近期披露数据。"
            "系统已跳过 AI 生成，避免在空数据情况下输出泛化模板或无依据分析。"
        )

    try:
        prompt = f"""
{SYSTEM_INSTRUCTIONS}

请基于以下已经采集并标准化的公开披露数据，生成中文研究分析摘要。

重要约束：
- 如果 Top scores JSON 和 Recent trades JSON 都为空，请只回复：本次没有可分析的披露数据。
- 如果数据很少，请直接说明数据不足，不要输出假设性框架、教程或示例。
- 不要说“请提供数据”，因为数据来自自动化系统；只需说明本次扫描数据不足。
- 对 S/M/F/A/G/J 等代码要谨慎解释：S 是卖出，但 M/A/F/G/J 通常不是主动买卖信号。
- 如果某个股票的卖出来自同一报告人、同一 Form 4 的多笔拆分成交，必须说明这不是多个独立巨鲸共振。

请输出以下部分：
1. 今日最值得关注的多头披露信号
2. 今日最值得关注的减持/卖出披露信号
3. 可能的高信念交易 vs 可能的例行/薪酬/税务/期权相关交易
4. 多个巨鲸或多个类别共振的股票
5. 需要人工复核的异常点
6. 数据限制、披露滞后和风险提示

Top scores JSON:
{json.dumps(top_scores[:25], ensure_ascii=False, default=str)}

Recent trades JSON:
{json.dumps(recent_trades[:120], ensure_ascii=False, default=str)}
"""
        try:
            return _generate_with_google_genai(prompt)
        except Exception as first_exc:  # noqa: BLE001
            log.warning("google-genai call failed; trying legacy google-generativeai fallback: %s", first_exc)
            try:
                return _generate_with_legacy_google_generativeai(prompt)
            except Exception as second_exc:  # noqa: BLE001
                raise RuntimeError(
                    "Gemini SDK 调用失败。请确认 requirements.txt 包含 google-genai>=1.0.0，"
                    "GitHub Actions 已重新安装依赖，并且 GEMINI_API_KEY/GEMINI_MODEL 有效。"
                    f" 原始错误1={first_exc}; 错误2={second_exc}"
                ) from second_exc
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini analysis failed: %s", exc)
        return f"Gemini 分析失败：{exc}"
