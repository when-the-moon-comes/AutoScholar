import argparse
from pathlib import Path

import fitz


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract readable text from a PDF into a plain text file."
    )
    parser.add_argument(
        "input_pdf",
        type=Path,
        help="Path to the input PDF file.",
    )
    parser.add_argument(
        "output_txt",
        nargs="?",
        type=Path,
        help="Optional output TXT path. Defaults to the input filename with a .txt suffix.",
    )
    return parser.parse_args()


def default_output_path(input_pdf: Path) -> Path:
    return input_pdf.with_suffix(".txt")


def extract_text(input_pdf: Path) -> str:
    chunks: list[str] = []
    with fitz.open(input_pdf) as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True).strip()
            chunks.append(f"=== Page {page_number} ===")
            if text:
                chunks.append(text)
            chunks.append("")
    return "\n\n".join(chunks).strip() + "\n"


def main() -> int:
    args = parse_args()
    input_pdf = args.input_pdf.resolve()
    output_txt = (args.output_txt or default_output_path(input_pdf)).resolve()

    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")
    if input_pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Input file is not a PDF: {input_pdf}")

    output_txt.parent.mkdir(parents=True, exist_ok=True)
    text = extract_text(input_pdf)
    output_txt.write_text(text, encoding="utf-8")

    print(f"Input: {input_pdf}")
    print(f"Output: {output_txt}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
