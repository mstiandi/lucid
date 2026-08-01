"""
Phase 0: 追 alternative 全空黄旗
单独喂一条明显该反驳的 claim, 验证节点是过度保守还是代码 bug

运行: cd D:\my_joker && python test_alternative.py
"""
import sys
import os
import io

# 强制 stdout 用 utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

from tools.llm.chat_llm import llm
from tools.loader.load_prompts import load_prompt
from langchain.tools import tool
from langchain.messages import SystemMessage


@tool
def alternative_explanation_return(all_claims: list[dict]) -> dict:
    """与 alternative_explanation_node.py 中的完全一致"""
    return {"all_claims": all_claims}


def run_test(case_name: str, claims: list[dict], all_signals: dict):
    """跑一次测试，打印完整的 LLM 调用和返回"""
    print(f"\n{'='*60}")
    print(f"[TEST] {case_name}")
    print(f"{'='*60}")

    needed_claims = "\n".join([f"Claim: {c['content']}" for c in claims])
    prompt = load_prompt("alternative_explanation_prompt.md") + \
             "\n所有status为pending的待验证的claims如下:\n" + needed_claims + \
             "\n所有的信号如下:\n" + str(all_signals)

    print(f"\n[PROMPT] length={len(prompt)} chars")
    print(f"[INPUT] claims={needed_claims}")
    u_behaviors = len(all_signals.get('user',{}).get('behaviors',[]))
    t_behaviors = len(all_signals.get('ta',{}).get('behaviors',[]))
    print(f"[INPUT] signals: user_behaviors={u_behaviors}, ta_behaviors={t_behaviors}")

    response = llm.bind_tools([alternative_explanation_return]).invoke(
        [SystemMessage(content=prompt)])

    print(f"\n[LLM RESPONSE]")
    content_preview = (response.content or '')[:200]
    print(f"   content: {content_preview}")
    print(f"   tool_calls count: {len(response.tool_calls) if response.tool_calls else 0}")

    if not response.tool_calls:
        print(f"\n[RESULT] NO tool_calls -> LLM chose not to call tool -> node returns {{}}")
        print(f"   This means LLM thinks no claim needs alternative explanation.")
        return None

    for i, tc in enumerate(response.tool_calls):
        print(f"\n   tool_call[{i}]:")
        print(f"     name: {tc.get('name')}")
        args = tc.get("args", {})
        updated_claims = args.get("all_claims", [])
        print(f"     all_claims count: {len(updated_claims)}")
        for j, c in enumerate(updated_claims):
            alts = c.get("alternative_explanations", {})
            print(f"     claim[{j}] content={c.get('content','?')}")
            print(f"            alternative_explanations count: {len(alts)}")
            if alts:
                for sig_key, alt_val in alts.items():
                    print(f"            signal: {sig_key[:100]}")
                    print(f"              youthink: {alt_val.get('youthink', '?')[:100]}")
                    print(f"              alternative: {alt_val.get('alternative', '?')[:100]}")

    tool_call = response.tool_calls[0]
    args = tool_call["args"]
    updated_claims = args.get("all_claims", [])
    total_alts = sum(len(c.get("alternative_explanations", {})) for c in updated_claims)

    if total_alts == 0:
        print(f"\n[RESULT] FAIL: tool_call exists but all alternative_explanations are EMPTY!")
    else:
        print(f"\n[RESULT] OK: produced {total_alts} alternative explanation(s)")

    return response


# ====== 测试数据 ======

# 测试1: prompt 里的示例 case
test1_claims = [
    {
        "content": "我认为她并不喜欢我",
        "direction": "single",
        "analysed_by": [],
        "status": "pending",
        "evidence_from_signals": {},
        "alternative_explanations": {}
    }
]

test1_signals = {
    "user": {
        "initiative_score": 0.8,
        "signal_clarity": 0.3,
        "emotional_explicitness": 0.5,
        "behaviors": [
            {
                "action": "每天都主动给她发早安晚安",
                "signal_type": "日常关心",
                "confidence": 1.0,
                "source_ref": "我每天都会给她发早安和晚安，坚持了三个月"
            },
            {
                "action": "邀请她一起去图书馆自习",
                "signal_type": "学习邀约",
                "confidence": 1.0,
                "source_ref": "上周我约她一起去图书馆，她说最近在准备考试没空"
            }
        ]
    },
    "ta": {
        "initiative_score": 0.2,
        "signal_clarity": 0.5,
        "emotional_explicitness": 0.3,
        "behaviors": [
            {
                "action": "回复消息很慢，有时隔天才回",
                "signal_type": "低频回复",
                "confidence": 1.0,
                "source_ref": "她经常隔很久才回我消息，有时候要等一整天"
            },
            {
                "action": "拒绝了一起去图书馆的邀约",
                "signal_type": "拒绝邀约",
                "confidence": 1.0,
                "source_ref": "上周我约她一起去图书馆，她说最近在准备考试没空"
            },
            {
                "action": "考试周主动找我问了一道题",
                "signal_type": "主动联系",
                "confidence": 1.0,
                "source_ref": "但是她考试前主动发微信问我一道高数题怎么解"
            }
        ]
    }
}

# 测试2: 极端明显 case - 拒绝表白但后续行为说明不是讨厌
test2_claims = [
    {
        "content": "她肯定讨厌我，因为她当面拒绝了我的表白",
        "direction": "single",
        "analysed_by": [],
        "status": "pending",
        "evidence_from_signals": {},
        "alternative_explanations": {}
    }
]

test2_signals = {
    "user": {
        "initiative_score": 0.9,
        "signal_clarity": 0.8,
        "emotional_explicitness": 0.9,
        "behaviors": [
            {
                "action": "当面表白",
                "signal_type": "直接表白",
                "confidence": 1.0,
                "source_ref": "昨天晚上我当面跟她说我喜欢她，想和她在一起"
            }
        ]
    },
    "ta": {
        "initiative_score": 0.3,
        "signal_clarity": 0.6,
        "emotional_explicitness": 0.7,
        "behaviors": [
            {
                "action": "当面拒绝了表白",
                "signal_type": "拒绝表白",
                "confidence": 1.0,
                "source_ref": "她说她现在不想谈恋爱，不是因为我的问题"
            },
            {
                "action": "拒绝后主动发消息安慰",
                "signal_type": "主动联系",
                "confidence": 1.0,
                "source_ref": "拒绝之后她还主动发消息说你人很好只是我现在状态不适合谈恋爱"
            },
            {
                "action": "之后仍然一起吃饭",
                "signal_type": "维持关系",
                "confidence": 0.9,
                "source_ref": "第二天中午她还像往常一样叫我一起去食堂吃饭"
            }
        ]
    }
}


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 0: 追 alternative 全空黄旗")
    print("=" * 60)

    run_test("prompt示例复现 (prompt里自己的例子)", test1_claims, test1_signals)
    run_test("极端明显: 拒绝表白 vs 讨厌 (还有安慰+继续约饭)", test2_claims, test2_signals)

    print(f"\n{'='*60}")
    print("测试结论:")
    print("- 两个都 0 alternative -> prompt '不能就跳过' 太保守, 需改 prompt")
    print("- 测试1是0但测试2有 -> prompt 不够激进, 需降低跳过门槛")
    print("- 两个都有 -> v1 真实数据的 claim 可能确实没好的反驳角度")
    print("=" * 60)
