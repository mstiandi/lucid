"""
替代解释节点 v3：纯 JSON 输出 + 智能重试 + 不丢弃 claim
DeepSeek function calling 在复杂嵌套结构上不可靠 → 改用纯 JSON 输出
"""

import json
from tools.llm._extract_json import extract_json

from ..state.JokerState import JokerState, Claim, AlternativeItem
from tools.loader.load_prompts import load_prompt
from tools.llm.chat_llm import json_llm as llm
from tools.context.prompt_builder import build_prompt, format_identity
from tools.rag import retrieve_theories
from tools.rag.fact_retriever import retrieve_facts
from tools.logger import get_logger
from tools.llm.claim_index import index_fix_content
from langchain.messages import SystemMessage


def _cleanup_alt_entry(entry: dict) -> dict:
    entry.pop("checklist", None)
    entry.pop("skip_reason", None)
    return entry


def _process_claims(claims: list[dict]) -> tuple[list[dict], list[str], int]:
    """处理所有 claims：清洗替代解释、记录缺口。不丢弃任何 claim。"""
    log = get_logger()
    gaps = []
    total_alts = 0

    for c in claims:
        alts = c.get("alternative_explanations", {})
        cleaned = {}
        for sig_key, entry in alts.items():
            entry = _cleanup_alt_entry(entry)
            if entry.get("alternative"):
                cleaned[sig_key] = entry
                total_alts += 1
        c["alternative_explanations"] = cleaned

        if not cleaned:
            gaps.append(c.get("content", "?"))

    if gaps:
        log.warn("ALTERNATIVE", f"{len(gaps)} 个 claim 无替代解释", claims=gaps)
    if total_alts:
        log.info("ALTERNATIVE", f"产出 {total_alts} 条替代解释", coverage=len(claims) - len(gaps))

    return claims, gaps, total_alts



def alternative_explanation_node(state: JokerState, *, store=None) -> dict:
    log = get_logger()
    pending_claims = [c for c in state["all_claims"] if c.get("status", "pending") == "pending"]
    if not pending_claims:
        return {}

    needed_claims = "\n".join([f"#{i}  Claim: {c['content']}" for i, c in enumerate(pending_claims)])

    prompt = build_prompt(
        node_name="alternative_explanation_node",
        system_prompt=load_prompt("alternative_explanation_prompt.md"),
        all_signals=state.get("all_signals"),
        claims_text="所有status为pending的待验证的claims如下（每条前面有编号）：\n" + needed_claims,
        extra="【只返回JSON，不要任何其他文字。返回格式：{\"all_claims\": [...]}。每个 claim 必须包含 claim_index 字段（值为输入中的 #n 编号，如 0, 1, ...）。】",
        theory_context=retrieve_theories(pending_claims, top_k=3),
        identity_context=format_identity(state.get("identity") or {}),
        fact_context=retrieve_facts(pending_claims, store, top_k=3),
    )

    retry_hint = ""

    # DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 LLM + JSON 解析
    for attempt in range(3):
        try:
            full_prompt = prompt + retry_hint
            response = llm.invoke([SystemMessage(content=full_prompt)])
            raw_text = response.content if hasattr(response, 'content') else str(response)
            parsed = extract_json(raw_text)
            if parsed and isinstance(parsed, dict) and "all_claims" in parsed:
                updated_claims = parsed["all_claims"]
                if isinstance(updated_claims, list):
                    # === content 修正 ===
                    updated_claims = index_fix_content(updated_claims, pending_claims)
                    # === 处理所有 claims（不丢弃无替代解释的） ===
                    all_updated, alt_gaps, total_alts = _process_claims(updated_claims)
                    for c in all_updated:
                        c.pop("claim_index", None)
                        c['analysed_by'] = c.get('analysed_by', [])
                        if "alternative_explanation_agent" not in c['analysed_by']:
                            c['analysed_by'].append("alternative_explanation_agent")
                    return {"all_claims": all_updated, "alt_gaps": alt_gaps}

            # 解析失败 → 记录片段，下次重试带提示（含 LLM 实际输出片段）
            preview = raw_text[:300] if raw_text else "(empty)"
            log.warn("ALTERNATIVE", "JSON 解析失败或 all_claims 缺失",
                     attempt=attempt + 1, raw_preview=preview)
            retry_hint = f"\n\n【上一轮返回的 JSON 格式无效。你的上一轮输出以如下内容开头：\n```\n{preview}\n```\n请确保：1) 所有字符串用双引号包裹 2) 没有末尾多余逗号 3) 所有花括号完整闭合。请重试返回合法 JSON。】"

        except Exception as e:
            log.warn("ALTERNATIVE", "调用异常", attempt=attempt + 1, error=str(e))
            retry_hint = f"\n\n【上一轮调用异常。请重试返回合法 JSON。】"

    # 三轮全败 → 返回空，pending claims 下轮可重试
    return {}
