"""
纯代码评分：不调 LLM。
- RAG 召回率（recall@1 / recall@3）
- 结构完整性（各节点是否产出非空结果）
"""

from langchain.messages import AIMessage
from tools.rag.retriever import retrieve_theories_raw


# ─── RAG 召回率 ──────────────────────────────────────

def score_rag(scenario: dict) -> dict:
    """
    用 ground_truth.expected_theories 计算 recall@1 和 recall@3。

    Returns:
        {
            "retrieved": ["基本归因错误", ...],
            "relevant": ["基本归因错误"],
            "recall_1": 1 | 0,
            "recall_3": float,   # hits / len(relevant)
            "hits": ["基本归因错误"],
            "misses": []
        }
    """
    relevant = set(scenario.get("ground_truth", {}).get("relevant_theories", []))
    if not relevant:
        return {
            "retrieved": [], "relevant": [],
            "recall_1": None, "recall_3": None,
            "hits": [], "misses": [],
            "note": "ground_truth.relevant_theories 为空，跳过 RAG 评分"
        }

    claims = [{"content": scenario.get("description", "")}]
    cards = retrieve_theories_raw(claims, top_k=3)
    retrieved = [c["name"] for c in cards]

    hits = [name for name in retrieved if name in relevant] # 第一条理论命中了
    misses = [name for name in relevant if name not in retrieved]

    recall_1 = 1 if retrieved and retrieved[0] in relevant else 0
    recall_3 = len(hits) / len(relevant) if relevant else 0

    return {
        "retrieved": retrieved,
        "relevant": list(relevant),
        "recall_1": recall_1,
        "recall_3": round(recall_3, 2),
        "hits": hits,
        "misses": misses,
    }


# ─── 结构完整性 ───────────────────────────────────────

def score_structure(result: dict) -> dict:
    """
    检查 graph 输出结构是否完整。

    Returns:
        {
            "checks": {
                "graph_completed": true,
                "all_claims_have_evidence": true,
                "all_claims_have_alternatives": true,
                "info_symmetry_produced": true,
                "contradictions_produced": true
            },
            "passed": 4,
            "total": 5,
            "score": 0.8
        }
    """
    checks = {}

    # 1. graph 是否完成（有 messages 且最后一条非空）
    messages = result.get("messages", [])
    checks["graph_completed"] = any(isinstance(message, AIMessage) for message in messages)
    # 只有summary节点会往messages中塞AIMessage

    # 2. 每个 claim 是否有 evidence
    claims = result.get("all_claims", [])
    if claims:
        checks["all_claims_have_evidence"] = all(
            c.get("evidence_from_signals") for c in claims
        )
        checks["all_claims_have_alternatives"] = all(
            c.get("alternative_explanations") for c in claims
        )
    else:
        checks["all_claims_have_evidence"] = False
        checks["all_claims_have_alternatives"] = False

    # 3. info_symmetry 是否有产出
    info_sym = result.get("info_symmetry", {})
    checks["info_symmetry_produced"] = bool(info_sym) and any(
        v.get("is_sufficient") is not None for v in info_sym.values() # info_symmetry节点被执行就行了
        if isinstance(v, dict)
    )

    # 4. contradictions 是否有产出（至少有一个 contradiction）
    contradictions = result.get("contradictions", {})
    checks["contradictions_produced"] = bool(contradictions) and any(
        len(items) > 0 for items in contradictions.values()
        if isinstance(items, list)
    )

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)

    return {
        "checks": checks,
        "passed": passed,
        "total": total,
        "score": round(passed / total, 2) if total else 0,
    }
