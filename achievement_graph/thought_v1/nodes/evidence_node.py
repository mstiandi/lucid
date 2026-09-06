"""
证据节点 v2：checklist → 代码算 credit_score + 输出校验
DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 JSON 输出（与 alternative 节点一致）
"""

import json
from tools.llm._extract_json import extract_json

from ..state.JokerState import JokerState, Claim, EvidenceItem
from langchain.messages import SystemMessage
from tools.loader.load_prompts import load_prompt
from tools.llm.chat_llm import json_llm as llm
from tools.context.prompt_builder import build_prompt, format_identity
from tools.rag import retrieve_theories
from tools.rag.fact_retriever import retrieve_facts
from tools.logger import get_logger
from tools.llm.claim_index import index_fix_content


# === Checklist 选项 → 分值 ===
CHECKLIST_MAP = {
    "source_quality":    {"直接": 1.0, "间接": 0.5, "推测": 0.0},
    "relevance":         {"高度相关": 1.0, "部分相关": 0.5, "勉强沾边": 0.0},
    "counter_evidence":  {"无": 1.0, "部分": 0.5, "有明确反证": 0.0},
}

CHECKLIST_DIMS = ["source_quality", "relevance", "counter_evidence"]


def _calc_credit_score(checklist: dict) -> float:
    """从 checklist 答案计算 credit_score（等权平均）。异常值 → 兜底 0.5。"""
    scores = []
    for dim in CHECKLIST_DIMS:
        answer = checklist.get(dim, "")
        score = CHECKLIST_MAP.get(dim, {}).get(answer)
        if score is None:
            score = 0.5
        scores.append(score)
    return round(sum(scores) / len(scores), 2)


def _validate_and_fix(claims: list[dict]) -> list[dict]:
    """输出校验：补齐缺失字段、修正类型和范围异常。"""
    for c in claims:
        for e_key, e_val in c.get("evidence_from_signals", {}).items():
            e_val.setdefault("content", "")

            checklist = e_val.pop("checklist", None)
            if checklist and isinstance(checklist, dict):
                e_val["credit_score"] = _calc_credit_score(checklist)
            e_val.setdefault("credit_score", 0.5)

            if not isinstance(e_val["credit_score"], (int, float)):
                e_val["credit_score"] = 0.5

            cs = e_val["credit_score"]
            if cs < 0 or cs > 1:
                e_val["credit_score"] = max(0.0, min(1.0, cs))

    return claims



def evidence_node(state: JokerState, *, store=None) -> dict:
    log = get_logger()
    pending_claims = [c for c in state['all_claims'] if c.get('status', 'pending') == 'pending']
    if not pending_claims:
        return {}

    needed_claims = "\n".join([f"#{i}  Claim: {c['content']}" for i, c in enumerate(pending_claims)])

    theory_context = retrieve_theories(pending_claims, top_k=3)
    fact_context = retrieve_facts(pending_claims, store, top_k=3)
    identity_context = format_identity(state.get("identity") or {})

    prompt = build_prompt(
        node_name="evidence_node",
        system_prompt=load_prompt("evidence_prompt.md"),
        all_signals=state.get("all_signals"),
        claims_text="所有status为pending的待验证的claims如下（每条前面有编号）：\n" + needed_claims,
        extra="【只返回JSON，不要任何其他文字。返回格式：{\"all_claims\": [...]}。每个 claim 必须包含 claim_index 字段（值为输入中的 #n 编号，如 0, 1, ...）。】",
        theory_context=theory_context,
        identity_context=identity_context,
        fact_context=fact_context,
    )

    retry_hint = ""

    # DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 LLM + JSON 解析
    for attempt in range(3):
        try:
            response = llm.invoke([SystemMessage(content=prompt + retry_hint)])
            parsed = extract_json(response.content if hasattr(response, 'content') else str(response))
            if parsed and isinstance(parsed, dict) and "all_claims" in parsed:
                updated_claims = parsed["all_claims"]
                if isinstance(updated_claims, list):
                    updated_claims = _validate_and_fix(updated_claims)
                    updated_claims = index_fix_content(updated_claims, pending_claims)
                    for c in updated_claims:
                        c.pop("claim_index", None)
                        c['analysed_by'] = ["evidence_agent"]
                    log.info("EVIDENCE", "LLM 调用成功", claims=len(updated_claims))
                    return {"all_claims": updated_claims}

            preview = raw_text[:300] if (raw_text := (response.content if hasattr(response, 'content') else str(response))) else "(empty)"
            log.warn("EVIDENCE", "JSON 解析失败或 all_claims 缺失", attempt=attempt + 1, raw_preview=preview)
            retry_hint = f"\n\n【上一轮返回的 JSON 格式无效。你的上一轮输出以如下内容开头：\n```\n{preview}\n```\n请确保：1) 所有字符串用双引号包裹 2) 没有末尾多余逗号 3) 所有花括号完整闭合。请重试返回合法 JSON。】"
        except Exception as e:
            log.warn("EVIDENCE", "调用异常", attempt=attempt + 1, error=str(e))
            retry_hint = f"\n\n【上一轮调用异常。请重试返回合法 JSON。】"

    return {}
