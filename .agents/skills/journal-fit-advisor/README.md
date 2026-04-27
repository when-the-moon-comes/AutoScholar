# Journal Fit Advisor

This skill adds a paper-framing workflow to AutoScholar for cases where:

- the method is already fixed
- the main experiments are already done
- the remaining question is how to position the paper for 1-3 target journals

Use the repo CLI:

```powershell
autoscholar jfa init --working-title "My Paper"
autoscholar jfa run --paper-id <paper_id> --input path\to\input.md
```

For draft-reframing mode:

```powershell
autoscholar jfa phase0 --paper-id <paper_id> --draft-pdf path\to\draft.pdf --input path\to\input.md
```

The `--input` file should follow `input_template.md`.
