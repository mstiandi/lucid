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
    注册两类信号以提醒 summary：
    1. 弱证据：credit_score < 0.5 的证据（不支撑该 claim）
    2. 替代解释：alternative 节点产出的其他解读
    注意——这些不是"矛盾"（行为冲突），而是"该 claim 的证据基础不够坚实"。
    """
    needed_claims = [c for c in state['all_claims'] if c.get('status', 'pending') == 'pending' and (any(e.get('credit_score', 0.5) < 0.5 for e in c.get('evidence_from_signals', {}).values()) or c.get('alternative_explanations', {}))]
    contradictions = {}

    for claim in needed_claims:
        reasons = []
        for evidence in claim['evidence_from_signals'].values():
            if evidence.get('credit_score', 0.5) < 0.5:
                reasons.append({
                    "type": "weak_evidence",
                    "reason": f"证据'{evidence.get('content', '?')}'支撑度不足（credit_score={evidence.get('credit_score', 0.5)}），不能充分支持该观点"
                })
        for signal_info, alt in claim['alternative_explanations'].items():
            reasons.append({
                "type": "alternative_explanation",
                "reason": f"信号'{signal_info}'有替代解读：'{alt.get('alternative', '?')}'"
            })

        contradictions[claim['content']] = reasons

    return {"contradictions": contradictions}