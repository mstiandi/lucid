"""
对应JokerState中的all_claims字段的reducer，处理信号的合并和更新。
"""

# 首先是all_claims的结构：
# list[Claim]，其中Claim的结构如下：
# class Claim(TypedDict):
#     content: str
#     direction: Literal["single", "both"]
#     analysed_by: list[str]
#     status: Literal["pending", "analysed"]
#     evidence_from_signals: dict[str, EvidenceItem]
#     alternative_explanations: dict[str, AlternativeItem]

# new_claims是一个list[Claim]，表示新发现的claims，可能是空列表。直接追加就行，本质上应该就是一个add_list
# 不对，这个reducer可以同时应对evidence和alternative的更新，还有summary中的status的更新，所以应该做的更加仔细


def all_claims_reducer(old_claims: list | None, new_claims: list | None) -> list:
    """
    合并旧的claims和新的claims，返回更新后的all_claims。
    Args:
        old_claims (list | None): 旧的claims列表，可能为None。
        new_claims (list | None): 新的claims列表，可能为None。
    """
    if old_claims is None:
        old_claims = []
    if new_claims is None:
        new_claims = []

    old_claims_dict = {claim["content"]: claim for claim in old_claims} # 已经存在的claims
    for claim in new_claims:
        if claim["content"] not in old_claims_dict:
            # 新 claim → 补齐默认字段
            claim.setdefault("direction", "single")
            claim.setdefault("analysed_by", [])
            claim.setdefault("status", "pending")
            claim.setdefault("evidence_from_signals", {})
            claim.setdefault("alternative_explanations", {})
            old_claims_dict[claim["content"]] = claim
        else:
            # 如果已经存在，则更新evidence_from_signals和alternative_explanations
            existing_claim = old_claims_dict[claim["content"]] # dict, list, set可变，同时改变
            existing_claim["evidence_from_signals"].update(claim.get("evidence_from_signals", {}))
            existing_claim["alternative_explanations"].update(claim.get("alternative_explanations", {}))
            existing_claim["status"] = claim.get("status", existing_claim["status"])
            existing_claim["analysed_by"] = list(set(existing_claim["analysed_by"] + claim.get("analysed_by", [])))
    
    return list(old_claims_dict.values())

    
    

