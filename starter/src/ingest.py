"""Step 4: embed chunks from step 3 and load them into pgvector (indexes A and B).

Run from starter/ (after `python -m src.build_chunks`):  python -m src.ingest
Re-running only embeds new/changed chunks (content hash) and deletes obsolete ones,
so a second run must report 0 embedded and an unchanged row count.
Each run is appended to results/ingest_runs.jsonl.
"""
import hashlib
import json
import time
from datetime import datetime, timezone

from .config import DATABASE_URL, INDEXES, MODEL_PRICE_PER_1M, RESULTS
from .embeddings import OpenAIEmbedder
from .models import Chunk
from .store import PgVectorStore


def load_chunks(name: str) -> list[Chunk]:
    path = RESULTS / name
    if not path.exists():
        raise FileNotFoundError(f"Chưa có {path}; chạy `python -m src.build_chunks` trước")
    return [Chunk(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    embedder = OpenAIEmbedder()
    store = PgVectorStore(DATABASE_URL, embedder.dimensions)
    store.create_schema()
    run = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "model": embedder.model_name, "dimensions": embedder.dimensions, "indexes": {}}

    for index, filename in INDEXES.items():
        chunks = load_chunks(filename)
        hashes = [hashlib.sha256(f"{embedder.model_name}\n{c.text}".encode()).hexdigest() for c in chunks]
        existing = store.existing_hashes(index)
        todo = [(c, h) for c, h in zip(chunks, hashes) if existing.get(c.chunk_id) != h]
        tokens_before, t0 = embedder.total_tokens, time.perf_counter()
        if todo:
            vectors = embedder.embed_documents([c.text for c, _ in todo])
            store.upsert(index, [c for c, _ in todo], vectors, [h for _, h in todo], embedder.model_name)
        deleted = store.delete_obsolete(index, [c.chunk_id for c in chunks])
        tokens = embedder.total_tokens - tokens_before
        stats = {
            "chunks": len(chunks), "embedded": len(todo), "unchanged": len(chunks) - len(todo),
            "deleted_obsolete": deleted, "rows_in_db": store.count(index), "tokens": tokens,
            "cost_usd": round(tokens / 1e6 * MODEL_PRICE_PER_1M[embedder.model_name], 6),
            "seconds": round(time.perf_counter() - t0, 2),
        }
        run["indexes"][index] = stats
        print(f"[{index}] {stats['chunks']} chunk | embed mới {stats['embedded']} | giữ nguyên "
              f"{stats['unchanged']} | xóa cũ {deleted} | số dòng DB {stats['rows_in_db']} | "
              f"{tokens} token ~ ${stats['cost_usd']} | {stats['seconds']}s")
        if stats["rows_in_db"] != len(chunks):
            raise RuntimeError(f"Index {index}: DB có {stats['rows_in_db']} dòng, khác {len(chunks)} chunk")

    with open(RESULTS / "ingest_runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    print("Đã ghi results/ingest_runs.jsonl (C dùng chung vector của B, chỉ thêm filter khi truy vấn)")


if __name__ == "__main__":
    main()
