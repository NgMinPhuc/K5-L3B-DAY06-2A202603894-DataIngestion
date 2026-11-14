"""Fill page statistics in data/manifest.json from the PDFs.

Run from starter/:  python scripts/build_manifest.py
Hand-edited fields (url, accessed_at, excluded_pages, ...) are preserved.
"""
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.json"
MIN_CHARS = 200  # pages shorter than this after normalization are not counted


def normalized_len(text: str) -> int:
    text = unicodedata.normalize("NFC", text or "")
    return len(" ".join(text.split()))


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    totals = {"physical_pages": 0, "counted_pages": 0, "total_chars": 0}
    missing = []

    for src in manifest["sources"]:
        pdf = ROOT / src["source_path"]
        if not pdf.exists():
            missing.append(str(pdf))
            continue
        src["sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        excluded = {int(e["page"]) if isinstance(e, dict) else int(e)
                    for e in src.get("excluded_pages", [])}
        pages = []
        for i, page in enumerate(PdfReader(pdf).pages, start=1):
            try:
                chars = normalized_len(page.extract_text())
                error = None
            except Exception as exc:  # keep going, record the failure
                chars, error = 0, repr(exc)
            if error:
                reason = "extract_error"
            elif i in excluded:
                reason = "excluded_manual"
            elif chars < MIN_CHARS:
                reason = "too_short"
            else:
                reason = None
            entry = {"page": i, "chars": chars, "counted": reason is None}
            if reason:
                entry["reason"] = reason
            if error:
                entry["error"] = error
            pages.append(entry)

        counted = [p for p in pages if p["counted"]]
        src["pages"] = pages
        src["physical_pages"] = len(pages)
        src["counted_pages"] = len(counted)
        src["total_chars"] = sum(p["chars"] for p in counted)
        for key in totals:
            totals[key] += src[key]
        print(f"{src['source_id']}: {len(pages)} trang vật lý, "
              f"{len(counted)} trang tính, {src['total_chars']} ký tự")

    manifest["totals"] = totals
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"TỔNG: {totals['counted_pages']} trang nội dung "
          f"({'ĐẠT' if totals['counted_pages'] >= 30 else 'CHƯA ĐẠT'} >= 30)")
    if missing:
        print("Thiếu file:", *missing, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
