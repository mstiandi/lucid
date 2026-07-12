"""
对应JokerState中的info_symmetry字段的reducer，处理信息对称性的合并和更新。
"""

# 首先还是info_symmetry的结构：
# dict[str, InfoSymmetryItem]，其中InfoSymmetryItem的结构如下：
# class InfoSymmetryItem(TypedDict):
#     from_: str  # "user" | "ta"
#     user_knew: bool
#     ta_knew: bool
#     is_sufficient: bool

def info_symmetry_reducer(old_info_symmetry: dict | None, new_info_symmetry: dict | None) -> dict:
    """
    合并旧的info_symmetry和新的info_symmetry，返回更新后的info_symmetry。
    Args:
        old_info_symmetry (dict | None): 旧的info_symmetry字典，可能为None。
        new_info_symmetry (dict | None): 新的info_symmetry字典，可能为None。
    """
    if old_info_symmetry is None:
        old_info_symmetry = {}
    if new_info_symmetry is None:
        new_info_symmetry = {}
    
    for claim_content, new_item in new_info_symmetry.items():
        if claim_content not in old_info_symmetry:
            old_info_symmetry[claim_content] = new_item
        else:
            existing_item = old_info_symmetry[claim_content]
            # 更新现有条目
            existing_item['from_'] = new_item['from_']  # 假设from_不会改变，如果需要，可以根据逻辑决定是否更新
            existing_item["user_knew"] = existing_item["user_knew"] or new_item["user_knew"]
            existing_item["ta_knew"] = existing_item["ta_knew"] or new_item["ta_knew"]
            existing_item["is_sufficient"] = existing_item["is_sufficient"] or new_item["is_sufficient"]

    return old_info_symmetry