"""项目级冒烟测试：graph 能编译、关键纯代码逻辑不回归。"""


def test_graph_compiles():
    """import graph 即完成：9 节点注册 + compile + 挂 checkpointer/store。"""
    from achievement_graph.thought_v1.graph import app

    assert app is not None


def test_extract_json_three_layer_fallback():
    from tools.llm._extract_json import extract_json

    assert extract_json('{"a": 1}') == {"a": 1}                    # 纯 JSON
    assert extract_json('```json\n{"b": 2}\n```') == {"b": 2}      # markdown 代码块
    assert extract_json('前缀废话 {"c": 3} 后缀') == {"c": 3}       # 前后有废话
    assert extract_json('这不是 JSON') is None


def test_credit_score_checklist_full_and_off_map():
    from achievement_graph.thought_v1.nodes.evidence_node import _calc_credit_score

    full = {"source_quality": "直接", "relevance": "高度相关", "counter_evidence": "无"}
    assert _calc_credit_score(full) == 1.0

    # LLM 返回了不在选项里的值 → 兜底 0.5
    off_map = {"source_quality": "乱七八糟", "relevance": "高度相关", "counter_evidence": "无"}
    assert _calc_credit_score(off_map) == round((0.5 + 1.0 + 1.0) / 3, 2)


def test_compress_behaviors_bounds_to_summary_plus_recent():
    from tools.context.compressor import compress_behaviors

    behaviors = [{"action": f"a{i}", "signal_type": "x", "confidence": 1.0, "source_ref": ""}
                 for i in range(100)]
    compressed, removed = compress_behaviors(behaviors, keep_recent=5)

    assert len(compressed) == 6        # 1 条摘要 + 最近 5 条
    assert len(removed) == 95
    assert compressed[0]["signal_type"] == "summary"


def test_merge_all_signals_weighted_average():
    from tools.reducer import merge_all_signals

    # 增量轮：旧值非 0 → 0.7 旧 + 0.3 新（新值即使是 0 也走加权）
    old = {"user": {"initiative_score": 0.8, "emotional_explicitness": 0.5,
                    "signal_clarity": 0.6, "behaviors": []},
           "ta": {"initiative_score": 0.2, "emotional_explicitness": 0.3,
                  "signal_clarity": 0.4, "behaviors": []}}
    new = {"user": {"initiative_score": 1.0, "emotional_explicitness": 1.0,
                    "signal_clarity": 1.0, "behaviors": []},
           "ta": {"initiative_score": 0.0, "emotional_explicitness": 0.0,
                  "signal_clarity": 0.0, "behaviors": []}}

    merged = merge_all_signals(old, new)
    assert merged["user"]["initiative_score"] == round(0.8 * 0.7 + 1.0 * 0.3, 2)
    assert merged["ta"]["initiative_score"] == round(0.2 * 0.7 + 0.0 * 0.3, 2)

    # 首轮：旧值 0.0 → 全量采用新值
    old2 = {"user": {"initiative_score": 0.0, "emotional_explicitness": 0.0,
                     "signal_clarity": 0.0, "behaviors": []},
            "ta": {"initiative_score": 0.0, "emotional_explicitness": 0.0,
                   "signal_clarity": 0.0, "behaviors": []}}
    new2 = {"user": {"initiative_score": 0.9, "emotional_explicitness": 0.9,
                     "signal_clarity": 0.9, "behaviors": []},
            "ta": {"initiative_score": 0.9, "emotional_explicitness": 0.9,
                   "signal_clarity": 0.9, "behaviors": []}}

    merged2 = merge_all_signals(old2, new2)
    assert merged2["user"]["initiative_score"] == 0.9
