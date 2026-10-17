# Arabic text comes from repaired PDFs, never the HTML pages

The official portal publishes each instrument as a PDF and as an HTML page. We use only the PDFs, because they are the stable official download and hash the same every time. Their Arabic text layers are broken in two different ways, and we repair them instead of falling back to HTML:

- **Labour Law (Arabic):** glyphs map correctly, including the لأ/لا/لم ligatures, but extractors that reverse right-to-left lines character by character flip those two-letter ligatures ("األجر" instead of "الأجر"). Ingest reorders lines a whole glyph at a time.
- **Executive Regulations (Arabic):** 80 glyph IDs (about 5% of characters) have no Unicode mapping, because the embedded font's character map was stripped. A committed glyph table maps each (font, glyph ID) to its letter(s). The table is built once by rendering each glyph and labelling it, then checked once against the official HTML page; neither the HTML nor that check is part of the pipeline.

Ingest fails closed: if any U+FFFD remains, or the Arabic and English article numbers don't match, it stops instead of indexing bad text.
