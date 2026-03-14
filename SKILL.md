---
name: idea_creation
description: "Given a seed paper (title + abstract, or full text), generate structured paradigm-shift innovation candidates for CS/AI research. Uses assumption decomposition as the primary discovery engine, with a paradigm axis checklist as a safety net. Outputs idea cards ready to use as paper motivation drafts. Integrates with the Semantic Scholar API for novelty verification."
---

# Idea Creation Skill

## Core Philosophy

Every research paper is built on a stack of **implicit assumptions** the authors never questioned.
Innovation happens when you identify one of those assumptions and deliberately break it.

This skill does NOT start from a fixed vocabulary of paradigms.
It starts by asking: **"What does this paper silently take for granted?"**
The paradigm axis checklist runs afterward as a safety net — to catch anything the free-form mining missed.

This produces ideas that are:
- **Grounded**: directly derived from the seed paper's own problem structure
- **Open-ended**: not limited to pre-enumerated paradigm slots
- **Verifiable**: confirmed sparse via Semantic Scholar before being surfaced

---

## Inputs

The user provides one of:
- Paper title + abstract (minimum viable input)
- Paper title + abstract + key methodology section
- A `.txt` or `.md` file containing the above

Store the input as:
```
paper/seed_paper.md
```

---

## Workflow

### Step 0 — Workspace Setup

Create the working directory structure if it does not exist:

```
paper/
├── seed_paper.md                  # user input
├── parsed_paper.json              # output of Step 1
├── assumptions.json               # output of Step 2
├── paradigm_gap_check.json        # output of Step 3
├── innovation_candidates.json     # output of Step 4
├── novelty_verification.json      # output of Step 5
└── idea_cards.md                  # final output
```

---

### Step 1 — Paper Parsing

**Goal**: Extract the paper's task, domain, methodology, and current problem formulation.

Analyze the seed paper and produce `parsed_paper.json` with this schema:

```json
{
  "title": "string",
  "domain": "string — application domain, e.g. 'industrial visual inspection', 'medical imaging'",
  "task": "string — fine-grained task name, e.g. 'partial discharge pattern classification', NOT just 'image classification'",
  "input_data_type": "string — e.g. ' 2D spectrogram images', 'point cloud', 'time series'",
  "output_type": "string — e.g. 'multi-class label', 'bounding box', 'anomaly score'",
  "core_method": "string — main technical approach used",
  "problem_formulation": "string — one sentence describing how the problem is formally set up",
  "claimed_contribution": "string — what the paper says it contributes"
}
```

**Instructions for this step**:
- `task` must be specific. If the paper says "image classification", look at the data and domain to infer the real task.
- `problem_formulation` should capture the mathematical/structural framing, e.g. "closed-set multi-class classification over a fixed label space" or "supervised detection with full annotation".

---

### Step 2 — Assumption Mining (Core Step)

**Goal**: Surface every assumption the paper makes — explicit and implicit.

This is the most important step. Read `parsed_paper.json` and produce `assumptions.json`.

For each assumption, think across these **lenses** (these are lenses to guide thinking, NOT a checklist to fill mechanically):

```
LABEL SPACE LENS
  - What does the paper assume about the set of possible classes/categories?
  - Are all classes known at training time?
  - Can new classes appear at test time or after deployment?

DATA AVAILABILITY LENS
  - What does the paper assume about annotation quality and quantity?
  - Is full supervision assumed? Is the label noise level assumed to be zero?
  - Is the full dataset assumed to be available upfront?

TEMPORAL / DEPLOYMENT LENS
  - Does the paper assume data arrives all at once or in a stream?
  - Does it assume the model never needs to update after deployment?
  - Does it assume the data distribution is stationary?

DISTRIBUTION / DOMAIN LENS
  - Does the paper assume train and test data come from the same distribution?
  - Does it assume a single source domain?
  - Does it assume consistent image quality, sensor type, or acquisition conditions?

SAMPLE STRUCTURE LENS
  - Does the paper assume one label per sample (single-label)?
  - Does it assume samples are independent (no relationships between them)?
  - Does it assume balanced class frequency?

INFERENCE MODE LENS
  - Does the paper assume one-shot, single-pass inference?
  - Does it assume no human feedback during inference?
  - Does it assume the model is certain about its predictions?

RESOURCE / DEPLOYMENT CONSTRAINT LENS
  - Does the paper assume abundant compute at inference time?
  - Does the paper assume centralized data access?
  - Does it assume cloud deployment, ignoring edge/IoT constraints?

TASK GRANULARITY LENS
  - Does the paper stop at a coarser granularity when finer granularity is meaningful?
  - For example: does it classify when localization would be more useful?
```

Output format for `assumptions.json`:

```json
{
  "assumptions": [
    {
      "id": "A1",
      "lens": "LABEL SPACE",
      "assumption": "All discharge pattern types are known at training time and no unknown types appear at test time.",
      "how_it_manifests": "The model uses softmax over a fixed number of output classes with no rejection mechanism.",
      "implicit_or_explicit": "implicit"
    },
    {
      "id": "A2",
      "lens": "TEMPORAL",
      "assumption": "The full dataset is collected and annotated before training begins; no new data arrives after deployment.",
      "how_it_manifests": "Standard offline training loop with no online update mechanism.",
      "implicit_or_explicit": "implicit"
    }
  ]
}
```

**Quality bar**: A good run should surface 8–15 assumptions. If you find fewer than 6, go deeper — most of the valuable ones are implicit.

---

### Step 3 — Paradigm Gap Check (Safety Net)

**Goal**: Cross-check the assumptions found in Step 2 against a standard paradigm axis list. Flag any axes that were NOT covered by the assumption mining.

This step exists to catch blind spots — it does NOT replace Step 2.

Check against these axes:

| Axis | Key Question |
|------|-------------|
| Label space | Closed-set → open-set / zero-shot / few-shot / fine-grained |
| Supervision | Fully supervised → semi / self / weakly / noisily supervised |
| Temporal | Static → incremental / continual / online learning |
| Distribution | Single-domain → domain adaptation / generalization / federated |
| Sample structure | Single-label → multi-label / hierarchical label / instance relationships |
| Task granularity | Classification → detection → segmentation → grounding |
| Inference mode | Single-pass → interactive / human-in-the-loop / uncertainty-aware |
| Deployment | Cloud → edge / lightweight / privacy-preserving (federated) |
| Data volume | Large-scale → long-tail / extreme few-shot / zero annotation |

Produce `paradigm_gap_check.json`:

```json
{
  "covered_axes": ["label_space", "temporal"],
  "uncovered_axes": [
    {
      "axis": "sample_structure",
      "question": "Does this task ever involve samples with multiple co-occurring fault types?",
      "suggested_assumption_to_add": "Each sample contains only one fault type — multi-fault scenarios are excluded."
    }
  ]
}
```

If uncovered axes suggest meaningful assumptions, add them to `assumptions.json` as additional entries before proceeding.

---

### Step 4 — Innovation Candidate Generation

**Goal**: For each assumption (or small group of related assumptions), generate one concrete innovation direction by "breaking" that assumption.

Read `assumptions.json` and produce `innovation_candidates.json`.

For each candidate, reason through:
1. **What changes** when this assumption is broken
2. **Why the real world actually needs** this change (does the application domain demand it?)
3. **What the new problem formulation** looks like
4. **What the core technical challenge** becomes
5. **A candidate paper title** to make the direction concrete

Output format:

```json
{
  "candidates": [
    {
      "id": "C1",
      "source_assumption_ids": ["A1"],
      "assumption_broken": "All classes are known at training time",
      "innovation_direction": "Open-set recognition for industrial partial discharge patterns",
      "real_world_motivation": "In real industrial deployment, new discharge pattern types emerge as equipment ages or degrades in novel ways. A deployed classifier must detect and flag unknown types rather than misclassifying them into known categories.",
      "new_problem_formulation": "The model must classify known discharge types AND reject/flag samples belonging to unknown types not seen during training.",
      "core_technical_challenge": "Defining a calibrated decision boundary between known-class regions and the open space; avoiding overconfident predictions on unknown inputs.",
      "candidate_title": "Open-Set Recognition for Industrial Partial Discharge Pattern Classification",
      "novelty_search_queries": [
        "open-set recognition partial discharge",
        "open-set industrial fault classification",
        "unknown class rejection industrial inspection"
      ]
    }
  ]
}
```

**Pruning rules** — drop a candidate if:
- The broken assumption doesn't create a coherent new research problem
- The direction is purely an engineering concern with no algorithmic novelty (e.g. "run it faster")
- The assumption is so minor that breaking it doesn't change the paper's core contribution

Target: 5–10 candidates after pruning.

---

### Step 5 — Novelty Verification via Semantic Scholar

**Goal**: For each candidate, check whether this (task × paradigm) combination is sparse in the literature.

Use the existing Semantic Scholar API (`SemanticScholarApi/api.py`) to run the search queries from each candidate's `novelty_search_queries` field.

```python
# Run this for each candidate C in innovation_candidates.json
for query in C["novelty_search_queries"]:
    results = api.search(
        query,
        limit=15,
        fields=["paperId", "title", "year", "citationCount", "venue", "abstract"]
    )
```

Produce `novelty_verification.json`:

```json
{
  "verifications": [
    {
      "candidate_id": "C1",
      "total_papers_found": 3,
      "recent_papers_2022_plus": 1,
      "sparsity_rating": "HIGH",
      "top_existing_papers": [
        {
          "title": "...",
          "year": 2023,
          "citationCount": 12,
          "venue": "IEEE TII"
        }
      ],
      "verdict": "PROCEED — very sparse, high novelty potential",
      "note": "1 tangentially related paper found but uses different methodology and different industrial domain"
    }
  ]
}
```

Sparsity rating rules:
- `HIGH` (< 5 directly relevant papers): strong novelty signal → PROCEED
- `MEDIUM` (5–20 papers): meaningful gap may still exist, check if existing work is strong → INVESTIGATE
- `LOW` (> 20 papers): crowded space → DEPRIORITIZE unless a clear gap in existing work exists

---

### Step 6 — Idea Card Generation

**Goal**: Produce human-readable `idea_cards.md` that a researcher can directly use as motivation drafts.

Only include candidates with sparsity rating `HIGH` or `MEDIUM` (after investigation).

Format each card as:

```markdown
---

## Idea Card #1

**Innovation Direction**: Open-Set Recognition for Industrial Partial Discharge Classification

**Assumption Broken**
> "All discharge pattern types are known at training time."

**Why the Real World Needs This**
Industrial partial discharge monitoring systems are deployed for years on aging equipment.
New discharge signatures emerge as insulation degrades in previously unseen ways.
A classifier that silently assigns unknown patterns to known classes provides dangerous false confidence.
The deployment reality demands rejection of unknowns — not forced categorization.

**New Problem Formulation**
Closed-set multi-class classification → Open-set recognition with unknown-class rejection.
The model must partition its input space into: known classes (classified) + open space (rejected/flagged).

**Core Technical Challenge**
- Defining a principled decision boundary enclosing known-class regions
- Avoiding overconfident softmax scores on out-of-distribution inputs
- Evaluating both closed-set accuracy AND open-set rejection performance

**Literature Density**: ★☆☆☆☆ Very sparse (3 papers found)
**Recommended next step**: Proceed — run full literature review using AutoScholar citation pipeline

**Candidate Paper Title**
> "Open-Set Recognition for Industrial Partial Discharge Pattern Classification via [Your Method]"

---
```

At the end of `idea_cards.md`, add a summary table:

```markdown
## Summary Table

| # | Direction | Assumption Broken | Sparsity | Recommended |
|---|-----------|------------------|----------|-------------|
| 1 | Open-set recognition | Fixed label space | ★☆☆☆☆ | ✅ Proceed |
| 2 | Class-incremental learning | Static dataset | ★★☆☆☆ | ✅ Proceed |
| 3 | Multi-label fault classification | Single-label assumption | ★★★☆☆ | ⚠️ Investigate |
```

---

## Handoff to AutoScholar Citation Pipeline

Once the user selects an idea card to develop further, the idea card maps directly onto the AutoScholar input format:

- `candidate_title` → seed for `search_keyword_prep.md`
- `novelty_search_queries` → initial query set for `semantic_scholar_search.yaml`
- `top_existing_papers` from novelty verification → seed papers for `recommendation_auto_correct.py`

This means the output of this skill is the **upstream input** to the existing AutoScholar citation workflow.

---

## Example Invocation

```
User provides: paper title + abstract of their seed paper

Agent workflow:
1. Write content to paper/seed_paper.md
2. Run Step 1 → produce paper/parsed_paper.json
3. Run Step 2 → produce paper/assumptions.json  
4. Run Step 3 → produce paper/paradigm_gap_check.json, update assumptions.json if needed
5. Run Step 4 → produce paper/innovation_candidates.json
6. Run Step 5 → call SemanticScholarApi, produce paper/novelty_verification.json
7. Run Step 6 → produce paper/idea_cards.md
8. Present idea_cards.md to user
```

---

## Quality Checklist (Agent Self-Review Before Presenting Output)

Before presenting `idea_cards.md`, verify:

- [ ] At least 8 assumptions were mined in Step 2
- [ ] All 9 paradigm axes were checked in Step 3
- [ ] Each candidate has a real-world motivation grounded in the application domain (not just "it's an interesting research direction")
- [ ] Novelty verification was actually run via Semantic Scholar (not guessed)
- [ ] Candidates with LOW sparsity are excluded or clearly marked DEPRIORITIZE
- [ ] Each idea card contains a concrete candidate paper title
- [ ] The summary table is present and accurate
