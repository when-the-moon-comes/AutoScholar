from __future__ import annotations

import html
import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from autoscholar.citation.config import CitationRulesConfig
from autoscholar.io import read_yaml
from autoscholar.models import (
    ClaimRecord,
    PaperRecord,
    QueryRecord,
    QueryReviewRecord,
    SearchResultRecord,
)

DEFAULT_STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "into", "this", "these", "those",
    "their", "there", "where", "which", "while", "within", "across", "between",
    "rather", "than", "such", "through", "using", "based", "study", "research",
    "analysis", "approach", "case", "system", "systems",
}

TITLE_STOPWORDS = {
    "a", "an", "and", "as", "at", "based", "by", "for", "from", "in", "into",
    "of", "on", "or", "the", "to", "under", "using", "via", "with",
}

CONFERENCE_MARKERS = {
    "conference", "congress", "proceedings", "symposium", "workshop",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_rules(path: Path) -> CitationRulesConfig:
    return CitationRulesConfig.model_validate(read_yaml(path))


def tokenize(text: str, stopwords: set[str]) -> set[str]:
    tokens = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", (text or "").lower()):
        normalized = token.strip("-")
        if len(normalized) < 4:
            continue
        if normalized in stopwords:
            continue
        tokens.add(normalized)
    return tokens


def rules_stopwords(rules: CitationRulesConfig) -> set[str]:
    return DEFAULT_STOPWORDS | {item.strip().lower() for item in rules.stopwords if item.strip()}


def paper_key(paper: PaperRecord) -> str:
    if paper.paper_id:
        return f"paper:{paper.paper_id}"
    if paper.doi:
        return f"doi:{paper.doi.lower()}"
    title = paper.title.strip().lower()
    year = paper.year or ""
    return f"title:{title}|year:{year}"


def paper_reference_aliases(paper: PaperRecord) -> list[str]:
    aliases = [paper_key(paper)]
    if paper.paper_id:
        aliases.append(f"paper:{paper.paper_id.lower()}")
    if paper.doi:
        aliases.append(f"doi:{paper.doi.lower()}")
    title = paper.title.strip().lower()
    if title:
        aliases.append(f"title:{title}|year:{paper.year or ''}")
    deduped: list[str] = []
    seen = set()
    for alias in aliases:
        if alias in seen:
            continue
        seen.add(alias)
        deduped.append(alias)
    return deduped


def paper_strength(paper: PaperRecord) -> tuple[int, int, int]:
    return (
        paper.influential_citation_count or 0,
        paper.citation_count or 0,
        paper.year or 0,
    )


def dedupe_search_results(records: list[SearchResultRecord]) -> list[SearchResultRecord]:
    grouped: dict[str, list[SearchResultRecord]] = defaultdict(list)
    for record in records:
        grouped[record.query_id].append(record)

    deduped: list[SearchResultRecord] = []
    for query_id, items in grouped.items():
        _ = query_id
        best = max(items, key=lambda item: (item.paper_count, item.total_hits or -1, item.retrieved_at))
        seen_keys: set[str] = set()
        papers: list[PaperRecord] = []
        for paper in best.papers:
            key = paper_key(paper)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            papers.append(paper.model_copy(update={"rank": len(papers) + 1}))
        deduped.append(best.model_copy(update={"papers": papers, "paper_count": len(papers)}))
    deduped.sort(key=lambda item: item.query_id)
    return deduped


def evaluate_query(record: SearchResultRecord) -> tuple[str, str]:
    paper_count = record.paper_count
    max_citations = max((paper.citation_count or 0) for paper in record.papers) if paper_count else 0
    if paper_count == 0:
        return "rewrite", "empty result set"
    if paper_count == 1 and max_citations == 0:
        return "rewrite", "single low-signal result"
    if max_citations == 0:
        return "review", "all returned papers currently have zero citations"
    if paper_count < 3:
        return "review", "small result set; keep but verify manually"
    return "keep", "usable for preliminary screening"


def build_query_reviews(
    claims: dict[str, ClaimRecord],
    queries: dict[str, QueryRecord],
    records: list[SearchResultRecord],
    rules: CitationRulesConfig,
) -> list[QueryReviewRecord]:
    _ = claims
    reviews: list[QueryReviewRecord] = []
    for record in records:
        if record.query_id in rules.excluded_queries:
            status = "exclude"
            reason = rules.excluded_queries[record.query_id]
        else:
            status, reason = evaluate_query(record)
        max_citations = max((paper.citation_count or 0) for paper in record.papers) if record.paper_count else 0
        reviews.append(
            QueryReviewRecord(
                query_id=record.query_id,
                claim_id=queries[record.query_id].claim_id,
                status=status,
                reason=reason,
                paper_count=record.paper_count,
                total_hits=record.total_hits,
                max_citations=max_citations,
            )
        )
    reviews.sort(key=lambda item: item.query_id)
    return reviews


def review_by_query_id(reviews: list[QueryReviewRecord]) -> dict[str, QueryReviewRecord]:
    return {review.query_id: review for review in reviews}


def claim_status_for_selected(query_reviews: list[QueryReviewRecord], selected_count: int, note: str | None) -> str:
    if selected_count == 0:
        return "weak"
    if note:
        return "review"
    if not any(review.status == "keep" for review in query_reviews):
        return "review"
    return "ready"


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
    })
    return " ".join(text.translate(translation_table).split())


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def clean_bib_field_text(value: str | None) -> str:
    text = strip_accents(normalize_text(value))
    text = "".join(char for char in text if ord(char) < 128)
    return " ".join(text.split())


def slugify(value: str) -> str:
    ascii_text = strip_accents(normalize_text(value)).lower()
    return "".join(re.findall(r"[a-z0-9]+", ascii_text))


def first_author_surname(paper: PaperRecord) -> str:
    if not paper.authors:
        return "unknown"
    parts = re.findall(r"[A-Za-z0-9]+", strip_accents(str(paper.authors[0])))
    return parts[-1].lower() if parts else "unknown"


def title_key_words(title: str, limit: int = 2) -> str:
    words: list[str] = []
    ascii_title = strip_accents(normalize_text(title)).lower()
    for token in re.findall(r"[a-z0-9]+", ascii_title):
        if token in TITLE_STOPWORDS:
            continue
        words.append(token)
        if len(words) == limit:
            break
    return "".join(words) or "untitled"


def infer_entry_type(paper: PaperRecord) -> tuple[str, str | None]:
    doi = normalize_text(paper.doi).lower()
    venue = normalize_text(paper.venue)
    if "/978-" in doi:
        return "incollection", "booktitle"
    if any(marker in venue.lower() for marker in CONFERENCE_MARKERS):
        return "inproceedings", "booktitle"
    if venue or doi:
        return "article", "journal"
    return "book", None


def score_authority(paper: PaperRecord) -> tuple[float, float]:
    influential = math.log1p(paper.influential_citation_count or 0)
    citations = math.log1p(paper.citation_count or 0)
    return influential, citations
