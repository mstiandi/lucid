"""
证据节点 v2：checklist → 代码算 credit_score + 输出校验（三层防御第一层）
LLM 回答 3 道选择题，Python 根据答案计算 credit_score。
"""

from ..state.JokerState import JokerState, Claim, EvidenceItem
from langchain.tools import tool
from langchain.messages import SystemMessage
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from tools.llm.safe_llm_call import safe_llm_call
from tools.context.prompt_builder import build_prompt
from tools.rag import retrieve_theories


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


def _parse_index(raw) -> int | None:
    """归一化 claim_index：处理 '#1' / '1' / 1 / '# 1' 等各种 LLM 可能输出。"""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip().lstrip("#").strip()
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _index_fix_content(updated_claims: list[dict], pending_claims: list[dict]) -> list[dict]:
    """用 claim_index 精确定位 pending claim，强覆盖 LLM 返回的 content（问题 #5）。"""
    for uc in updated_claims:
        idx = _parse_index(uc.get("claim_index"))
        if idx is not None and 0 <= idx < len(pending_claims):
            uc["content"] = pending_claims[idx]["content"]
        else:
            # index 缺失/越界/无法解析 → 尝试 content 精确匹配兜底
            llm_content = uc.get("content", "")
            matched = None
            for pc in pending_claims:
                if pc["content"] == llm_content:
                    matched = pc
                    break
            if matched is None and len(pending_claims) == 1:
                matched = pending_claims[0]
            if matched is not None:
                uc["content"] = matched["content"]
            # 实在对不上 → 保留 LLM 值

    return updated_claims


def _validate_and_fix(claims: list[dict]) -> list[dict]:
    """输出校验：补齐缺失字段、修正类型和范围异常（三层防御第一层）。"""
    for c in claims:
        for e_key, e_val in c.get("evidence_from_signals", {}).items():
            # 校验 content
            e_val.setdefault("content", "")

            # 如果 LLM 返回了 checklist → 代码算分；否则用旧逻辑：直接取 credit_score 再兜底
            checklist = e_val.pop("checklist", None)
            if checklist and isinstance(checklist, dict):
                e_val["credit_score"] = _calc_credit_score(checklist)
            # --- 此时 e_val 可能已有 credit_score（旧 prompt），或刚刚算出，或都没有 ---
            e_val.setdefault("credit_score", 0.5)

            # 类型校验
            if not isinstance(e_val["credit_score"], (int, float)):
                e_val["credit_score"] = 0.5

            # 范围裁剪
            cs = e_val["credit_score"]
            if cs < 0 or cs > 1:
                e_val["credit_score"] = max(0.0, min(1.0, cs))

    return claims


@tool
def evidence_return(all_claims: list[dict]) -> dict:
    """
    证据节点的返回值。为每个待验证的 claim 填入从信号中找到的证据。
    Args:
        all_claims (list[dict]): 每个元素对应一个 claim：
        {
            "claim_index": int,             # 输入中每个 claim 的编号（#0, #1, ...），用于精确关联
            "content": str,                 # claim 原文
            "evidence_from_signals": {      # 证据字典
                "evidence1": {
                    "content": str,         # 完整证据描述
                    "checklist": {          # 由代码算分后移除
                        "source_quality": "直接|间接|推测",
                        "relevance": "高度相关|部分相关|勉强沾边",
                        "counter_evidence": "无|部分|有明确反证"
                    }
                },
                ...
            }
        }
    """
    return {"all_claims": all_claims}


def evidence_node(state: JokerState) -> dict:
    pending_claims = [c for c in state['all_claims'] if c.get('status', 'pending') == 'pending']
    if not pending_claims:
        return {}

    needed_claims = "\n".join([f"#{i}  Claim: {c['content']}" for i, c in enumerate(pending_claims)])

    theory_context = retrieve_theories(pending_claims, top_k=3)

    prompt = build_prompt(
        node_name="evidence_node",
        system_prompt=load_prompt("evidence_prompt.md"),
        all_signals=state.get("all_signals"),
        claims_text="所有status为pending的待验证的claims如下（每条前面有编号）：\n" + needed_claims,
        extra="请在返回值中给每个 claim 带上 \"claim_index\" 字段，值为对应编号（如 0, 1, ...）。",
        theory_context=theory_context,
    )

    response = safe_llm_call(llm, [evidence_return],
        [SystemMessage(content=prompt)], node_name="EVIDENCE")

    if response is None:
        return {}

    tool_call = response.tool_calls[-1]
    args = tool_call["args"]
    updated_claims = args.get("all_claims", [])

    # === 输出校验（三层防御第一层）===
    updated_claims = _validate_and_fix(updated_claims)
    # === content 修正（问题 #5）===
    updated_claims = _index_fix_content(updated_claims, pending_claims)

    for c in updated_claims:
        c.pop("claim_index", None)  # 清理 metadata，不写入 state
        c['analysed_by'] = ["evidence_agent"]

    return {"all_claims": updated_claims}
