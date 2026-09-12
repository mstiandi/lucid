"""M2 记忆分层：中层 timeline 落地的冒烟测试。

验证 _load_timeline 的意图：summary 节点从 store 读「本会话最近 k 轮结论」注入，
补上 [-4:] 硬截断丢掉的长程脉络，且不同 thread 互不污染。
"""
import os
import time

# summary_node 模块 import 时经 chat_llm 读 DEEPSEEK_API_KEY，测试给占位 key。
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")

from tools.memory.sqlite_store import SqliteStore
from achievement_graph.thought_v1.nodes.summary_node import _load_timeline


def _put(store, tid, key, summary):
    store.put(("timeline", tid), key, {"summary": summary})


def test_load_timeline_returns_recent_summaries_old_to_new(tmp_path):
    """取最近 k 条，且按旧→新顺序输出（search 返回的是新→旧）。"""
    store = SqliteStore(str(tmp_path / "t.db"))
    _put(store, "tid1", "round_1", "第一轮结论")
    time.sleep(0.02)
    _put(store, "tid1", "round_2", "第二轮结论")
    time.sleep(0.02)
    _put(store, "tid1", "round_3", "第三轮结论")

    ctx = _load_timeline(store, "tid1", k=2)

    assert "第二轮结论" in ctx
    assert "第三轮结论" in ctx
    assert "第一轮结论" not in ctx  # 只取最近 k=2 条
    assert ctx.index("第二轮结论") < ctx.index("第三轮结论")  # 旧→新


def test_load_timeline_isolates_by_thread(tmp_path):
    """thread 隔离：本会话的脉络不混入别的会话。"""
    store = SqliteStore(str(tmp_path / "t.db"))
    _put(store, "tid1", "round_1", "我的会话结论")
    _put(store, "tid2", "round_1", "别人的会话结论")

    ctx = _load_timeline(store, "tid1", k=3)

    assert "我的会话结论" in ctx
    assert "别人的会话结论" not in ctx


def test_load_timeline_empty_when_no_store():
    """store 为空或缺失时安全降级为空字符串。"""
    assert _load_timeline(None, "tid1") == ""
