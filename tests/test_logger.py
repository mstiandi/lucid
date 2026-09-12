"""结构化日志的冒烟测试：验证 run_id 关联 + JSONL 字段。"""
import json

import pytest

from tools.logger import get_logger, get_run_id, reset_logger, set_run_id


@pytest.fixture(autouse=True)
def _clean_logger():
    """每个测试前后重置 logger 单例和 run_id，避免相互污染。"""
    reset_logger()
    set_run_id(None)
    yield
    reset_logger()
    set_run_id(None)


def test_set_and_get_run_id():
    set_run_id("run-abc")
    assert get_run_id() == "run-abc"
    set_run_id(None)
    assert get_run_id() is None


def test_logger_writes_jsonl_with_run_id(tmp_path):
    log = get_logger(log_dir=tmp_path)
    set_run_id("run-123")
    log.info("EVIDENCE", "LLM调用", attempt=1, input_tokens=18432)
    set_run_id(None)

    lines = log.log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1, "应恰好写一条日志"

    entry = json.loads(lines[0])
    assert entry["run_id"] == "run-123"
    assert entry["node"] == "EVIDENCE"
    assert entry["msg"] == "LLM调用"
    assert entry["level"] == "INFO"
    assert entry["data"] == {"attempt": 1, "input_tokens": 18432}


def test_run_id_isolation_between_contexts(tmp_path):
    """同一个 logger，不同 run_id 各自写入自己的关联字段。"""
    log = get_logger(log_dir=tmp_path)

    set_run_id("run-A")
    log.info("PREPROCESS", "进入")
    set_run_id("run-B")
    log.info("PREPROCESS", "进入")
    set_run_id(None)

    lines = log.log_file.read_text(encoding="utf-8").strip().splitlines()
    run_ids = [json.loads(l)["run_id"] for l in lines]
    assert run_ids == ["run-A", "run-B"]


def test_run_id_propagates_through_langgraph(tmp_path):
    """run_id 穿透 LangGraph 节点执行——同一轮所有节点日志带同一个 run_id。

    这是「日志能复述一次完整调用链」的机制验证：contextvar 在 async 上下文里
    set_run_id 后，被 LangGraph ainvoke 执行的同步节点日志仍能读到它。
    """
    import asyncio

    from langgraph.graph import StateGraph

    log = get_logger(log_dir=tmp_path)

    def node_a(state):
        get_logger().info("A", "进入")
        return {}

    def node_b(state):
        get_logger().info("B", "进入")
        return {}

    g = StateGraph(dict)
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge("__start__", "a")
    g.add_edge("a", "b")
    g.add_edge("b", "__end__")
    app = g.compile()

    async def main():
        set_run_id("prop-test")
        await app.ainvoke({})
        set_run_id(None)

    asyncio.run(main())

    entries = [json.loads(l) for l in log.log_file.read_text(encoding="utf-8").strip().splitlines()]
    assert [e["node"] for e in entries] == ["A", "B"]
    assert all(e["run_id"] == "prop-test" for e in entries)
