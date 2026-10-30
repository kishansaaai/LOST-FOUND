"""Embedding generation (runs locally, no paid APIs).

  text : all-MiniLM-L6-v2  -> 384-d, L2-normalised
  image: CLIP clip-ViT-B-32 -> 512-d, L2-normalised (multiple photos are averaged)
"""
import hashlib
from typing import Protocol

import numpy as np
from PIL import Image

TEXT_MODEL = "all-MiniLM-L6-v2"
IMAGE_MODEL = "clip-ViT-B-32"
MODEL_LABEL = f"{TEXT_MODEL} | {IMAGE_MODEL}"


class Embedder(Protocol):
    def embed_text(self, texts: list[str]) -> np.ndarray: ...
    def embed_images(self, images: list[Image.Image]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    """Lazy-loading wrapper: models are loaded on first use and cached per process."""

    def __init__(self) -> None:
        self._text = None
        self._image = None

    def _load(self, name: str):
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(name, device="cpu")

    def embed_text(self, texts: list[str]) -> np.ndarray:
        if self._text is None:
            self._text = self._load(TEXT_MODEL)
        return np.asarray(self._text.encode(texts, normalize_embeddings=True, batch_size=64,
                                            show_progress_bar=False), dtype=np.float32)

    def embed_images(self, images: list[Image.Image]) -> np.ndarray:
        if self._image is None:
            self._image = self._load(IMAGE_MODEL)
        return np.asarray(self._image.encode(images, normalize_embeddings=True, batch_size=16,
                                             show_progress_bar=False), dtype=np.float32)


_default: Embedder | None = None


def get_embedder() -> Embedder:
    global _default
    if _default is None:
        _default = SentenceTransformerEmbedder()
    return _default


def set_embedder(e: Embedder | None) -> None:
    """Swap the embedder (tests inject a fast deterministic fake)."""
    global _default
    _default = e


def item_document(item: dict) -> str:
    """The text that represents an item to the text model."""
    parts = [item["title"], item["description"]]
    for key, label in (("category", "Category"), ("color", "Color"), ("brand", "Brand")):
        if item.get(key):
            v = str(item[key]).replace("_", " ")
            parts.append(f"{label}: {v}")
    return ". ".join(p.strip().rstrip(".") for p in parts) + "."


def content_hash(item: dict, image_digests: list[str]) -> str:
    h = hashlib.sha256()
    h.update(item_document(item).encode())
    for d in image_digests:
        h.update(d.encode())
    return h.hexdigest()


def mean_unit(vectors: np.ndarray) -> np.ndarray:
    m = vectors.mean(axis=0)
    return m / (np.linalg.norm(m) or 1.0)


def vec_literal(v: np.ndarray | None) -> str | None:
    """pgvector text input format; bound as a parameter and cast with ::vector."""
    return None if v is None else "[" + ",".join(f"{x:.7g}" for x in v.tolist()) + "]"
