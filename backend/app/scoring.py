"""Human-facing match confidence.

RRF is a RANK fusion: it says which candidate is best among the others, not how similar
it is in absolute terms (rank 1 of a weak pool still gets the maximum RRF). So users see a
confidence derived from the real cosine similarities: how far the best signal sits above the
similarity floor used to accept a candidate at all."""
from .config import get_settings


def confidence(text_score: float | None, image_score: float | None) -> float:
    s = get_settings()
    parts = []
    if text_score is not None:
        parts.append((text_score - s.match_min_text) / (1 - s.match_min_text))
    if image_score is not None:
        parts.append((image_score - s.match_min_image) / (1 - s.match_min_image))
    return round(max(0.0, min(1.0, max(parts))) if parts else 0.0, 3)
