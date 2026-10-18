"""Dev tool for building a source's glyph table (ADR-0004); needs the dev group (fonttools).

    uv run python -I scripts/glyph_sheet.py <pdf> <out dir>

Prints every (font, glyph ID) the PDF cannot map to Unicode, with its count and words it
appears in (shown as `[glyph ID]`), and writes one SVG sheet per font drawing those glyphs.
"""

import collections
import io
import re
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage

from eval_harness.pdf_text import REPLACEMENT, _GlyphRecorder, pdf_text

CELL = 160
COLUMNS = 8


class _UnmappedRecorder(_GlyphRecorder):
    def __init__(self, resources: PDFResourceManager):
        super().__init__(resources, {})
        self.unmapped: collections.Counter[tuple[str, int]] = collections.Counter()
        self.font_files: dict[str, bytes] = {}

    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
        advance = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
        if self.glyphs[-1].text == REPLACEMENT:
            self.unmapped[(font.fontname, cid)] += 1
            self.font_files.setdefault(font.fontname, font.fontfile.get_data())
        return advance


def unmapped_glyphs(path: Path) -> _UnmappedRecorder:
    resources = PDFResourceManager()
    recorder = _UnmappedRecorder(resources)
    interpreter = PDFPageInterpreter(resources, recorder)
    with path.open("rb") as file:
        for page in PDFPage.get_pages(file):
            recorder.glyphs = []
            interpreter.process_page(page)
    return recorder


def sample_words(path: Path, keys: list[tuple[str, int]]) -> dict[tuple[str, int], list[str]]:
    markers = {key: f"[{key[1]}]" for key in keys}
    text = pdf_text(path, markers)
    words: dict[tuple[str, int], list[str]] = {key: [] for key in keys}
    for word in re.findall(r"\S*\[\d+\]\S*", text):
        for key, marker in markers.items():
            if marker in word and word not in words[key] and len(words[key]) < 6:
                words[key].append(word)
    return words


def sheet(font: TTFont, glyph_ids: list[int]) -> str:
    glyph_set = font.getGlyphSet()
    names = font.getGlyphOrder()
    scale = CELL * 0.45 / font["head"].unitsPerEm  # ty: ignore[unresolved-attribute]
    rows = -(-len(glyph_ids) // COLUMNS)
    cells = []
    for n, glyph_id in enumerate(glyph_ids):
        x, y = (n % COLUMNS) * CELL, (n // COLUMNS) * CELL
        pen = SVGPathPen(glyph_set)
        glyph_set[names[glyph_id]].draw(pen)
        cells.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" fill="none" stroke="#ccc"/>'
            f'<text x="{x + 4}" y="{y + 16}" font-size="14">{glyph_id}</text>'
            f'<path transform="translate({x + CELL * 0.3},{y + CELL * 0.7}) '
            f'scale({scale},{-scale})" d="{pen.getCommands()}"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{COLUMNS * CELL}" '
        f'height="{rows * CELL}"><rect width="100%" height="100%" fill="white"/>'
        + "".join(cells)
        + "</svg>"
    )


def main(pdf: str, out_dir: str) -> None:
    path, out = Path(pdf), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    recorder = unmapped_glyphs(path)
    keys = sorted(recorder.unmapped)
    words = sample_words(path, keys)
    for key in keys:
        print(key[0], key[1], recorder.unmapped[key], " ".join(words[key]))
    for font_name, data in recorder.font_files.items():
        glyph_ids = [cid for name, cid in keys if name == font_name]
        svg = sheet(TTFont(io.BytesIO(data)), glyph_ids)
        (out / f"{font_name}.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
