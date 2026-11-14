"""Fixed-size (strategy A) and article-aware (strategies B/C) chunking.

Both chunkers work on one source file at a time: pages are joined into a single
stream with a character-offset -> page map, so a chunk that crosses a page break
records both `page` (start) and `metadata["page_end"]`. Both chunkers attach the
same metadata (chapter/article are taken from the nearest heading before the chunk),
so A vs B compares chunking only.
"""
import bisect
import re
from dataclasses import dataclass

from .models import Chunk, DocumentPage

# "Điều 25. Thời gian thử việc" at a line start. The capital letter after the dot
# rejects wrapped cross-references such as "Điều 97 của Bộ luật này".
# The 2012 PDF inserts spaces inside numbers ("Điều 1 45.", "Điều 20 0."), so
# spaces between digits are allowed and removed; the increasing-number check in
# _stream() rejects any misread.
ARTICLE_RE = re.compile(r"^Đi ?ều (\d(?: ?\d){0,2})\s?\.\s*(?=[A-ZĐÀ-Ỹ])", re.MULTILINE)
CHAPTER_RE = re.compile(r"^(?:Chương|CHƯƠNG) ([IVXLC]+)\b", re.MULTILINE)
CLAUSE_RE = re.compile(r"^\d{1,2}\.\s", re.MULTILINE)        # "1. " khoản
POINT_RE = re.compile(r"^[a-zđ]\)\s", re.MULTILINE)           # "a) " điểm


@dataclass
class _Stream:
    pages: list[DocumentPage]
    text: str
    starts: list[int]                    # offset where each page starts
    articles: list[tuple[int, str]]      # (offset, "Điều N")
    chapters: list[tuple[int, str]]      # (offset, "Chương X")

    def page_at(self, offset: int) -> int:
        return self.pages[bisect.bisect_right(self.starts, offset) - 1].page

    @staticmethod
    def _last_before(marks: list[tuple[int, str]], offset: int) -> str | None:
        i = bisect.bisect_right([m[0] for m in marks], offset) - 1
        return marks[i][1] if i >= 0 else None

    def make_chunk(self, kind: str, start: int, end: int, text: str | None = None) -> Chunk:
        first = self.pages[0]
        body = (text if text is not None else self.text[start:end]).strip()
        meta = dict(first.metadata)
        meta.update({
            "page_end": self.page_at(max(start, end - 1)),
            "chapter": self._last_before(self.chapters, start),
            "article": self._last_before(self.articles, start),
            "char_start": start, "char_end": end, "chunker": kind,
        })
        return Chunk(chunk_id=f"{meta['source_id']}:{kind}:{start}-{end}",
                     document_id=first.document_id, source=first.source,
                     page=self.page_at(start), text=body, metadata=meta)


def _stream(pages: list[DocumentPage]) -> _Stream:
    parts, starts, pos = [], [], 0
    for p in pages:
        starts.append(pos)
        parts.append(p.text)
        pos += len(p.text) + 1                    # +1 for the joining newline
    text = "\n".join(parts)
    articles, last = [], 0
    for m in ARTICLE_RE.finditer(text):
        n = int(m.group(1).replace(" ", ""))
        if not articles or last < n <= last + 5:  # headings increase; skip stray matches
            articles.append((m.start(), f"Điều {n}"))
            last = n
    chapters = [(m.start(), f"Chương {m.group(1)}") for m in CHAPTER_RE.finditer(text)]
    return _Stream(pages, text, starts, articles, chapters)


def fixed_size(pages: list[DocumentPage], size: int, overlap: int) -> list[Chunk]:
    """Strategy A: sliding character windows of `size` with `overlap`.

    The window end is moved back to the previous whitespace (at most 40 chars) so
    words are not cut; otherwise boundaries ignore document structure on purpose.
    """
    if not 0 <= overlap < size:
        raise ValueError("need 0 <= overlap < size")
    s = _stream(pages)
    chunks, start, n = [], 0, len(s.text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            cut = s.text.rfind(" ", end - 40, end)
            cut = max(cut, s.text.rfind("\n", end - 40, end))
            end = cut if cut > start else end
        chunks.append(s.make_chunk("fixed", start, end))
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c.text]


def _split_by(pattern: re.Pattern, text: str) -> list[tuple[int, int]]:
    """Spans of `text` cut before every line matching `pattern` (first span = lead-in)."""
    cuts = [0] + [m.start() for m in pattern.finditer(text) if m.start() > 0] + [len(text)]
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if text[a:b].strip()]


def _pack(spans: list[tuple[int, int]], max_size: int) -> list[tuple[int, int]]:
    """Greedily merge consecutive spans while the merged length stays <= max_size."""
    out: list[tuple[int, int]] = []
    for a, b in spans:
        if out and b - out[-1][0] <= max_size:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def by_article(pages: list[DocumentPage], max_size: int) -> list[Chunk]:
    """Strategy B: one chunk per "Điều"; long articles are split by khoản, then điểm.

    Every sub-chunk of a split article is prefixed with the article heading line
    (e.g. "Điều 25. Thời gian thử việc") so it stays understandable on its own.
    Text before the first article (title, preamble) becomes its own unit.
    Pieces still longer than max_size after the điểm split are kept whole and
    reported by the stats (no blind character cut).
    """
    s = _stream(pages)
    bounds = [0] + [off for off, _ in s.articles] + [len(s.text)]
    chunks: list[Chunk] = []
    for a, b in zip(bounds, bounds[1:]):
        unit = s.text[a:b]
        if not unit.strip():
            continue
        if len(unit.strip()) <= max_size:
            chunks.append(s.make_chunk("article", a, b))
            continue
        heading = unit.strip().splitlines()[0]
        spans = []
        for ca, cb in _split_by(CLAUSE_RE, unit):
            if cb - ca <= max_size:
                spans.append((ca, cb))
            else:
                spans.extend((ca + pa, ca + pb) for pa, pb in _split_by(POINT_RE, unit[ca:cb]))
        for i, (pa, pb) in enumerate(_pack(spans, max_size)):
            piece = unit[pa:pb].strip()
            text = piece if i == 0 else f"{heading}\n{piece}"
            chunks.append(s.make_chunk("article", a + pa, a + pb, text=text))
    return [c for c in chunks if c.text]
