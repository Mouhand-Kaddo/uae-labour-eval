"""PDF text from positioned glyphs, with right-to-left lines put back in logical order."""

import itertools
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTChar
from pdfminer.pdffont import PDFUnicodeNotDefined
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage

REPLACEMENT = "�"
GlyphTable = dict[tuple[str, int], str]

LEFT_TO_RIGHT = {"L", "EN", "AN"}
RIGHT_TO_LEFT = {"R", "AL"}
SEPARATORS = {"CS", "ES"}
SAME_LINE = 0.3


@dataclass(frozen=True)
class Glyph:
    text: str
    x0: float
    x1: float
    baseline: float
    size: float


def pdf_text(path: Path, glyph_table: GlyphTable) -> str:
    """The text of every page, line by line in reading order.

    `glyph_table` gives the text for (font name, glyph ID) pairs whose Unicode mapping in the
    PDF is missing or wrong; any other unmapped glyph becomes U+FFFD.
    """
    resources = PDFResourceManager()
    device = _GlyphRecorder(resources, glyph_table)
    interpreter = PDFPageInterpreter(resources, device)
    pages = []
    with path.open("rb") as file:
        for page in PDFPage.get_pages(file):
            device.glyphs = []
            interpreter.process_page(page)
            pages.append("\n".join(page_lines(device.glyphs)))
    return "\n".join(pages)


class _GlyphRecorder(PDFPageAggregator):
    def __init__(self, resources: PDFResourceManager, glyph_table: GlyphTable):
        super().__init__(resources, laparams=None)
        self.glyph_table = glyph_table
        self.glyphs: list[Glyph] = []

    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
        try:
            text = font.to_unichr(cid)
        except PDFUnicodeNotDefined:
            text = REPLACEMENT
        text = self.glyph_table.get((font.fontname, cid), text)
        char = LTChar(
            matrix,
            font,
            fontsize,
            scaling,
            rise,
            text,
            font.char_width(cid),
            font.char_disp(cid),
            ncs,
            graphicstate,
        )
        self.glyphs.append(Glyph(text, char.x0, char.x1, matrix[5], char.size))
        return char.adv


def page_lines(glyphs: list[Glyph]) -> list[str]:
    """The page's lines top to bottom, each in logical (reading) order. Diacritics, which
    sit above or below the baseline, are attached to the letter they are drawn on."""
    marks = [g for g in glyphs if g.text and _is_mark(g.text)]
    lines: list[list[Glyph]] = []
    letters = (g for g in glyphs if g.text and not _is_mark(g.text))
    for glyph in sorted(letters, key=lambda g: -g.baseline):
        if lines and lines[-1][0].baseline - glyph.baseline <= SAME_LINE * glyph.size:
            lines[-1].append(glyph)
        else:
            lines.append([glyph])
    if not lines:
        return []
    lines = [sorted(line, key=lambda g: g.x0) for line in lines]
    texts = [[g.text for g in line] for line in lines]
    for mark in marks:
        n = min(range(len(lines)), key=lambda i: abs(lines[i][0].baseline - mark.baseline))
        texts[n][_host(lines[n], mark)] += mark.text
    return [_logical(line) for line in texts]


def _is_mark(text: str) -> bool:
    return all(unicodedata.combining(c) for c in text)


def _host(line: list[Glyph], mark: Glyph) -> int:
    """Index of the letter nearest the mark's centre, ignoring spaces."""
    centre = (mark.x0 + mark.x1) / 2
    letters = [i for i, g in enumerate(line) if g.text.strip()] or list(range(len(line)))
    return min(letters, key=lambda i: max(line[i].x0 - centre, centre - line[i].x1, 0))


def _logical(visual: list[str]) -> str:
    """Reverse the glyphs of a right-to-left line, keeping left-to-right runs in their order."""
    directions = [_direction(text) for text in visual]
    if not RIGHT_TO_LEFT.intersection(directions):
        return "".join(visual)
    glyphs = visual[::-1]
    directions.reverse()
    in_run = [d in LEFT_TO_RIGHT for d in directions]
    strong = [i for i, d in enumerate(directions) if d in LEFT_TO_RIGHT | RIGHT_TO_LEFT]
    for before, after in itertools.pairwise(strong):
        between = range(before + 1, after)
        latin = directions[before] == directions[after] == "L"
        separator = len(between) == 1 and directions[before + 1] in SEPARATORS
        if in_run[before] and in_run[after] and (latin or separator):
            for i in between:
                in_run[i] = True
    out: list[str] = []
    for left_to_right, group in itertools.groupby(zip(glyphs, in_run, strict=True), lambda p: p[1]):
        texts = [text for text, _ in group]
        out.extend(reversed(texts) if left_to_right else texts)
    return "".join(out)


def _direction(text: str) -> str:
    return unicodedata.bidirectional(text[0])
