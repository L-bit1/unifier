"""轻量向量检索：词袋 + 字符 bigram 余弦（无额外依赖）。"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable


_WORD = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{1,2}")


def tokenize(text: str) -> list[str]:
    raw = (text or "").lower()
    toks = _WORD.findall(raw)
    # 额外字符 bigram（中文更稳）
    compact = re.sub(r"\s+", "", raw)
    bigrams = [compact[i : i + 2] for i in range(max(0, len(compact) - 1))]
    return toks + bigrams


def embed(text: str) -> dict[str, float]:
    counts = Counter(tokenize(text))
    if not counts:
        return {}
    norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
    return {k: v / norm for k, v in counts.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def rank_by_vector(
    query: str,
    documents: Iterable[tuple[Any, str]],
    *,
    min_score: float = 0.08,
) -> list[tuple[Any, float]]:
    """documents: (item, haystack_text) → [(item, score)] 降序。"""
    qv = embed(query)
    if not qv:
        return [(doc, 0.0) for doc, _ in documents]
    scored: list[tuple[Any, float]] = []
    needle = query.strip().lower()
    for item, hay in documents:
        score = cosine(qv, embed(hay))
        if needle and needle in (hay or "").lower():
            score = max(score, 0.55) + 0.15  # 子串命中加权
        if score >= min_score or (needle and needle in (hay or "").lower()):
            scored.append((item, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
