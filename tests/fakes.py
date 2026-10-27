"""Fast deterministic stand-ins for the ML models (the real ones are exercised by the seed
and by tests/test_real_models.py). The text fake is a hashed bag-of-words, so descriptions
that share words are genuinely similar; the image fake is a tiny colour thumbnail."""
import hashlib
import re

import numpy as np


def _bucket(word: str, dim: int) -> int:
    return int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "little") % dim


class FakeEmbedder:
    def embed_text(self, texts):
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for n, t in enumerate(texts):
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                out[n, _bucket(w, 384)] += 1.0
            norm = np.linalg.norm(out[n])
            if norm:
                out[n] /= norm
        return out

    def embed_images(self, images):
        out = np.zeros((len(images), 512), dtype=np.float32)
        for n, im in enumerate(images):
            small = np.asarray(im.convert("RGB").resize((8, 8)), dtype=np.float32).ravel() / 255.0
            out[n, : small.size] = small
            out[n] /= np.linalg.norm(out[n]) or 1.0
        return out
