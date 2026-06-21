from __future__ import annotations

import json
import logging
import time
from typing import Iterable

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


def _fallback_models() -> list[str]:
    configured = [m.strip() for m in str(settings.gemini_model or "").split(",") if m.strip()]
    # Flash-Lite/Flash are better suited for this daily batch summary than Pro when demand spikes.
    defaults = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    models: list[str] = []
    for model in configured + defaults:
        if model and model not in models:
            models.append(model)
    return models


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(key in text for key in ["503", "unavailable", "high demand", "rate limit", "temporarily", "timeout", "deadline"])


def _generate_with_google_genai(prompt: str, model: str) -> str:
    """Use current Google GenAI SDK: pip package google-genai; import path from google import genai."""
    from google import genai  # type: ignore

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return getattr(response, "text", None) or "Gemini 没有返回分析内容。"


def _generate_with_legacy_google_generativeai(prompt: str, model: str) -> str:
    """Fallback for older environments that installed google-generativeai instead."""
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=settings.gemini_api_key)
    legacy_model = genai.GenerativeModel(model)
    response = legacy_model.generate_content(prompt)
    return getattr(response, "text", None) or "Gemini 没有返回分析内容。"


def _try_models(prompt: str, models: Iterable[str]) -> str:
    errors: list[str] = []
    for model in models:
        for attempt in range(1, 4):
            try:
                log.info("Calling Gemini model=%s attempt=%s", model, attempt)
                return _generate_with_google_genai(prompt, model)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{model}/google-genai/attempt{attempt}: {exc}")
                log.warning("Gemini google-genai failed model=%s attempt=%s: %s", model, attempt, exc)
                if not _is_transient_error(exc):
                    break
                time.sleep(min(30, 5 * attempt))

        # Legacy fallback: useful if the project still installs the old package.
        try:
            log.info("Calling Gemini legacy SDK model=%s", model)
            return _generate_with_legacy_google_generativeai(prompt, model)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{model}/legacy: {exc}")
            log.warning("Gemini legacy failed model=%s: %s", model, exc)

    short_errors = " | ".join(errors[-4:])
    return (
        "Gemini 暂时未能完成深度分析；本次 SEC 披露采集、评分和报告已正常生成。"
        "常见原因是 Gemini API 高需求/503、模型额度或临时网络问题。"
        f"最近错误：{short_errors}"
    )


def analyze_with_gemini(top_scores: list[dict], recent_trades: list[dict]) -> str:
    if not settings.enable_gemini or not settings.gemini_api_key:
        return "Gemini 分析未启用。"

    if not top_scores and not recent_trades:
        return (
            "本次扫描没有可供 Gemini 深度分析的新增或近期披露数据。"
            "系统已跳过 AI 生成，避免在空数据情况下输出泛化模板或无依据分析。"
        )

    # Feed Gemini mostly signal-bearing rows. This keeps the prompt smaller and reduces noise from A/M/F/G/J rows.
    core_recent = [t for t in recent_trades if str(t.get("action") or "") in {"BUY", "SELL"}]
    core_recent = core_recent[:80]

    prompt = f"""
{SYSTEM_INSTRUCTIONS}

请基于以下已经采集并标准化的公开披露数据，生成中文研究分析摘要。

重要约束：
- 如果 Top scores JSON 和 Recent trades JSON 都为空，请只回复：本次没有可分析的披露数据。
- 如果数据很少，请直接说明数据不足，不要输出假设性框架、教程或示例。
- 不要说“请提供数据”，因为数据来自自动化系统；只需说明本次扫描数据不足。
- 对 S/M/F/A/G/J 等代码要谨慎解释：S 是卖出，但 M/A/F/G/J 通常不是主动买卖信号。
- 如果某个股票的卖出来自同一报告人、同一 Form 4 的多笔拆分成交，必须说明这不是多个独立巨鲸共振。
- 把 P/BUY 主动买入与 S/SELL 减持分开讨论；不要把卖出直接等同于做空。

请输出以下部分：
1. 主动买入信号：只列有 P/BUY 的股票；若没有，直接说明未发现强买入信号
2. 减持/卖出预警：说明金额、独立事件数量、是否可能是计划性/薪酬/税务/分散化交易
3. 可能的高信念交易 vs 可能的例行/薪酬/税务/期权相关交易
4. 多个巨鲸或多个类别共振的股票
5. 需要人工复核的异常点
6. 数据限制、披露滞后和风险提示

Top scores JSON:
{json.dumps(top_scores[:25], ensure_ascii=False, default=str)}

Recent core BUY/SELL trades JSON:
{json.dumps(core_recent, ensure_ascii=False, default=str)}
"""
    try:
        return _try_models(prompt, _fallback_models())
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini analysis failed unexpectedly: %s", exc)
        return f"Gemini 分析失败：{exc}"
