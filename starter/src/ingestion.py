"""Read and normalize the PDF corpus listed in data/manifest.json."""
import json
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.json"

# Công báo prints "CÔNG BÁO/Số 1203 + 1204/Ngày 28-12-2020 <page>" on every page.
_GAZETTE_HEADER = re.compile(r"^\s*\d*\s*CÔNG BÁO/Số[^\n]*$", re.MULTILINE)
# Lines that are only a printed page number.
_PAGE_NUMBER_LINE = re.compile(r"^\s*\d{1,3}\s*$", re.MULTILINE)


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while keeping line structure.

    - NFC so composed/decomposed Vietnamese diacritics compare equal.
    - The 2012 PDF's font maps 'ư' to 'ƣ' (U+01A3): map it back.
    - Drop gazette header lines and bare page-number lines (noise in every chunk).
    - Collapse runs of spaces inside a line; keep newlines so "Điều"/"Khoản"
      headings stay at line starts. Spaces wrongly inserted inside syllables
      ("nhà n ước") are NOT repaired: no safe rule exists, see the report.
    """
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("ƣ", "ư").replace("Ƣ", "Ư").replace(" ", " ")
    text = _GAZETTE_HEADER.sub("", text)
    text = _PAGE_NUMBER_LINE.sub("", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def squash(text: str) -> str:
    """Whitespace-free form used to match evidence quotes against chunks."""
    return re.sub(r"\s+", "", normalize_text(text))


def load_pdf(path: Path, document_id: str, source: str,
             metadata: dict | None = None, excluded_pages: set[int] | None = None,
             errors: list[str] | None = None) -> list[DocumentPage]:
    """Extract each physical page with its 1-based page number.

    Empty pages, extraction failures and manifest-excluded pages are skipped
    and recorded in `errors` instead of being silently dropped.
    """
    excluded_pages = excluded_pages or set()
    errors = errors if errors is not None else []
    pages: list[DocumentPage] = []
    for number, page in enumerate(PdfReader(path).pages, start=1):
        if number in excluded_pages:
            errors.append(f"{source}\tpage {number}\texcluded_by_manifest")
            continue
        try:
            text = normalize_text(page.extract_text())
        except Exception as exc:  # keep processing the other pages
            errors.append(f"{source}\tpage {number}\textract_error\t{exc!r}")
            continue
        if not text:
            errors.append(f"{source}\tpage {number}\tempty_page")
            continue
        pages.append(DocumentPage(document_id=document_id, source=source, page=number,
                                  text=text, metadata=dict(metadata or {})))
    return pages


def load_corpus(manifest_path: Path = MANIFEST) -> tuple[dict[str, list[DocumentPage]], list[str]]:
    """Load every manifest source. Returns {source_id: pages} and the error log lines.

    Pages the manifest marks as not counted (too short, appendix forms) are excluded
    from the index as well, so retrieval sees the same content the page count describes.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    corpus: dict[str, list[DocumentPage]] = {}
    errors: list[str] = []
    for src in manifest["sources"]:
        excluded = {p["page"] for p in (src.get("pages") or []) if not p["counted"]}
        meta = {
            "source_id": src["source_id"],
            "document_number": src["document_number"],
            "document_type": src["document_type"],
            "year": src["year"],
            "title": src["title"],
        }
        corpus[src["source_id"]] = load_pdf(
            ROOT / src["source_path"], document_id=src["document_id"],
            source=src["source_path"], metadata=meta, excluded_pages=excluded, errors=errors)
    return corpus, errors
