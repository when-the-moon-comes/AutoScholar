"""Report renderers for the four triggered-push paradigms.

Each renderer reads its paradigm artifact and writes a Markdown report to
reports/push_<paradigm>_<run_id>.md.  Reports are views, not sources of
truth — re-render by rerunning push, never edit by hand.
"""

from __future__ import annotations

import json
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _read_json(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _header(paradigm: str, run_id: str, domain: str, profile: dict, cold_start: bool) -> str:
    traits = profile.get("derived_traits", {})
    lines = [
        f"# Triggered Push: {paradigm} ({run_id})",
        "",
        f"- Domain: {domain}",
        f"- Generated against profile updated at: {profile.get('updated_at')}",
        f"- Window size: {len(profile.get('recent_reactions', []))}",
    ]
    if cold_start:
        lines.append("- Note: **first scan** — diversity prioritized over personalization.")
    else:
        lines.append(f"- Engaging axes from prior reactions: {traits.get('engaging_axes')}")
        lines.append(f"- Boring axes (deprioritized): {traits.get('boring_axes')}")
    lines += [
        "",
        "## How to use this report",
        "",
        "1. Read the cards in any order. Don't skim for the 'best' one.",
        "2. For each card, register a reaction. Bored is a valid reaction.",
        "3. Positive reactions require a one-line take (`--take`).",
        "4. Run `autoscholar trigger react --workspace <dir> --card-id <id> ...`.",
        "",
    ]
    return "\n".join(lines)


def render_controversy(workspace: Path, manifest: dict, run_id: str, profile: dict) -> Path:
    cards = _read_jsonl(workspace / manifest["artifacts"]["controversy_cards"])
    cold_start = len(profile.get("recent_reactions", [])) < 5
    body = [_header("controversy", run_id, manifest["domain"], profile, cold_start)]
    body.append("## Controversies\n")
    for card in cards:
        body.append(f"### `{card['card_id']}` — axis: {card['ai_diversity_axis']}\n")
        body.append(f"**Proposition.** {card['proposition']}\n")
        side_a = card["side_a"]
        side_b = card["side_b"]
        body.append(f"**Side A** — {side_a['claim']}")
        for paper in side_a.get("representative_papers", []):
            body.append(f"  - {paper.get('title')} ({paper.get('year', 'n/a')})")
        body.append(f"\n**Side B** — {side_b['claim']}")
        for paper in side_b.get("representative_papers", []):
            body.append(f"  - {paper.get('title')} ({paper.get('year', 'n/a')})")
        clash = card.get("last_clash") or {}
        if clash:
            body.append(
                f"\n**Last clash.** {clash.get('title')} ({clash.get('year')}): "
                f"{clash.get('challenge_summary', '')}"
            )
        body.append(f"\n*Why this is a real fight:* {card.get('ai_synthesis_note', '')}\n")
        body.append("_Reactions: `bored` | `spectate` | `want_to_argue` (take required)_\n")
    body.append("---\n")
    body.append(
        "When you've reacted to every card you formed an opinion about "
        "(including bored ones), consider running:\n\n"
        "- `autoscholar trigger relay --source-card <id> --target-paradigm cross-domain` "
        "to carry a `want_to_argue` reaction forward.\n"
        "- `autoscholar trigger push --paradigm failure-archive` for a different cut.\n"
    )
    out = workspace / "reports" / f"push_controversy_{run_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(body), encoding="utf-8")
    return out


def render_failure_archive(workspace: Path, manifest: dict, run_id: str, profile: dict) -> Path:
    entries = _read_jsonl(workspace / manifest["artifacts"]["failure_archive"])
    cold_start = len(profile.get("recent_reactions", [])) < 5
    body = [_header("failure-archive", run_id, manifest["domain"], profile, cold_start)]
    body.append("## Abandoned Directions\n")
    for entry in entries:
        body.append(f"### `{entry['card_id']}` — axis: {entry['ai_diversity_axis']}\n")
        body.append(
            f"**{entry['direction_name']}** — "
            f"peak {entry['peak_period']['start_year']}-{entry['peak_period']['end_year']}\n"
        )
        body.append("**Peak papers.**")
        for paper in entry.get("peak_papers", []):
            body.append(f"  - {paper['title']} ({paper['year']}, cites={paper.get('citation_count', 0)})")
        body.append(f"\n**Abandoned around.** {entry['abandonment'].get('year_estimate')}\n")
        body.append("**Reasons.**")
        for reason in entry["abandonment"].get("reasons", []):
            body.append(f"  - [{reason['category']}] {reason['reason']}")
        if entry.get("current_condition_changes"):
            body.append("\n**Now, that did not exist at peak.**")
            for change in entry["current_condition_changes"]:
                body.append(f"  - {change}")
        body.append(
            f"\n*Why genuinely abandoned, not absorbed:* {entry.get('ai_synthesis_note', '')}\n"
        )
        body.append("_Reactions: `still_holds` | `unsure` | `changed` (take required)_\n")
    out = workspace / "reports" / f"push_failure-archive_{run_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(body), encoding="utf-8")
    return out


def render_matrix(workspace: Path, manifest: dict, run_id: str, profile: dict) -> Path:
    matrix = _read_json(workspace / manifest["artifacts"]["matrix"])
    cold_start = len(profile.get("recent_reactions", [])) < 5
    body = [_header("matrix", run_id, manifest["domain"], profile, cold_start)]

    methods = matrix.get("dimensions", {}).get("methods", [])
    scenarios = matrix.get("dimensions", {}).get("scenarios", [])
    cells = {c["cell_id"]: c for c in matrix.get("cells", [])}

    body.append("## Dimensions\n")
    body.append("**Methods (mechanism-level).**")
    for m in methods:
        body.append(f"- `{m['id']}` {m['label']} — {m.get('ai_rationale', '')}")
    body.append("\n**Scenarios.**")
    for s in scenarios:
        marker = " *(non-standard)*" if s.get("is_non_standard") else ""
        body.append(f"- `{s['id']}` {s['label']}{marker} — {s.get('ai_rationale', '')}")

    body.append("\n## Density Grid\n")
    header_row = "| | " + " | ".join(s["label"] for s in scenarios) + " |"
    sep = "| --- |" + " --- |" * len(scenarios)
    body.append(header_row)
    body.append(sep)
    for m in methods:
        row = [f"**{m['label']}**"]
        for s in scenarios:
            cell = cells.get(f"{m['id']}x{s['id']}")
            row.append(f"`{cell['density']}`" if cell else "-")
        body.append("| " + " | ".join(row) + " |")

    body.append("\n## Void Notes (sparse and empty cells only)\n")
    for cell in matrix.get("cells", []):
        if cell.get("density") in {"sparse", "empty"}:
            body.append(f"### `{cell['cell_id']}` — axis: {cell.get('ai_diversity_axis')}\n")
            body.append(f"- Method × Scenario: {cell['method_id']} × {cell['scenario_id']}")
            body.append(f"- Query used: `{cell['query_used']}`")
            body.append(
                f"- Density: {cell['density']} "
                f"(papers={cell['paper_count']}, max_cites={cell['max_citations']})"
            )
            body.append(f"- Void note: {cell.get('ai_void_note', '')}\n")
            body.append("_Reactions: `irrelevant` | `obvious_void` | `curious` (take required)_\n")

    summary = matrix.get("ai_synthesis_summary")
    if summary:
        body.append("## AI's own reaction\n")
        body.append(summary + "\n")

    out = workspace / "reports" / f"push_matrix_{run_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(body), encoding="utf-8")
    return out


def render_cross_domain(workspace: Path, manifest: dict, run_id: str, profile: dict) -> Path:
    pairs = _read_jsonl(workspace / manifest["artifacts"]["cross_domain_pairs"])
    cold_start = len(profile.get("recent_reactions", [])) < 5
    body = [_header("cross-domain", run_id, manifest["domain"], profile, cold_start)]
    body.append("## Pairs\n")
    body.append(
        "*Cross-domain reactions have a long half-life. If a pair feels "
        "`partial`, log the reaction and revisit in 1-2 weeks; do not "
        "force an immediate take.*\n"
    )
    for pair in pairs:
        body.append(f"### `{pair['card_id']}` — axis: {pair['ai_diversity_axis']}\n")
        body.append(f"**Skeleton.** {pair['skeleton']}\n")
        home = pair["home_paper"]
        foreign = pair["foreign_paper"]
        body.append(f"**Home paper** ({home['field']}). {home['title']} ({home.get('year', 'n/a')})")
        body.append(f"**Foreign paper** ({foreign['field']}). {foreign['title']} ({foreign.get('year', 'n/a')})\n")
        body.append(f"**Isomorphism hypothesis.** {pair['isomorphism_hypothesis']}\n")
        body.append(f"**Likely break point.** {pair['likely_break_point']}\n")
        body.append(
            "_Reactions: `not_isomorphic` | `shallow` | `partial` (take required) | "
            "`deep` (take required)_\n"
        )
    out = workspace / "reports" / f"push_cross-domain_{run_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(body), encoding="utf-8")
    return out
