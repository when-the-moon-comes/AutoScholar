# DNA Profile

The DNA profile is the **only** persistent state across runs. Read it
before every `push`, update it after every `react`.

## File location

`<workspace>/artifacts/dna_profile.json`

## Schema

```json
{
  "schema_version": "1",
  "updated_at": "ISO-8601",
  "rolling": {
    "max_count": 30,
    "max_age_days": 90,
    "policy": "intersection"
  },
  "seed_papers": [
    {
      "paper_id": "string",
      "title": "string",
      "user_note": "one-line reason the user gave",
      "added_at": "ISO-8601"
    }
  ],
  "recent_reactions": [
    {
      "reaction_id": "r_<sha8>",
      "captured_at": "ISO-8601",
      "paradigm": "controversy | failure-archive | matrix | cross-domain",
      "card_id": "string",
      "card_summary": "<= 200 chars; the proposition or pairing the user reacted to",
      "card_diversity_axis": "string; copied from the card",
      "reaction": "string; paradigm-specific enum, see below",
      "user_take": "string or null; required for positive reactions",
      "source_run_id": "string"
    }
  ],
  "derived_traits": {
    "engaging_keywords": [["interpretab", 4], ["scenario", 3]],
    "boring_keywords": [["transformer", 5]],
    "engaging_axes": [["mechanism_level", 3]],
    "boring_axes": [["scope_level", 2]],
    "preferred_paradigm": "controversy | ... | null",
    "computed_at": "ISO-8601"
  }
}
```

## Reaction enums per paradigm

- `controversy`: `bored | spectate | want_to_argue`
- `failure-archive`: `still_holds | changed | unsure`
- `matrix`: `obvious_void | curious | irrelevant`
- `cross-domain`: `not_isomorphic | shallow | partial | deep`

**Positive reactions** (require `user_take`): `want_to_argue`,
`changed`, `curious`, `partial`, `deep`.

**Boring/dismissive reactions** (do NOT require `user_take` but must
still be recorded): `bored`, `irrelevant`, `not_isomorphic`,
`still_holds`.

**Ambiguous reactions** (`spectate`, `unsure`, `shallow`) are recorded
without a take but contribute weight 0.5 to derived traits.

## Rolling window policy

The window is the **intersection** of two cutoffs (whichever excludes
more):

- Last `max_count` reactions by `captured_at`.
- All reactions with `captured_at` within `max_age_days`.

This prevents both "stale taste from 6 months ago dominates" and "one
heavy push session erases the prior month's signal".

The `reactions.jsonl` log file is **append-only and never trimmed**.
The rolling window only governs which reactions feed `derived_traits`.

## Derived traits computation

Pure-statistics, no LLM. Recompute on every `react`. Algorithm:

```
engaging_pool = [r for r in window if r.reaction in POSITIVE_REACTIONS]
boring_pool   = [r for r in window if r.reaction in BORING_REACTIONS]

engaging_keywords = top_k(
    word_freq(r.card_summary + " " + (r.user_take or "") for r in engaging_pool),
    k=10,
    stopwords=DOMAIN_STOPWORDS,
)
boring_keywords = top_k(
    word_freq(r.card_summary for r in boring_pool),
    k=10,
    stopwords=DOMAIN_STOPWORDS,
)

engaging_axes = freq(r.card_diversity_axis for r in engaging_pool)
boring_axes   = freq(r.card_diversity_axis for r in boring_pool)

preferred_paradigm = paradigm with highest positive_count / total_count ratio,
                     or null if total < 5.
```

`DOMAIN_STOPWORDS` lives in `scripts/profile_stopwords.py` and starts
with the AutoScholar default stopword set; users may extend it.

## How `push` consumes the profile

When generating cards, AI is given:

1. The full `seed_papers` list with user notes.
2. `derived_traits.engaging_keywords` and `engaging_axes` as
   "lean toward these".
3. `derived_traits.boring_keywords` and `boring_axes` as
   "do not waste card slots on these".
4. The last 5 `recent_reactions` verbatim (with takes), as concrete
   examples of what landed.

This composition keeps recent context concrete (not just statistics)
while still bounded.

## Cold-start behavior

Until the user has logged 5 reactions total, `derived_traits` returns
empty arrays and `preferred_paradigm = null`. The first run is always
DNA-thin; the skill should make this explicit in the report header
("first scan — diversity prioritized over personalization").
