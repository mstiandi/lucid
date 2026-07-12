"""
contradictory_registration_agent
纯代码，不用调用模型
"""
# schema:
# class EvidenceItem(TypedDict):
#     content: str
#     credit_score: float

# class AlternativeItem(TypedDict):
#     youthink: str
#     alternative: str

# class Claim(TypedDict):
#     content: str
#     direction: Literal["single", "both"]
#     analysed_by: list[str]
#     status: Literal["pending", "analysed"]
#     evidence_from_signals: dict[str, EvidenceItem]
#     alternative_explanations: dict[str, AlternativeItem]

# class JokerState(TypedDict):
#     messages: Annotated[list, add_messages]
#     all_signals: Annotated[AllSignals, all_signals_reducer]
#     all_claims: Annotated[list[Claim], all_claims_reducer]
#     contradictions: Annotated[dict[str, list[ContradictionItem]], contradictions_reducer]  # claim_content -> contradiction_item
#     info_symmetry: Annotated[dict[str, InfoSymmetryItem], info_symmetry_reducer]
#     next_agents: list[str]
#     new_signals: bool  # 覆盖
    
from ..state.JokerState import JokerState

def contradictory_registration_node(state: JokerState) -> dict:
    """
    对JokerState中的all_claims中的满足credit_score < 0.5的evidence_from_signals或alternative_explanations非空的Claim进行注册，注册到contradictions中。
    返回的字典中包含contradictions字段，格式为：
    {
        "claim_content": [
            {
                "reason": str
            }
        ]
    """
    needed_claims = [c for c in state['all_claims'] if c['status'] == 'pending' and (any(e['credit_score'] < 0.5 for e in c['evidence_from_signals'].values()) or c['alternative_explanations'])]
    contradictions = {}

    for claim in needed_claims: # 遍历需要进行矛盾注册的Claim
        reason = []
        for evidence in claim['evidence_from_signals'].values(): # 遍历某个Claim的所有验证信息evidence
            if evidence['credit_score'] < 0.5:
                reason.append(f"Evidence: '{evidence['content']}' has low credit score: {evidence['credit_score']}.")
        for signal_info, alt in claim['alternative_explanations'].items(): # 遍历某个Claim的所有alternative explanations
            reason.append(f"Signal_info: '{signal_info}'.\n Alternative explanation: '{alt['alternative']}'.")

        contradictions[claim['content']] = [{"reason": r} for r in reason]

    return {"contradictions": contradictions}