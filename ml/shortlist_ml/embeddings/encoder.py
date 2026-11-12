"""Text encoders. The real model is bge-small-en-v1.5 (ADR 0012); a hashing fake is used in tests/CI."""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Any, Protocol

from shortlist_ml.config import Settings
from shortlist_ml.db.types import EMBEDDING_DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"
# bge's documented instruction for QUERIES (documents are encoded without it).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Encoder(Protocol):
    name: str
    dim: int

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]: ...


class MissingMLDependencies(RuntimeError):
    """Raised when the real encoder is requested but the optional `ml` group is not installed."""


def resolve_device(requested: str = "auto") -> str:
    """auto -> mps (Apple GPU) if available, else cuda, else cpu."""
    if requested != "auto":
        return requested
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


class SentenceTransformerEncoder:
    dim = EMBEDDING_DIM

    def __init__(
        self, model_name: str = MODEL_NAME, device: str = "auto", batch_size: int = 32
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised only without the ml group
            raise MissingMLDependencies(
                "Install the ML dependencies first: make install-ml"
            ) from exc
        self.name = model_name
        self.device = resolve_device(device)
        self.batch_size = batch_size
        self._model: Any = SentenceTransformer(model_name, device=self.device)
        self._model.max_seq_length = 512

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vecs = self._model.encode(
            list(texts), batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True,
            show_progress_bar=False,
        )  # fmt: skip
        return [[float(x) for x in v] for v in vecs]

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts)

    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode([QUERY_PREFIX + t for t in texts])


class HashingEncoder:
    """Deterministic bag-of-words hashing encoder. NOT a semantic model: texts that share words are
    similar, nothing more. Exists so tests and CI exercise the whole pipeline with no model download."""

    name = "fake-hashing-384"
    dim = EMBEDDING_DIM

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9+#.]+", text.lower()):
            h = hashlib.md5(tok.encode(), usedforsecurity=False).digest()
            idx = int.from_bytes(h[:4], "big") % self.dim
            vec[idx] += 1.0 if h[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]


def get_encoder(settings: Settings) -> Encoder:
    if settings.embedding_backend == "fake":
        return HashingEncoder()
    if settings.embedding_backend == "real":
        return SentenceTransformerEncoder(
            device=settings.embedding_device, batch_size=settings.embedding_batch_size
        )
    raise ValueError(f"unknown embedding_backend {settings.embedding_backend!r}")
