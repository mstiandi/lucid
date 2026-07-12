"""
对应JokerState中的contradictions字段的reducer，处理矛盾的合并和更新。
"""

# 首先还是contradictions的结构：
# dict[str, list[ContradictionItem]]，其中ContradictionItem的结构如下：
# class ContradictionItem(TypedDict):
#     reason: str

def contradictions_reducer(old_contradictions: dict | None, new_contradictions: dict | None) -> dict:
    """
    合并旧的contradictions和新的contradictions，返回更新后的contradictions。
    Args:
        old_contradictions (dict | None): 旧的contradictions字典，可能为None。
        new_contradictions (dict | None): 新的contradictions字典，可能为None。
    """
    if old_contradictions is None:
        old_contradictions = {}
    if new_contradictions is None:
        new_contradictions = {}
    
    for claim_content, new_items in new_contradictions.items():
        if claim_content not in old_contradictions:
            old_contradictions[claim_content] = new_items
        else:
            existing_items = old_contradictions[claim_content]
            existing_reasons = {item["reason"] for item in existing_items}
            for new_item in new_items:
                if new_item["reason"] not in existing_reasons:
                    existing_items.append(new_item)
                    existing_reasons.add(new_item["reason"])

    return old_contradictions