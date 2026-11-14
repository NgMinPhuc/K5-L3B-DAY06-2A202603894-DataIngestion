"""Quick top-k check for one question.

Examples (from starter/):
  python -m src.search "Thời gian thử việc tối đa là bao lâu?" --strategy A
  python -m src.search "Theo BLLĐ 2012, tuổi nghỉ hưu của nam?" --strategy C --filter year=2012
"""
import argparse

from .config import DATABASE_URL, STRATEGIES, TOP_K
from .embeddings import OpenAIEmbedder
from .store import PgVectorStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--strategy", choices=STRATEGIES, default="C")
    ap.add_argument("--filter", action="append", default=[], help="key=value, vd year=2012")
    ap.add_argument("-k", type=int, default=TOP_K)
    args = ap.parse_args()

    cfg = STRATEGIES[args.strategy]
    filters = {}
    for item in args.filter:
        key, value = item.split("=", 1)
        filters[key] = int(value) if key == "year" else value
    if not cfg["use_filter"] and filters:
        print(f"Lưu ý: chiến lược {args.strategy} không dùng filter -> bỏ qua {filters}")
        filters = {}

    embedder = OpenAIEmbedder()
    store = PgVectorStore(DATABASE_URL, embedder.dimensions)
    hits = store.search(cfg["index"], embedder.embed_query(args.question), args.k, filters or None)
    for rank, h in enumerate(hits, 1):
        m = h["metadata"]
        print(f"#{rank} score={h['score']:.4f} | {h['source_id']} trang {h['page']}-{h['page_end']} | "
              f"{m.get('article')} | năm {m.get('year')}")
        print("   " + h["text"][:300].replace("\n", " ") + "\n")


if __name__ == "__main__":
    main()
