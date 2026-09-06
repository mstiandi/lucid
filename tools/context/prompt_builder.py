"""
  核心流程

  build_prompt(node_name, system_prompt, all_signals, claims_text, extra, ...)
      │
      ├── 1. 组装 prompt（system + identity + theory + fact + claims + signals + extra）
      │
      ├── 2. estimate → ≤ budget → 直接 return
      │               >  budget → 进入第3步
      │
      ├── 3. compress_signals(all_signals, keep_recent=5)
      │       重拼 → estimate
      │       ≤ budget → return
      │       >  budget → 进入第4步
      │
      ├── 4. compress_signals(all_signals, keep_recent=0)  ← 激进：全部摘要化
      │       重拼 → estimate
      │       ≤ budget → return
      │       >  budget → 进入第5步
      │
      └── 5. 仍然超 → WARN 日志 + 返回当前 prompt
             这意味着 system_prompt + claims 本身就快超预算，
             应该增大 MAX_TOKEN_MAP 里该节点的值

  三个注入的 context（都插在 system_prompt 之后、claims 之前）：
  - identity_context: 静态画像（身份信息，来自 preprocess 提取）
  - theory_context:   RAG 检索的理论卡片（来自 theory_store）
  - fact_context:     记忆 fact 检索（来自 fact_retriever）
"""

import json
from tools.context.token_budget import MAX_TOKEN_MAP, estimate_token_count
from tools.context.compressor import compress_signals
from tools.logger import get_logger

log = get_logger()


def format_identity(identity: dict) -> str:
    """格式化身份画像为 prompt 文本。空画像返回空字符串。"""
    if not identity:
        return ""
    user = identity.get("user", {})
    ta = identity.get("ta", {})
    parts = []
    if user:
        parts.append("用户：" + "、".join(f"{k}={v}" for k, v in user.items()))
    if ta:
        parts.append("对方：" + "、".join(f"{k}={v}" for k, v in ta.items()))
    if not parts:
        return ""
    return "## 身份画像\n" + "\n".join(parts)


def build_prompt(
    node_name: str,
    system_prompt: str,
    all_signals: dict | None = None,
    claims_text: str = "",
    extra: str = "",
    theory_context: str = "",
    identity_context: str = "",
    fact_context: str = "",
) -> str:
    """
    组装 prompt，并根据 token 预算决定是否压缩 all_signals。
    """
    # 1. 组装 prompt
    parts = [system_prompt]
    if identity_context:
        parts.append(identity_context)
    if theory_context:
        parts.append(theory_context)
    if fact_context:
        parts.append(fact_context)
    if claims_text:
        parts.append(claims_text)
    if all_signals:
        parts.append("所有的信号如下:\n" + json.dumps(all_signals, ensure_ascii=False, indent=2))
    if extra:
        parts.append(extra)
    prompt = "\n\n".join(parts)

    # 2. 查预算
    max_token = MAX_TOKEN_MAP.get(node_name)
    if max_token is None:
        return prompt

    # 3. 估算 token 数量
    token_count = estimate_token_count(prompt)
    if token_count <= max_token:
        return prompt

    # 4. 压缩信号，先保留最近5条，再保留0条
    for keep_recent in [5, 0]:
        compressed_signals = compress_signals(all_signals, keep_recent=keep_recent)
        compressed_parts = [system_prompt]
        if identity_context:
            compressed_parts.append(identity_context)
        if theory_context:
            compressed_parts.append(theory_context)
        if fact_context:
            compressed_parts.append(fact_context)
        if claims_text:
            compressed_parts.append(claims_text)
        if compressed_signals:
            compressed_parts.append("所有的信号如下:\n" + json.dumps(compressed_signals, ensure_ascii=False, indent=2))
        if extra:
            compressed_parts.append(extra)
        compressed_prompt = "\n\n".join(compressed_parts)

        token_count = estimate_token_count(compressed_prompt)
        if token_count <= max_token:
            return compressed_prompt

    # 5. 超预算，返回当前 prompt 并记录 WARN 日志
    log.warn("PROMPT_BUILDER", f"{node_name} 超过 token 预算 {max_token}，当前估计 {token_count}")
    return prompt
