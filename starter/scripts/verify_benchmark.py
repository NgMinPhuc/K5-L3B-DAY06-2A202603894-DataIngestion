"""Check every gold/alt evidence quote exists on its page, plus split/filter rules.

Run from starter/:  python scripts/verify_benchmark.py
"""
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def squash(text: str) -> str:
    """Same normalization as the evidence_match_rule, then drop all whitespace."""
    text = unicodedata.normalize("NFC", text or "").replace("ƣ", "ư").replace("Ƣ", "Ư")
    text = re.sub(r"CÔNG BÁO/Số[^\n]*", "", text)
    return re.sub(r"\s+", "", text)


def main() -> int:
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    bench = json.loads((ROOT / "benchmark/questions.json").read_text(encoding="utf-8"))
    sources = {s["source_id"]: s for s in manifest["sources"]}
    pages = {sid: [squash(p.extract_text()) for p in PdfReader(ROOT / s["source_path"]).pages]
             for sid, s in sources.items()}
    filter_values = {"year": {s["year"] for s in sources.values()},
                     "document_id": {s["document_id"] for s in sources.values()}}

    errors = []
    qs = bench["questions"]
    for q in qs:
        golds = [{"source_id": q["gold_source_id"], "page": q["gold_page"],
                  "evidence_quote": q["evidence_quote"]}] + q.get("alt_gold", [])
        for g in golds:
            sid, page = g["source_id"], g["page"]
            if sid not in pages or not 1 <= page <= len(pages[sid]):
                errors.append(f"{q['id']}: không có {sid} trang {page}")
                continue
            if squash(g["evidence_quote"]) not in pages[sid][page - 1]:
                errors.append(f"{q['id']}: evidence không nằm ở {sid} trang {page}")
        for key, val in (q.get("filter") or {}).items():
            if val not in filter_values.get(key, set()):
                errors.append(f"{q['id']}: filter {key}={val} không tồn tại trong manifest")

    split = Counter(q["split"] for q in qs)
    filt = Counter(q["split"] for q in qs if q.get("filter"))
    ids = [q["id"] for q in qs]
    if len(set(ids)) != len(ids):
        errors.append("id bị trùng")
    if len(qs) < 20 or split["dev"] < 15 or split["test"] < 5:
        errors.append(f"số câu chưa đủ: {dict(split)}")
    if sum(filt.values()) < 3 or filt["test"] < 1:
        errors.append(f"câu có filter chưa đủ: {dict(filt)}")

    print(f"{len(qs)} câu | split {dict(split)} | có filter {dict(filt)} | "
          f"loại {dict(Counter(q['type'] for q in qs))}")
    for e in errors:
        print("LỖI:", e)
    print("OK: mọi evidence đã kiểm chứng" if not errors else f"{len(errors)} lỗi")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
