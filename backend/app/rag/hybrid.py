"""Reciprocal Rank Fusion for combining ranked retrieval lists.

Pure-function combiner: given two ranked lists (e.g. vector + keyword),
returns a single ranking via the RRF formula:

    score(d) = sum over each list L of: weight_L / (k_constant + rank_L(d))

Cormack et al. 2009 use k_constant=60 and equal weights as the
literature-standard defaults; both are exposed for tuning. Only RANK
is used from the input lists — input scores are ignored.
"""

from __future__ import annotations


def reciprocal_rank_fusion(
    vector_results: list[tuple[int, float]],
    keyword_results: list[tuple[int, float]],
    k_constant: int = 60,
    vector_weight: float = 1.0,
    keyword_weight: float = 1.0,
) -> list[tuple[int, float]]:
    """Combine two ranked lists into a single ranking via RRF.

    Args:
        vector_results: (id, vector_score) tuples, sorted by score desc.
        keyword_results: (id, keyword_score) tuples, sorted by score desc.
        k_constant: RRF damping constant. 60 is the literature standard.
        vector_weight: Multiplier on the vector contribution.
        keyword_weight: Multiplier on the keyword contribution.

    Returns:
        List of (id, rrf_score) sorted by rrf_score desc. IDs that
        appear in BOTH input lists naturally rank higher than IDs in
        only one.

    Notes:
        - Raw RRF scores are small (typically < 0.05). Don't compare to
          cosine similarity values.
        - Input scores are unused; only rank position matters.
    """
    vector_ranks = {id_: i + 1 for i, (id_, _) in enumerate(vector_results)}
    keyword_ranks = {id_: i + 1 for i, (id_, _) in enumerate(keyword_results)}

    rrf_scores: dict[int, float] = {}
    for id_ in set(vector_ranks) | set(keyword_ranks):
        score = 0.0
        if id_ in vector_ranks:
            score += vector_weight * (1.0 / (k_constant + vector_ranks[id_]))
        if id_ in keyword_ranks:
            score += keyword_weight * (1.0 / (k_constant + keyword_ranks[id_]))
        rrf_scores[id_] = score

    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
