"""Step 3: read + normalize the corpus and export chunks for strategies A and B.

Run from starter/:  python -m src.build_chunks
Outputs (results/):
  ingest_errors.log        skipped pages (empty / excluded / extraction errors)
  chunks_A.jsonl           fixed-size chunks
  chunks_B.jsonl           article-aware chunks (strategy C reuses these + filters)
  chunk_stats.json         counts, length distribution, evidence-split check on DEV
"""
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from .chunking import by_article, fixed_size
from .ingestion import ROOT, load_corpus, squash

RESULTS = ROOT / "results"
BENCHMARK = ROOT / "benchmark" / "questions.json"

# Chunking parameters, fixed before looking at retrieval results.
STRATEGIES = {
    "A": {"chunker": "fixed_size", "size": 800, "overlap": 100},
    "B": {"chunker": "by_article", "max_size": 1500},
}


def build(pages_by_source, cfg):
    chunks = []
    for pages in pages_by_source.values():
        if cfg["chunker"] == "fixed_size":
            chunks += fixed_size(pages, cfg["size"], cfg["overlap"])
        else:
            chunks += by_article(pages, cfg["max_size"])
    return chunks


def evidence_coverage(chunks, questions):
    """How many DEV gold quotes sit entirely inside one chunk (any valid gold)?

    Dev only, so test gold is not used to tune chunking. A miss means the evidence
    is split across chunks, so Evidence Hit@3 can never succeed for that question.
    """
    index = [(c.metadata["source_id"], c.page, c.metadata["page_end"], squash(c.text)) for c in chunks]
    whole, split_ids = 0, []
    for q in questions:
        golds = [(q["gold_source_id"], q["gold_page"], q["evidence_quote"])]
        golds += [(g["source_id"], g["page"], g["evidence_quote"]) for g in q.get("alt_gold", [])]
        ok = any(src == gs and p0 <= gp <= p1 and squash(quote) in text
                 for gs, gp, quote in golds for src, p0, p1, text in index)
        whole += ok
        if not ok:
            split_ids.append(q["id"])
    return {"dev_questions": len(questions), "evidence_in_one_chunk": whole,
            "evidence_split_ids": split_ids}


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    corpus, errors = load_corpus()
    load_s = time.perf_counter() - t0
    (RESULTS / "ingest_errors.log").write_text("\n".join(errors) + "\n", encoding="utf-8")
    n_pages = sum(len(p) for p in corpus.values())
    print(f"Đọc {n_pages} trang từ {len(corpus)} file trong {load_s:.1f}s; "
          f"{len(errors)} trang bỏ qua (xem results/ingest_errors.log)")

    dev = [q for q in json.loads(BENCHMARK.read_text(encoding="utf-8"))["questions"]
           if q["split"] == "dev"]
    stats = {"pages_indexed": n_pages, "pages_skipped": len(errors), "load_seconds": round(load_s, 2)}
    for name, cfg in STRATEGIES.items():
        t0 = time.perf_counter()
        chunks = build(corpus, cfg)
        secs = time.perf_counter() - t0
        with open(RESULTS / f"chunks_{name}.jsonl", "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
        lens = sorted(len(c.text) for c in chunks)
        limit = cfg.get("max_size", cfg.get("size"))
        stats[name] = {
            "params": cfg, "chunks": len(chunks), "total_chars": sum(lens),
            "len_min": lens[0], "len_median": statistics.median(lens),
            "len_p90": lens[int(0.9 * (len(lens) - 1))], "len_max": lens[-1],
            "over_limit": sum(l > limit for l in lens),
            "cross_page_chunks": sum(c.page != c.metadata["page_end"] for c in chunks),
            "without_article": sum(c.metadata["article"] is None for c in chunks),
            "chunk_seconds": round(secs, 3),
            **evidence_coverage(chunks, dev),
        }
        s = stats[name]
        print(f"[{name}] {s['chunks']} chunk | độ dài min/median/p90/max = "
              f"{s['len_min']}/{s['len_median']}/{s['len_p90']}/{s['len_max']} | "
              f"vượt giới hạn: {s['over_limit']} | evidence dev nằm trọn 1 chunk: "
              f"{s['evidence_in_one_chunk']}/{s['dev_questions']}")
    (RESULTS / "chunk_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    print("Đã ghi results/chunks_A.jsonl, results/chunks_B.jsonl, results/chunk_stats.json")


if __name__ == "__main__":
    main()
