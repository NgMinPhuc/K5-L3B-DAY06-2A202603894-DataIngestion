"""Step 5: run the benchmark for strategies A, B, C and prepare manual-audit sheets.

Run from starter/ (after `python -m src.ingest`):  python -m src.run
Outputs:
  results/trace_{A,B,C}.jsonl          full top-3 trace per question
  results/metrics.json                 Hit@1 / Hit@3 (n/of) by strategy x split + breakdowns
  results/audit_metadata.csv           5 test q x top-3 x strategy -> label metadata by hand
  results/audit_grounding.csv          5 test q x strategy        -> label grounding 0-2 by hand
  results/audit_coherence.csv          10 positions x A/B          -> label coherence 0-2 by hand
  ../artifacts/experiment_log.csv      configs, hypotheses, dev/test hits
"""
import csv
import json
import time

from .build_chunks import STRATEGIES as CHUNK_PARAMS
from .config import (AUDIT_TEST_QUESTIONS, COHERENCE_POSITIONS, DATABASE_URL, HYPOTHESES,
                     MODEL_PRICE_PER_1M, RESULTS, ROOT, SELECTION_RULE, STRATEGIES, TOP_K)
from .embeddings import OpenAIEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_corpus, squash
from .store import PgVectorStore

BENCHMARK = ROOT / "benchmark" / "questions.json"
EXPERIMENT_LOG = ROOT.parent / "artifacts" / "experiment_log.csv"


def fmt(r):
    return f"{r['n']}/{r['of']} ({r['rate']:.1%})" if r["of"] else "N/A"


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:   # BOM so Excel shows Vietnamese
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def audit_sheets(traces_by_strategy, questions):
    test_ids = sorted(q["id"] for q in questions if q["split"] == "test")[:AUDIT_TEST_QUESTIONS]
    meta_rows, ground_rows = [], []
    for s, traces in traces_by_strategy.items():
        for t in (t for t in traces if t["id"] in test_ids):
            for h in t["hits"]:
                meta_rows.append([s, t["id"], h["rank"], t["filter"] and json.dumps(t["filter"]),
                                  h["chunk_id"], h["document_id"], h["source_id"], h["page"],
                                  h["page_end"], h["year"], h["article"], h["text"], "", "", ""])
            ground_rows.append([s, t["id"], t["question"], t["expected_answer"],
                                "\n\n".join(f"#{h['rank']} [{h['source_id']} tr.{h['page']}-{h['page_end']}"
                                            f" {h['article']}]\n{h['text']}" for h in t["hits"]),
                                int(t["hit3"]), "", ""])
    write_csv(RESULTS / "audit_metadata.csv",
              ["strategy", "qid", "rank", "question_filter", "chunk_id", "document_id", "source_id",
               "page", "page_end", "year", "article", "chunk_text",
               "metadata_du_va_dung(0/1)", "filter_ok(0/1/NA)", "ghi_chu_loi"], meta_rows)
    write_csv(RESULTS / "audit_grounding.csv",
              ["strategy", "qid", "question", "expected_answer", "top3", "auto_hit3",
               "grounding(0-2)", "ly_do"], ground_rows)
    return test_ids


def coherence_sheet():
    """Same 10 source positions for every strategy (C shares B's chunks)."""
    corpus, _ = load_corpus()
    pages = [p for src in corpus.values() for p in src]
    step = len(pages) / COHERENCE_POSITIONS
    picks = [pages[int(i * step + step / 2)] for i in range(COHERENCE_POSITIONS)]
    chunks = {k: [json.loads(l) for l in (RESULTS / f"chunks_{k}.jsonl").read_text(encoding="utf-8").splitlines()]
              for k in ("A", "B")}
    rows = []
    for i, p in enumerate(picks, 1):
        flat = squash(p.text)
        anchor = flat[len(flat) // 2: len(flat) // 2 + 60]
        for k, cs in chunks.items():
            c = next((c for c in cs if c["metadata"]["source_id"] == p.metadata["source_id"]
                      and anchor in squash(c["text"])), None)
            rows.append([f"P{i:02d}", k, p.metadata["source_id"], p.page, anchor,
                         c and c["chunk_id"], c and c["metadata"]["article"], c and c["text"], "", ""])
    write_csv(RESULTS / "audit_coherence.csv",
              ["position", "strategy", "source_id", "page", "anchor(khong_khoang_trang)", "chunk_id",
               "article", "chunk_text", "coherence(0-2)", "ly_do"], rows)


def main() -> None:
    questions = json.loads(BENCHMARK.read_text(encoding="utf-8"))["questions"]
    embedder = OpenAIEmbedder()
    store = PgVectorStore(DATABASE_URL, embedder.dimensions)

    t0 = time.perf_counter()
    # Same model and no prefix for queries and documents, so one batched call serves all strategies.
    qvecs = dict(zip([q["id"] for q in questions], embedder.embed_documents([q["question"] for q in questions])))
    embed_s = time.perf_counter() - t0

    all_traces, by_strategy, timing = [], {}, {}
    for s, cfg in STRATEGIES.items():
        t0, traces = time.perf_counter(), []
        for q in questions:
            filters = q["filter"] if cfg["use_filter"] and q.get("filter") else None
            hits = store.search(cfg["index"], qvecs[q["id"]], TOP_K, filters)
            t = evaluate_query(q, hits)
            t.update(strategy=s, index=cfg["index"], applied_filter=filters)
            traces.append(t)
        timing[s] = round(time.perf_counter() - t0, 2)
        by_strategy[s] = traces
        all_traces += traces
        with open(RESULTS / f"trace_{s}.jsonl", "w", encoding="utf-8") as f:
            for t in traces:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

    metrics = summarize(all_traces)
    dev_rank = sorted(STRATEGIES, key=lambda s: (-metrics[s]["dev"]["hit3"]["n"], -metrics[s]["dev"]["hit1"]["n"]))
    report = {
        "model": embedder.model_name, "top_k": TOP_K, "questions": len(questions),
        "query_tokens": embedder.total_tokens,
        "query_cost_usd": round(embedder.total_tokens / 1e6 * MODEL_PRICE_PER_1M[embedder.model_name], 6),
        "query_embed_seconds": round(embed_s, 2), "search_seconds": timing,
        "selection_rule": SELECTION_RULE, "chosen_on_dev": dev_rank[0],
        "note": "Grounding/coherence/metadata-đúng chưa có: chấm tay trong results/audit_*.csv",
        "metrics": metrics,
    }
    (RESULTS / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'':3}| {'dev Hit@1':>16} | {'dev Hit@3':>16} | {'test Hit@1':>14} | {'test Hit@3':>14} | "
          f"{'filter dev H@3':>14} | {'filter test H@3':>14}")
    for s in STRATEGIES:
        d, t = metrics[s]["dev"], metrics[s]["test"]
        print(f"{s:3}| {fmt(d['hit1']):>16} | {fmt(d['hit3']):>16} | {fmt(t['hit1']):>14} | {fmt(t['hit3']):>14} | "
              f"{fmt(d['filter_questions_hit3']):>14} | {fmt(t['filter_questions_hit3']):>14}")
    print(f"Tuân thủ filter top-3 (câu có filter, dev/test): " + " | ".join(
        f"{s}: {fmt(metrics[s]['dev']['filter_compliance_top3'])} / {fmt(metrics[s]['test']['filter_compliance_top3'])}"
        for s in STRATEGIES))
    print(f"Evidence bị tách (chunk chứa 1 phần quote) trong top-3, dev+test: " +
          ", ".join(f"{s}={metrics[s]['dev']['partial_evidence_in_top3'] + metrics[s]['test']['partial_evidence_in_top3']}"
                    for s in STRATEGIES))
    print(f"Chọn theo dev ({SELECTION_RULE.split(';')[0]}): {dev_rank[0]}")
    print(f"Embed {len(questions)} câu hỏi: {embedder.total_tokens} token ~ ${report['query_cost_usd']}")

    with open(EXPERIMENT_LOG, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["strategy", "chunking", "chunk_size", "overlap", "metadata", "filter", "vectorizer",
                    "hypothesis", "dev_hit1", "dev_hit3", "test_hit1", "test_hit3", "notes"])
        for s, cfg in STRATEGIES.items():
            cp = CHUNK_PARAMS[cfg["index"]]
            d, t = metrics[s]["dev"], metrics[s]["test"]
            w.writerow([s, cp["chunker"], cp.get("size", cp.get("max_size")), cp.get("overlap", 0),
                        "source_id,page,page_end,year,document_type,chapter,article",
                        "year/document_id khi câu hỏi có filter" if cfg["use_filter"] else "không",
                        f"OpenAI {embedder.model_name} ({embedder.dimensions}d), pgvector cosine exact",
                        HYPOTHESES[s], fmt(d["hit1"]), fmt(d["hit3"]), fmt(t["hit1"]), fmt(t["hit3"]),
                        "C dùng chung index B" if s == "C" else ""])

    test_ids = audit_sheets(by_strategy, questions)
    coherence_sheet()
    print(f"Đã ghi trace_*.jsonl, metrics.json, audit_*.csv (câu test để chấm tay: {', '.join(test_ids)}) "
          f"và artifacts/experiment_log.csv")


if __name__ == "__main__":
    main()
