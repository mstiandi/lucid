"""
这里定义 JokerState 类，各种字段、参数，联合reducer -- D:\my_joker\tools\reducer
"""

from typing import TypedDict, Literal, Annotated
from langgraph.graph import add_messages
from tools.reducer import all_claims_reducer, all_signals_reducer, contradictions_reducer, info_symmetry_reducer

# 嵌套结构逐层定义
class EvidenceItem(TypedDict):
    content: str
    credit_score: float

class AlternativeItem(TypedDict):
    youthink: str
    alternative: str

class Claim(TypedDict):
    content: str
    direction: Literal["single", "both"]
    analysed_by: list[str]
    status: Literal["pending", "analysed"]
    evidence_from_signals: dict[str, EvidenceItem]
    alternative_explanations: dict[str, AlternativeItem]

class SignalBehavior(TypedDict):
    action: str
    signal_type: str
    confidence: float
    source_ref: str  # 原话

class PersonSignals(TypedDict):
    initiative_score: float
    emotional_explicitness: float
    signal_clarity: float
    behaviors: list[SignalBehavior]

class AllSignals(TypedDict):
    user: PersonSignals
    ta: PersonSignals

class ContradictionItem(TypedDict):
    reason: str

class InfoSymmetryItem(TypedDict):
    from_: str  # "user" | "ta"
    user_knew: bool
    ta_knew: bool
    is_sufficient: bool

class JokerState(TypedDict):
    messages: Annotated[list, add_messages]
    all_signals: Annotated[AllSignals, all_signals_reducer]
    all_claims: Annotated[list[Claim], all_claims_reducer]
    contradictions: Annotated[dict[str, list[ContradictionItem]], contradictions_reducer]  # claim_content -> contradiction_item
    info_symmetry: Annotated[dict[str, InfoSymmetryItem], info_symmetry_reducer]
    next_agents: list[str]
    new_signals: bool  # 覆盖
    alt_gaps: list[str]  # 替代解释节点未能产出的 claim content 列表，供 summary 警告用户