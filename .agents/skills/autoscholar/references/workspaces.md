# Workspaces

AutoScholar v2 uses explicit workspaces. Each workspace contains:

- `workspace.yaml`
- `inputs/`
- `configs/`
- `artifacts/`
- `reports/`

Key rules:

- The manifest is the only path source of truth.
- Workspaces can live outside the repo.
- `artifacts/*.jsonl` and `artifacts/*.json` are authoritative.
- `reports/*.md` are rendered outputs.

Use:

```powershell
autoscholar workspace init <dir> --template citation-paper|idea-evaluation --reports-lang zh|en
autoscholar workspace doctor --workspace <dir>
```
