# Citation Workflow Reference

## Inputs

- `artifacts/claims.jsonl`
- `artifacts/queries.jsonl`
- `configs/search.yaml`
- `configs/recommendation.yaml`
- `configs/citation_rules.yaml`

## Primary Outputs

- `artifacts/search_results.raw.jsonl`
- `artifacts/search_results.deduped.jsonl`
- `artifacts/query_reviews.json`
- `artifacts/recommendation_corrections.jsonl`
- `artifacts/selected_citations.jsonl`
- `artifacts/references.bib`

## Notes

- Use prescreen to decide whether a query set is usable.
- Use correction only when weak or mixed retrieval makes it worthwhile.
- Use shortlist as the claim-level recommendation layer.
- Render Markdown only after structured artifacts are in place.
