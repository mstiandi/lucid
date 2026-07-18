"""
信息对称性节点 v2：checklist → 代码判定 is_sufficient + 输出校验
"""

from ..state.JokerState import JokerState, InfoSymmetryItem
from langchain.tools import tool
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from tools.llm.safe_llm_call import safe_llm_call
from tools.context.prompt_builder import build_prompt
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


@tool
def information_symmetry_return(info_symmetry: dict[str, dict]) -> dict:
    """
    information_symmetry_agent 的返回值。
    Args:
        info_symmetry (dict[str, dict]):
        键是 claim 的 content，值结构：
        {
            "from_": "user" | "ta",
            "user_knew": bool,
            "ta_knew": bool,
            "checklist": {
                "has_ta_signals": "有|仅有用户陈述|无",
                "claim_specificity": "直接相关|间接相关|无关",
                "gap_size": "小|中|大"
            }
        }
        is_sufficient 由代码根据 checklist 计算，不需要返回。
    """
    return {"info_symmetry": info_symmetry}


def information_symmetry_node(state: JokerState) -> dict:
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
    )

    response = safe_llm_call(llm, [information_symmetry_return],
        [SystemMessage(content=prompt)], node_name="INFO_SYMM")

    if response is None:
        return {}

    tool_call = response.tool_calls[-1]
    args = tool_call["args"]
    updated_info_symmetry = args.get("info_symmetry", {})

    # === 校验 + 算 is_sufficient ===
    updated_info_symmetry = _validate_info_items(updated_info_symmetry)

    # === 更新 analysed_by ===
    updated_claims = [{
        "content": c["content"],
        "analysed_by": ["information_symmetry_agent"],
    } for c in info_symmetry_claims]

    return {"info_symmetry": updated_info_symmetry, "all_claims": updated_claims}
