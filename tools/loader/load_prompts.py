import os
def load_prompt(filename: str) -> str:
    """从 prompts 目录加载 prompt 文件"""
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
    with open(os.path.join(prompts_dir, filename), "r", encoding="utf-8") as f:
        return f.read().strip()