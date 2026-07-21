"""
  核心流程

  build_prompt(node_name, system_prompt, all_signals, claims_text, extra)
      │
      ├── 1. 组装 prompt
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


  函数签名

  def build_prompt(
      node_name: str,
      system_prompt: str,
      all_signals: dict | None = None,
      claims_text: str = "",
      extra: str = "",
  ) -> str:

  - node_name：查 MAX_TOKEN_MAP，拿预算值。不在 map 里的节点直接走快速路径，不估算不压缩。
  - system_prompt：已经 load_prompt() 好的模板内容
  - all_signals：完整 state，build_prompt 内部决定要不要压缩
  - claims_text：各节点自己格式化好的 claims 列表字符串（如 "#0 Claim: ...\n#1 Claim: ..."）
  - extra：各节点特有的附加指令（如 alternative 节点的 【只返回JSON...】）

  
  事例：
    prompt = build_prompt(
      node_name="evidence_node",
      system_prompt=load_prompt("evidence_prompt.md"),
      all_signals=state.get("all_signals"),
      claims_text=needed_claims,
      extra="请在返回值中给每个 claim 带上 \"claim_index\" 字段，值为对应编号（如 0, 1, ...）。",
  )

"""

import json
from tools.context.token_budget import MAX_TOKEN_MAP, estimate_token_count
from tools.context.compressor import compress_signals
from tools.logger import get_logger

log = get_logger()

def build_prompt(
    node_name: str,
    system_prompt: str,
    all_signals: dict | None = None,
    claims_text: str = "",
    extra: str = "",
    theory_context: str = "",
) -> str:
    """
    组装 prompt，并根据 token 预算决定是否压缩 all_signals。

    theory_context: 从 RAG 检索到的理论卡片文本，插在 system_prompt 之后、claims 之前。
    """
    # 1. 组装 prompt
    parts = [system_prompt]
    if theory_context:
        parts.append(theory_context)
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
        if theory_context:
            compressed_parts.append(theory_context)
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