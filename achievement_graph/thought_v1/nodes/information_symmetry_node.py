"""
信息对称性节点 v2：checklist → 代码判定 is_sufficient + 输出校验
DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 JSON 输出（与 evidence/alternative 节点一致）
"""

import json
from tools.llm._extract_json import extract_json

from ..state.JokerState import JokerState, InfoSymmetryItem
from tools.loader.load_prompts import load_prompt
from tools.llm.chat_llm import json_llm as llm
from tools.context.prompt_builder import build_prompt, format_identity
from tools.rag.fact_retriever import retrieve_facts
from tools.logger import get_logger
from langchain.messages import SystemMessage


# === Checklist 选项 → 分值 ===
CHECKLIST_MAP = {
    "has_ta_signals":    {"有": 1.0, "仅有用户陈述": 0.5, "无": 0.0},
    "claim_specificity": {"直接相关": 1.0, "间接相关": 0.5, "无关": 0.0},
    "gap_size":          {"小": 1.0, "中": 0.5, "大": 0.0},
}

CHECKLIST_DIMS = ["has_ta_signals", "claim_specificity", "gap_size"]
IS_SUFFICIENT_THRESHOLD = 0.67


def _calc_is_sufficient(checklist: dict) -> bool:
    """从 checklist 答案计算 is_sufficient。异常值 → 兜底 0.5。"""
    scores = []
    for dim in CHECKLIST_DIMS:
        answer = checklist.get(dim, "")
        score = CHECKLIST_MAP.get(dim, {}).get(answer)
        if score is None:
            score = 0.5
        scores.append(score)
    avg = sum(scores) / len(scores)
    return avg >= IS_SUFFICIENT_THRESHOLD


def _validate_info_items(info_symmetry: dict) -> dict:
    """校验每个 InfoSymmetryItem：算 is_sufficient、补齐缺失字段。"""
    for claim_content, item in info_symmetry.items():
        if not isinstance(item, dict):
            info_symmetry[claim_content] = {"from_": "user", "user_knew": True, "ta_knew": False, "is_sufficient": False}
            continue

        # checklist → is_sufficient
        checklist = item.pop("checklist", {})
        if isinstance(checklist, dict) and checklist:
            item["is_sufficient"] = _calc_is_sufficient(checklist)

        # setdefault 补齐
        item.setdefault("from_", "user")
        item.setdefault("user_knew", True)
        item.setdefault("ta_knew", False)
        item.setdefault("is_sufficient", False)

    return info_symmetry



def information_symmetry_node(state: JokerState, *, store=None) -> dict:
    log = get_logger()
    pending_claims = [c for c in state["all_claims"] if c.get("status", "pending") == "pending"]
    info_symmetry_claims = [c for c in pending_claims if c.get("direction", "single") == "both"]

    if not info_symmetry_claims:
        return {}

    needed_claims = "\n".join([f"#{i}  Claim: {c['content']}" for i, c in enumerate(info_symmetry_claims)])

    prompt = build_prompt(
        node_name="information_symmetry_node",
        system_prompt=load_prompt("information_symmetry_prompt.md"),
        all_signals=state.get("all_signals"),
        claims_text="所有direction为both的待处理的claims如下（每条前面有编号）：\n" + needed_claims,
        extra="【只返回JSON，不要任何其他文字。返回格式：{\"info_symmetry\": {...}}。每个 key 是 claim 的原文。】",
        identity_context=format_identity(state.get("identity") or {}),
        fact_context=retrieve_facts(info_symmetry_claims, store, top_k=3),
    )

    retry_hint = ""

    # DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 LLM + JSON 解析
    for attempt in range(3):
        try:
            response = llm.invoke([SystemMessage(content=prompt + retry_hint)])
            parsed = extract_json(response.content if hasattr(response, 'content') else str(response))
            if parsed and isinstance(parsed, dict) and "info_symmetry" in parsed:
                updated_info_symmetry = parsed["info_symmetry"]

                # === 校验 + 算 is_sufficient ===
                updated_info_symmetry = _validate_info_items(updated_info_symmetry)

                # === 更新 analysed_by ===
                updated_claims = [{
                    "content": c["content"],
                    "analysed_by": ["information_symmetry_agent"],
                } for c in info_symmetry_claims]

                log.info("INFO_SYMM", "LLM 调用成功", claims=len(updated_info_symmetry))
                return {"info_symmetry": updated_info_symmetry, "all_claims": updated_claims}

            preview = raw_text[:300] if (raw_text := (response.content if hasattr(response, 'content') else str(response))) else "(empty)"
            log.warn("INFO_SYMM", "JSON 解析失败或 info_symmetry 缺失", attempt=attempt + 1, raw_preview=preview)
            retry_hint = f"\n\n【上一轮返回的 JSON 格式无效。你的上一轮输出以如下内容开头：\n```\n{preview}\n```\n请确保：1) 所有字符串用双引号包裹 2) 没有末尾多余逗号 3) 所有花括号完整闭合。请重试返回合法 JSON。】"
        except Exception as e:
            log.warn("INFO_SYMM", "调用异常", attempt=attempt + 1, error=str(e))
            retry_hint = f"\n\n【上一轮调用异常。请重试返回合法 JSON。】"

    return {}
