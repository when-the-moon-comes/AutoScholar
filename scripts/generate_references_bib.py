import html
import importlib.util
import re
import sys
import unicodedata
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = REPO_ROOT / "paper"
OUTPUT_BIB = PAPER_DIR / "references.bib"
RECOMMENDATION_SCRIPT = REPO_ROOT / "scripts" / "generate_claim_recommendation_list.py"

TITLE_STOPWORDS = {
    "a", "an", "and", "as", "at", "based", "by", "for", "from", "in", "into",
    "of", "on", "or", "the", "to", "under", "using", "via", "with",
}

CONFERENCE_MARKERS = {
    "conference", "congress", "proceedings", "symposium", "workshop",
}


def load_recommendation_module():
    spec = importlib.util.spec_from_file_location(
        "generate_claim_recommendation_list",
        RECOMMENDATION_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {RECOMMENDATION_SCRIPT}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    translation_table = str.maketrans({
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2026": "...",
        "\u00a0": " ",
        "＊": "'",
        "＆": "'",
        "※": '"',
        "§": '"',
        "坼": "-",
        "聽": " ",
    })
    text = text.translate(translation_table)
    return " ".join(text.split())


def clean_bib_field_text(value: str | None) -> str:
    text = strip_accents(normalize_text(value))
    text = "".join(char for char in text if ord(char) < 128)
    return " ".join(text.split())


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def slugify(value: str) -> str:
    ascii_text = strip_accents(normalize_text(value)).lower()
    parts = re.findall(r"[a-z0-9]+", ascii_text)
    return "".join(parts)


def first_author_surname(paper: dict) -> str:
    authors = paper.get("authors") or []
    if not authors:
        return "unknown"

    parts = re.findall(r"[A-Za-z0-9]+", strip_accents(str(authors[0])))
    if not parts:
        return "unknown"
    return parts[-1].lower()


def title_key_words(title: str, limit: int = 2) -> str:
    words = []
    ascii_title = strip_accents(normalize_text(title)).lower()
    for token in re.findall(r"[a-z0-9]+", ascii_title):
        if token in TITLE_STOPWORDS:
            continue
        words.append(token)
        if len(words) == limit:
            break
    return "".join(words) or "untitled"


def escape_bibtex(value: str) -> str:
    text = clean_bib_field_text(value)
    replacements = {
        "\\": "\\textbackslash{}",
        "{": "\\{",
        "}": "\\}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def infer_entry_type(paper: dict) -> tuple[str, str | None]:
    doi = normalize_text(paper.get("doi")).lower()
    venue = normalize_text(paper.get("venue"))
    venue_lower = venue.lower()

    if "/978-" in doi:
        return "incollection", "booktitle"
    if any(marker in venue_lower for marker in CONFERENCE_MARKERS):
        return "inproceedings", "booktitle"
    if venue:
        return "article", "journal"
    if doi:
        return "article", "journal"
    return "book", None


def paper_sort_key(paper: dict) -> tuple:
    return (
        first_author_surname(paper),
        paper.get("year") or 0,
        normalize_text(paper.get("title")).lower(),
    )


def build_citekeys(papers: list[dict], recommendation_module) -> dict[str, str]:
    used_keys: dict[str, str] = {}
    citekeys: dict[str, str] = {}

    for paper in sorted(papers, key=paper_sort_key):
        paper_identifier = recommendation_module.paper_key(paper)
        year = str(paper.get("year") or "nodate")
        base = f"{first_author_surname(paper)}{year}{title_key_words(paper.get('title') or '')}"
        key = slugify(base) or "refnodateuntitled"

        if key in used_keys and used_keys[key] != paper_identifier:
            suffix_code = ord("a")
            while True:
                candidate = f"{key}{chr(suffix_code)}"
                if candidate not in used_keys or used_keys[candidate] == paper_identifier:
                    key = candidate
                    break
                suffix_code += 1

        used_keys[key] = paper_identifier
        citekeys[paper_identifier] = key

    return citekeys


def format_entry(citekey: str, paper: dict) -> str:
    entry_type, venue_field = infer_entry_type(paper)
    fields: list[tuple[str, str]] = [
        ("author", " and ".join(clean_bib_field_text(author) for author in (paper.get("authors") or []))),
        ("title", escape_bibtex(paper.get("title") or "Untitled")),
    ]

    if paper.get("year"):
        fields.append(("year", str(paper["year"])))

    venue = clean_bib_field_text(paper.get("venue"))
    if venue and venue_field:
        fields.append((venue_field, escape_bibtex(venue)))
    elif venue and entry_type == "misc":
        fields.append(("note", escape_bibtex(f"Venue: {venue}")))

    doi = normalize_text(paper.get("doi"))
    if doi:
        fields.append(("doi", doi.lower()))

    lines = [f"@{entry_type}{{{citekey},"]
    for name, value in fields:
        if not value:
            continue
        if name == "title":
            lines.append(f"  {name} = {{{{{value}}}}},")
        else:
            lines.append(f"  {name} = {{{value}}},")
    lines.append("}")
    return "\n".join(lines)


def collect_selected_papers(recommendation_module) -> list[dict]:
    claims = recommendation_module.load_claim_units(recommendation_module.CLAIM_UNITS)
    records = recommendation_module.load_records(recommendation_module.DEDUPED_RESULTS)
    recommendations = recommendation_module.build_recommendations(claims, records)

    unique_papers: dict[str, dict] = {}
    for item in recommendations.values():
        for group in item["selected_papers"]:
            paper = group["paper"]
            key = recommendation_module.paper_key(paper)
            unique_papers.setdefault(key, paper)

    return [unique_papers[key] for key in sorted(unique_papers)]


def write_bib(output_path: Path) -> tuple[int, dict[str, str]]:
    recommendation_module = load_recommendation_module()
    papers = collect_selected_papers(recommendation_module)
    citekeys = build_citekeys(papers, recommendation_module)

    entries = []
    for paper in sorted(papers, key=paper_sort_key):
        paper_identifier = recommendation_module.paper_key(paper)
        entries.append(format_entry(citekeys[paper_identifier], paper))

    header = [
        "% Auto-generated from claim recommendation outputs.",
        "% Source files: paper/claim_recommended_citations.md, paper/semantic_scholar_raw_results_deduped.jsonl",
        f"% Entry count: {len(entries)}",
    ]
    output_path.write_text("\n".join(header) + "\n\n" + "\n\n".join(entries) + "\n", encoding="utf-8")
    return len(entries), citekeys


def main() -> int:
    entry_count, _ = write_bib(OUTPUT_BIB)
    print(f"Wrote: {OUTPUT_BIB}")
    print(f"Entries: {entry_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
