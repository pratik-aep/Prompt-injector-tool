"""Fingerprints, similarity, and diversity selection for candidate prompts."""
from __future__ import annotations

import hashlib
import re

_WORD = re.compile(r"[a-z0-9']+")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()[:24]


def tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def shingles(text: str, n: int = 3) -> set[str]:
    w = _WORD.findall(text.lower())
    if len(w) < n:
        return {" ".join(w)} if w else set()
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def similarity(a: str, b: str) -> float:
    """Blend of word-set and 3-gram Jaccard in [0, 1]; 1.0 means effectively identical."""
    ta, tb = tokens(a), tokens(b)
    sa, sb = shingles(a), shingles(b)
    j1 = len(ta & tb) / len(ta | tb) if ta | tb else 1.0
    j2 = len(sa & sb) / len(sa | sb) if sa | sb else 1.0
    return 0.5 * j1 + 0.5 * j2


def novelty(text: str, archive: list[str]) -> float:
    return 1.0 if not archive else 1.0 - max(similarity(text, a) for a in archive)


def is_near_duplicate(text: str, others: list[str], threshold: float = 0.85) -> bool:
    fp = fingerprint(text)
    return any(fingerprint(o) == fp or similarity(text, o) >= threshold for o in others)


def dedupe(texts: list[str], threshold: float = 0.85, existing: list[str] | None = None) -> list[int]:
    """Indexes of ``texts`` to keep (first occurrence wins), also vs ``existing``."""
    kept: list[int] = []
    pool = list(existing or [])
    for i, t in enumerate(texts):
        if not is_near_duplicate(t, pool, threshold):
            kept.append(i)
            pool.append(t)
    return kept


def diverse_subset(texts: list[str], k: int) -> list[int]:
    """Greedy max-min selection of ``k`` mutually dissimilar texts (indexes)."""
    if len(texts) <= k:
        return list(range(len(texts)))
    chosen = [0]
    while len(chosen) < k:
        best, best_d = None, -1.0
        for i in range(len(texts)):
            if i in chosen:
                continue
            d = min(1.0 - similarity(texts[i], texts[j]) for j in chosen)
            if d > best_d:
                best, best_d = i, d
        chosen.append(best)  # type: ignore[arg-type]
    return sorted(chosen)
