"""
claim_index 工具：处理 LLM 返回的 claim_index 字段，将编号映射回 pending claim 的原始 content。
"""


def parse_index(raw) -> int | None:
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


def index_fix_content(updated_claims: list[dict], pending_claims: list[dict]) -> list[dict]:
    """用 claim_index 精确定位 pending claim，强覆盖 LLM 返回的 content。"""
    for uc in updated_claims:
        idx = parse_index(uc.get("claim_index"))
        if idx is not None and 0 <= idx < len(pending_claims):
            uc["content"] = pending_claims[idx]["content"]
        else:
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

    return updated_claims
