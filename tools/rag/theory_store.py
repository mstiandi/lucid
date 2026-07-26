"""
BGE embedding + numpy 检索。10-50 张卡片用 numpy 算余弦相似度足够，零外部向量数据库。

嵌入字段：name + category + core_idea + signals_to_look_for
不嵌入：  common_misinterpretations（区分/否定语义会污染向量方向）
"""

import csv
import os

import numpy as np
from sentence_transformers import SentenceTransformer


def _build_search_text(card: dict) -> str:
    """拼接用于 embedding 的字段。"""
    return " ".join([
        card.get("name", ""),
        card.get("category", ""),
        card.get("core_idea", ""),
        card.get("signals_to_look_for", ""),
    ])


class TheoryStore:
    """心理学理论卡片向量存储。numpy 实现，零外部向量数据库。"""

    def __init__(
        self,
        csv_path: str | None = None,
        model_name: str = "BAAI/bge-base-zh-v1.5",
    ):
        if csv_path is None:
            csv_path = os.path.join(os.path.dirname(__file__), "theory_cards.csv")

        self.csv_path = csv_path
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

        # 索引状态
        self._cards: list[dict] = []
        self._embeddings: np.ndarray | None = None  # shape: (n_cards, dim), L2-normalized

    @property
    def model(self) -> SentenceTransformer:
        """懒加载 embedding 模型。优先本地缓存，未缓存则自动下载。"""
        if self._model is None:
            model_path = self._resolve_model_path()
            self._model = SentenceTransformer(model_path)
        return self._model

    def _resolve_model_path(self) -> str:
        """定位模型路径：本地缓存 → 自动下载 → 返回绝对路径。"""
        from pathlib import Path
        hub_cache = Path(
            os.environ.get("HF_HOME",
                           os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))
        )
        model_dir = hub_cache / "models--BAAI--bge-base-zh-v1.5"
        snapshots_dir = model_dir / "snapshots"

        # 尝试从本地缓存加载
        if snapshots_dir.exists():
            snapshots = sorted(snapshots_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for snap in snapshots:
                if (snap / "config.json").exists():
                    return str(snap)

        # 本地无缓存 → 下载
        from huggingface_hub import snapshot_download
        return snapshot_download(self._model_name)

    # ─── 索引 ──────────────────────────────────────────

    def is_indexed(self) -> bool:
        return self._embeddings is not None and len(self._embeddings) > 0

    def ensure_indexed(self, force: bool = False) -> int:
        """
        加载 CSV 并向量化。幂等：已索引且不 force → 跳过。
        返回卡片数量。
        """
        if self.is_indexed() and not force:
            return len(self._cards)

        self._cards = self._load_cards()
        if not self._cards:
            return 0

        search_texts = [_build_search_text(c) for c in self._cards]
        self._embeddings = self.model.encode(
            search_texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return len(self._cards)

    # ─── 检索 ──────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """
        语义检索 top_k 张理论卡片。
        返回完整卡片 dict 列表，按相似度降序排列。
        """
        if not self.is_indexed():
            self.ensure_indexed()

        query_emb = self.model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )  # shape: (1, dim)

        # 余弦相似度 = 归一化向量的点积
        scores = np.dot(self._embeddings, query_emb.T).flatten()  # shape: (n_cards,)
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [dict(self._cards[i]) for i in top_indices]

    # ─── 内部 ──────────────────────────────────────────

    def _load_cards(self) -> list[dict]:
        """从 CSV 读取卡片。"""
        cards = []
        with open(self.csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cleaned = {k.strip(): v.strip() for k, v in row.items()}
                if cleaned.get("id") and cleaned.get("name"):
                    cards.append(cleaned)
        return cards
