"""judge 双跑异步化的冒烟测试：证明 LLM 调用真并发（不是套 async 皮的假异步）。"""
import os

# judge → chat_llm 在 import 时读 DEEPSEEK_API_KEY；测试用假 LLM，这里给个占位 key 让 import 通过。
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")

import asyncio
import time

from tools.llm.safe_llm_call import safe_llm_call_async
from tools.eval.judge import judge_coverage


class _FakeAIMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class _FakeAsyncLLM:
    """假异步 LLM：ainvoke 睡 delay 秒后返回带 tool_calls 的 AIMessage，模拟等网络。"""

    def __init__(self, delay=0.1):
        self.delay = delay

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        # 真异步的关键：asyncio.sleep 让出，不是 time.sleep 阻塞
        await asyncio.sleep(self.delay)
        return _FakeAIMessage([{
            "name": "coverage_return",
            "args": {"covered_count": 3, "missed_count": 1, "comment": "ok"},
            "id": "call-1",
            "type": "tool_call",
        }])


def test_safe_llm_call_async_is_truly_async():
    """两个 safe_llm_call_async 用 gather 并发，耗时 ≈ 单次（0.1s），不是相加（0.2s）。"""
    fake = _FakeAsyncLLM(delay=0.1)

    async def run():
        t0 = time.perf_counter()
        r1, r2 = await asyncio.gather(
            safe_llm_call_async(fake, [], [], node_name="TEST"),
            safe_llm_call_async(fake, [], [], node_name="TEST"),
        )
        return time.perf_counter() - t0, r1, r2

    elapsed, r1, r2 = asyncio.run(run())

    assert r1.tool_calls and r2.tool_calls
    assert elapsed < 0.18, f"双跑耗时 {elapsed:.2f}s，疑似顺序执行（假异步）"


def _scenario():
    return {
        "description": "用户场景",
        "ground_truth": {"expected_direction": "期望方向"},
    }


def test_judge_coverage_double_run_is_concurrent():
    """judge_coverage 的双跑是 asyncio.gather 并发：两次 0.1s 重叠 ≈ 0.1s，不是 0.2s。"""
    fake = _FakeAsyncLLM(delay=0.1)

    t0 = time.perf_counter()
    out = asyncio.run(judge_coverage(_scenario(), {}, llm=fake))
    elapsed = time.perf_counter() - t0

    assert out["score"] is not None
    assert elapsed < 0.18, f"judge 双跑耗时 {elapsed:.2f}s，疑似顺序执行"
