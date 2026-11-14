"""Score retrieved chunks against gold evidence and aggregate Hit@1 / Evidence Hit@3.

A retrieved chunk is a hit when, for the primary gold or any documented alt_gold:
  - its source_id equals the gold source,
  - the gold page lies within [page, page_end] of the chunk, and
  - the whole evidence quote is contained in the chunk text
    (compared after normalization with ALL whitespace removed, the benchmark's
    evidence_match_rule, because the PDFs insert spaces inside syllables).
Grounding and coherence are NOT inferred here; they are labelled by hand.
"""
from collections import defaultdict
from typing import Any

from .ingestion import squash


def _golds(q: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"source_id": q["gold_source_id"], "page": q["gold_page"],
             "evidence_quote": q["evidence_quote"]}] + list(q.get("alt_gold", []))


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    golds = [(g["source_id"], g["page"], squash(g["evidence_quote"])) for g in _golds(question)]
    flt = question.get("filter") or {}
    ranked = []
    for rank, h in enumerate(hits, 1):
        text = squash(h["text"])
        on_page = [g for g in golds if g[0] == h["source_id"] and h["page"] <= g[1] <= h["page_end"]]
        full = [g for g in on_page if g[2] in text]
        # evidence really split: the chunk holds the first or last 25 chars of the quote, not all of it
        split = [g for g in on_page if g[2] not in text and (g[2][:25] in text or g[2][-25:] in text)]
        meta = dict(h["metadata"], document_id=h["document_id"], source_id=h["source_id"])
        ranked.append({
            "rank": rank, "chunk_id": h["chunk_id"], "score": round(h["score"], 5),
            "document_id": h["document_id"], "source_id": h["source_id"],
            "page": h["page"], "page_end": h["page_end"],
            "article": meta.get("article"), "year": meta.get("year"),
            "is_hit": bool(full),
            "same_page_other_chunk": bool(on_page) and not full,
            "partial_evidence": bool(split) and not full,   # quote cut across chunk boundary
            "matches_filter": all(meta.get(k) == v for k, v in flt.items()) if flt else None,
            "text": h["text"],
        })
    first = next((r["rank"] for r in ranked if r["is_hit"]), None)
    return {
        "id": question["id"], "split": question["split"], "type": question["type"],
        "question": question["question"], "filter": flt or None,
        "gold": _golds(question), "expected_answer": question["expected_answer"],
        "hit1": first == 1, "hit3": first is not None and first <= 3, "first_hit_rank": first,
        "partial_in_top3": any(r["partial_evidence"] for r in ranked),
        # only meaningful for questions that carry a filter
        "top3_all_match_filter": all(r["matches_filter"] for r in ranked) if flt else None,
        "hits": ranked,
    }


def _rate(n: int, d: int) -> dict[str, Any]:
    return {"n": n, "of": d, "rate": round(n / d, 4) if d else None}


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Per strategy x split: Hit@1, Hit@3 (as numerator/denominator), plus breakdowns."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in traces:
        groups[(t["strategy"], t["split"])].append(t)
    out: dict[str, Any] = defaultdict(dict)
    for (strategy, split), ts in sorted(groups.items()):
        filt = [t for t in ts if t["filter"]]
        by_type = defaultdict(list)
        for t in ts:
            by_type[t["type"]].append(t)
        out[strategy][split] = {
            "hit1": _rate(sum(t["hit1"] for t in ts), len(ts)),
            "hit3": _rate(sum(t["hit3"] for t in ts), len(ts)),
            "filter_questions_hit3": _rate(sum(t["hit3"] for t in filt), len(filt)),
            "filter_compliance_top3": _rate(sum(bool(t["top3_all_match_filter"]) for t in filt), len(filt)),
            "partial_evidence_in_top3": sum(t["partial_in_top3"] for t in ts),
            "hit3_by_type": {k: _rate(sum(t["hit3"] for t in v), len(v)) for k, v in sorted(by_type.items())},
        }
    return dict(out)
