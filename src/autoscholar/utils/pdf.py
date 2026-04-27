from __future__ import annotations

from pathlib import Path

import fitz


def default_output_path(input_pdf: Path) -> Path:
    return input_pdf.with_suffix(".txt")


def extract_pdf_text(input_pdf: Path) -> str:
    chunks: list[str] = []
    with fitz.open(input_pdf) as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True).strip()
            chunks.append(f"=== Page {page_number} ===")
            if text:
                chunks.append(text)
            chunks.append("")
    return "\n\n".join(chunks).strip() + "\n"


def pdf_to_text(input_pdf: Path, output_txt: Path | None = None) -> Path:
    input_pdf = input_pdf.resolve()
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")
    if input_pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Input file is not a PDF: {input_pdf}")
    output_path = (output_txt or default_output_path(input_pdf)).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(extract_pdf_text(input_pdf), encoding="utf-8")
    return output_path
