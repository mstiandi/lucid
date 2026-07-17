"""
替代解释节点 v2：DeepSeek function calling 在复杂嵌套结构上不可靠 → 改用纯 JSON 输出
"""

import json
import re

from ..state.JokerState import JokerState, Claim, AlternativeItem
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from tools.llm.safe_llm_call import safe_llm_call
from tools.logger import get_logger
from langchain.messages import SystemMessage, HumanMessage


def _parse_index(raw) -> int | None:
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
    for uc in updated_claims:
        idx = _parse_index(uc.get("claim_index"))
        if idx is not None and 0 <= idx < len(pending_claims):
            uc["content"] = pending_claims[idx]["content"]
        else:
            llm_content = uc.get("content", "")
            matched = None
            for p in pending_claims:
                if p["content"] == llm_content:
                    matched = p
                    break
            if matched is None and len(pending_claims) == 1:
                matched = pending_claims[0]
            if matched is not None:
                uc["content"] = matched["content"]
    return updated_claims


def _cleanup_alt_entry(entry: dict) -> dict:
    entry.pop("checklist", None)
    entry.pop("skip_reason", None)
    return entry


def _validate_and_clean(claims: list[dict]) -> tuple[list[dict], list[str]]:
    log = get_logger()
    gaps = []
    valid_claims = []

    for c in claims:
        alts = c.get("alternative_explanations", {})
        cleaned = {}
        for sig_key, entry in alts.items():
            entry = _cleanup_alt_entry(entry)
            if entry.get("alternative"):
                cleaned[sig_key] = entry
        c["alternative_explanations"] = cleaned

        if cleaned:
            valid_claims.append(c)
        else:
            gaps.append(c.get("content", "?"))

    if gaps:
        log.warn("ALTERNATIVE", f"{len(gaps)} 个 claim 无替代解释", claims=gaps)
    if valid_claims:
        total_alts = sum(len(c["alternative_explanations"]) for c in valid_claims)
        log.info("ALTERNATIVE", f"产出 {total_alts} 条替代解释", coverage=len(valid_claims))

    return valid_claims, gaps


def _extract_json(text: str) -> dict | None:
    """从 LLM 文本回复中提取 JSON 对象。处理 ```json ... ``` 包裹或裸 JSON。"""
    # 尝试直接解析
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # 尝试匹配 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 尝试匹配第一个 { 到最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def alternative_explanation_node(state: JokerState) -> dict:
    log = get_logger()
    pending_claims = [c for c in state["all_claims"] if c.get("status", "pending") == "pending"]
    if not pending_claims:
        return {}

    needed_claims = "\n".join([f"#{i}  Claim: {c['content']}" for i, c in enumerate(pending_claims)])
    all_signals = state.get("all_signals", {})

    base_prompt = load_prompt("alternative_explanation_prompt.md")
    prompt = (
        base_prompt +
        "\n\n所有status为pending的待验证的claims如下（每条前面有编号）：\n" + needed_claims +
        "\n\n所有的信号如下:\n" + json.dumps(all_signals, ensure_ascii=False, indent=2) +
        "\n\n【只返回JSON，不要任何其他文字。返回格式：{\"all_claims\": [...]}】"
    )

    # DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 LLM + JSON 解析
    for attempt in range(3):
        try:
            response = llm.invoke([SystemMessage(content=prompt)])
            parsed = _extract_json(response.content if hasattr(response, 'content') else str(response))
            if parsed and isinstance(parsed, dict) and "all_claims" in parsed:
                updated_claims = parsed["all_claims"]
                if isinstance(updated_claims, list):
                    # === content 修正 ===
                    updated_claims = _index_fix_content(updated_claims, pending_claims)
                    valid_claims, alt_gaps = _validate_and_clean(updated_claims)
                    for c in valid_claims:
                        c.pop("claim_index", None)
                        c['analysed_by'] = ["alternative_explanation_agent"]
                    return {"all_claims": valid_claims, "alt_gaps": alt_gaps}
            log.warn("ALTERNATIVE", "JSON 解析失败或 all_claims 缺失", attempt=attempt+1)
        except Exception as e:
            log.warn("ALTERNATIVE", "调用异常", attempt=attempt+1, error=str(e))

    return {"alt_gaps": [c["content"] for c in pending_claims]}
