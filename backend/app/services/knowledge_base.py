from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".json"}


class EmbeddingBackend:
    """可替换的向量化后端。

    默认实现：TF-IDF（无需任何外部模型，离线可用）。
    如需升级为语义向量检索，只需在子类中实现 `embed(texts)` 返回
    numpy 矩阵即可（例如调用 sentence-transformers / 远程 embedding 服务）。
    """

    def __init__(self) -> None:
        self._vectorizer = TfidfVectorizer(
            max_features=20000,
            ngram_range=(1, 2),
            stop_words="english",
            token_pattern=r"(?u)\b\w[\w\-]+\b",
        )
        self._fitted = False

    def fit(self, corpus: list[str]) -> None:
        if not corpus:
            return
        self._vectorizer.fit(corpus)
        self._fitted = True

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            self.fit(texts)
        matrix = self._vectorizer.transform(texts)
        return np.asarray(matrix.todense(), dtype=float)


class KnowledgeBase:
    """本地知识库：加载 markdown/txt/json，构建向量索引并提供检索。"""

    def __init__(self, root: Path | str, backend: EmbeddingBackend | None = None):
        self.root = Path(root)
        self.backend = backend or EmbeddingBackend()
        self.documents: list[dict[str, Any]] = []
        self._index_built = False

    # ------------------------------------------------------------------
    def _load_text(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return self._flatten_json(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to parse JSON %s: %s", path, exc)
                return ""
        return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _flatten_json(data: Any, prefix: str = "") -> str:
        lines: list[str] = []
        if isinstance(data, dict):
            for key, value in data.items():
                lines.append(f"{prefix}{key}:")
                lines.append(KnowledgeBase._flatten_json(value, prefix + "  "))
        elif isinstance(data, list):
            for item in data:
                lines.append(KnowledgeBase._flatten_json(item, prefix + "- "))
        else:
            lines.append(f"{prefix}{data}")
        return "\n".join(lines)

    def _collect_documents(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        if not self.root.exists():
            return docs
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                text = self._load_text(path)
                if text.strip():
                    relative = path.relative_to(self.root).as_posix()
                    docs.append(
                        {
                            "source": relative,
                            "path": str(path),
                            "text": text.strip(),
                        }
                    )
        return docs

    def build_index(self) -> None:
        self.documents = self._collect_documents()
        if not self.documents:
            self._index_built = True
            return
        corpus = [doc["text"] for doc in self.documents]
        self.backend.fit(corpus)
        self._embeddings = self.backend.embed(corpus)
        self._index_built = True

    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        segment_profile: str = "",
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        if not self._index_built:
            self.build_index()
        if not self.documents:
            return []

        # 融合业务问题与人群画像作为检索 query，提升相关性。
        combined_query = f"{query}\n{segment_profile}".strip()
        query_vec = self.backend.embed([combined_query])
        scores = cosine_similarity(query_vec, self._embeddings)[0]

        ranked = sorted(
            range(len(self.documents)),
            key=lambda idx: float(scores[idx]),
            reverse=True,
        )
        results: list[dict[str, Any]] = []
        for idx in ranked[:top_k]:
            results.append(
                {
                    "source": self.documents[idx]["source"],
                    "text": self.documents[idx]["text"],
                    "score": round(float(scores[idx]), 4),
                }
            )
        return results
