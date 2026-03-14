---
name: idea_creation
description: "Given a seed paper (title + abstract, or full text), generate structured innovation candidates for CS/AI research using two parallel thinking tracks: Context Substitution (break the paper's implicit deployment assumptions) and Insight Transfer (extract the paper's core intellectual discovery and ask where else that principle applies). Both tracks are run independently and merged into a unified idea card set. Integrates with the Semantic Scholar API for novelty verification. Outputs idea cards ready to use as paper motivation drafts."
---

# Idea Creation Skill

## Core Philosophy

A research paper can be a source of innovation in two fundamentally different ways.
This skill runs both simultaneously and merges the results.

### Track A — Context Substitution (场景替换)

Every paper is built on implicit assumptions about its deployment context:
who has the data, how it arrives, what the label space looks like, what constraints exist.
Break one of those assumptions and you get a new research problem in the same territory.

> PQFormer assumes training data is centralized → break it → federated segmentation

This track is **broad but can be mechanical** if run alone.
It answers: *"What other situations could this method serve?"*

### Track B — Insight Transfer (洞见迁移)

Every paper also contains at least one genuine intellectual discovery —
a finding that is counter-intuitive, non-obvious, or structurally generalizable.
That discovery is a transferable principle. Find where else it applies.

> PQFormer finds that restraining global attention improves spatial detail recovery →
> Where else does "less global modeling = better local precision" hold?
> → Dense prediction in remote sensing? Temporal boundary detection in video?

This track is **deeper and harder to fake**.
It answers: *"What truth did this paper reveal, and where else is that truth useful?"*

**The rule**: Track A without Track B produces safe, incremental ideas.
Track B without Track A misses obvious low-hanging fruit.
Both together produce a portfolio with range and depth.

---

## Inputs

The user provides one of:
- Paper title + abstract (minimum viable input)
- Paper title + abstract + methodology section
- Full paper PDF or `.md` file

Store the input as:
```
paper/seed_paper.md
```

---

## Workflow

### Step 0 — Workspace Setup

Create the working directory structure:

```
paper/
├── seed_paper.md                   # user input
├── parsed_paper.json               # Step 1
├── core_insights.json              # Step 1.5  ← Track B source
├── assumptions.json                # Step 2    ← Track A source
├── paradigm_gap_check.json         # Step 3
├── innovation_candidates.json      # Step 4    (both tracks merged)
├── novelty_verification.json       # Step 5
└── idea_cards.md                   # Step 6 final output
```

---

### Step 1 — Paper Parsing

**Goal**: Extract the paper's task, domain, methodology, and current problem formulation.

Produce `parsed_paper.json`:

```json
{
  "title": "string",
  "domain": "string — application domain, e.g. 'medical image segmentation'",
  "task": "string — fine-grained task, e.g. 'abdominal multi-organ segmentation', NOT just 'segmentation'",
  "input_data_type": "string — e.g. '2D CT slices', 'point cloud', 'time series'",
  "output_type": "string — e.g. 'pixel-wise class mask', 'bounding box', 'anomaly score'",
  "core_method": "string — main technical approach",
  "problem_formulation": "string — one sentence formal framing, e.g. 'fully-supervised closed-set segmentation on static 2D slices from a single imaging center'",
  "claimed_contribution": "string — what the paper says it contributes",
  "key_ablation_findings": "string — what the ablation studies revealed about which components matter and why"
}
```

**Instructions**:
- `task` must be specific enough that two different papers would not share the same string.
- `key_ablation_findings` is critical for Step 1.5 — fill it carefully even if not explicitly stated.

---

### Step 1.5 — Core Insight Extraction (洞见提炼)

**Goal**: Identify what is genuinely intellectually interesting about this paper —
not what it claims to contribute, but what it actually *discovered* or *demonstrated* that is non-obvious.

This step feeds Track B entirely. Do it carefully.

Read `parsed_paper.json` and reason through the following four questions.
Write your answers in `core_insights.json`.

**Question 1 — What is the most counter-intuitive finding?**

Look for results that go against the default assumption of "more is better":
- Does adding more of something (layers, attention, data, supervision) actually hurt?
- Does a simpler component outperform a complex one?
- Does restricting something (label space, receptive field, fusion points) improve quality?

Example: *PQFormer's ablation shows that adding MSF at deeper skip connections degrades performance.
The counter-intuitive finding is: selective, spatially-early fusion beats dense multi-scale fusion.*

**Question 2 — What structural principle does this finding reveal?**

Generalize the finding one level up.
Strip away the domain-specific language and express the principle abstractly.

Example: *"In dense prediction tasks where fine spatial detail must be recovered,
global feature mixing is most useful at high-resolution early stages
and becomes redundant or harmful at lower-resolution deeper stages."*

**Question 3 — What conditions must hold for this principle to apply elsewhere?**

List the structural prerequisites — the features a new task must have
for this principle to transfer. Be precise.

Example prerequisites for the above principle:
- The output requires spatially precise predictions (not just global labels)
- There is a resolution hierarchy (encoder-decoder or similar)
- Global context is useful but not the primary bottleneck

**Question 4 — What design choices in this paper are counter-intuitive but effective?**

Look at methodology choices the authors made that go against the field's dominant trends.
These are often the most transferable ideas because they represent genuine departures.

Example: *PQFormer uses a pure convolutional decoder while the field trends toward Transformer decoders.
The choice is justified by ablation. The implicit claim: for spatial reconstruction,
local refinement is more important than global token interaction.*

Output format for `core_insights.json`:

```json
{
  "insights": [
    {
      "id": "I1",
      "counter_intuitive_finding": "string — what the paper showed that goes against defaults",
      "abstract_principle": "string — the generalized structural truth behind the finding",
      "transfer_prerequisites": [
        "string — condition 1 a new task must satisfy",
        "string — condition 2"
      ],
      "candidate_transfer_domains": [
        "string — domain/task where prerequisites plausibly hold, with brief reasoning"
      ]
    }
  ],
  "counter_intuitive_design_choices": [
    {
      "id": "D1",
      "choice": "string — what the paper did differently from the field trend",
      "why_it_works": "string — the paper's implicit or explicit justification",
      "transferable_claim": "string — the generalizable design principle this implies"
    }
  ]
}
```

**Quality bar**: A paper with a real contribution should yield 2–4 insights and 1–3 design choices.
If you find only 1 insight, re-read the ablation section and the discussion — that is where genuine findings hide.

---

### Step 2 — Assumption Mining (Track A Source)

**Goal**: Surface every implicit assumption the paper makes about its deployment context.

Read `parsed_paper.json` and examine the paper through these lenses.
These are thinking prompts, not a form to fill:

```
LABEL SPACE LENS
  - Are all possible output categories known at training time?
  - Can new categories appear at test/deployment time?
  - Is the output space assumed to be exhaustive and mutually exclusive?

DATA AVAILABILITY LENS
  - Is full pixel/sample-level annotation assumed?
  - Is the dataset assumed to be clean, balanced, and complete before training starts?
  - Is label noise assumed to be zero?

TEMPORAL / DEPLOYMENT LENS
  - Is the data assumed to arrive all at once (offline)?
  - Is the model assumed to never update after deployment?
  - Is the data distribution assumed stationary over the deployment lifetime?

DISTRIBUTION / DOMAIN LENS
  - Are training and test distributions assumed identical?
  - Is a single imaging center / sensor type / acquisition protocol assumed?
  - Is cross-site or cross-device generalization out of scope?

SAMPLE STRUCTURE LENS
  - Is each sample assumed to contain exactly one target class?
  - Are samples assumed independent (no spatial, temporal, or relational structure)?
  - Is class frequency assumed to be approximately balanced?

INFERENCE MODE LENS
  - Is inference assumed to be single-pass and fully automatic?
  - Is there no mechanism for the model to express uncertainty or abstain?
  - Is human feedback during inference excluded?

RESOURCE / DEPLOYMENT CONSTRAINT LENS
  - Is centralized data access assumed?
  - Are computational resources assumed to be unconstrained at inference?
  - Is privacy of training data assumed to be a non-issue?

TASK GRANULARITY LENS
  - Is the task operating at a coarser granularity than the application actually needs?
  - Would finer-grained outputs (e.g. localization vs classification) be more useful?
```

Output format for `assumptions.json`:

```json
{
  "assumptions": [
    {
      "id": "A1",
      "lens": "LABEL SPACE",
      "assumption": "All organ classes are known and fixed; no new anatomical targets are added post-deployment.",
      "how_it_manifests": "Fixed softmax output head with no rejection or extension mechanism.",
      "implicit_or_explicit": "implicit"
    }
  ]
}
```

**Quality bar**: 8–15 assumptions. Fewer than 6 means you missed the implicit ones — go deeper.

---

### Step 3 — Paradigm Gap Check (Safety Net for Track A)

**Goal**: Ensure no standard paradigm axis was missed by assumption mining.

Check `assumptions.json` against each axis below.
If an axis is uncovered AND plausibly relevant to this paper's domain, add a corresponding assumption.

| Axis | Key Question |
|------|-------------|
| Label space | Closed-set → open-set / zero-shot / few-shot / fine-grained |
| Supervision | Fully supervised → semi / self / weakly / noisy labels |
| Temporal | Static → incremental / continual / online learning |
| Distribution | Single-domain → domain adaptation / generalization / federated |
| Sample structure | Single-label → multi-label / hierarchical / relational |
| Task granularity | Classification → detection → segmentation → grounding |
| Inference mode | Single-pass → interactive / human-in-the-loop / uncertainty-aware |
| Deployment | Cloud → edge / lightweight / privacy-preserving |
| Data volume | Large-scale → long-tail / extreme few-shot / zero annotation |

Produce `paradigm_gap_check.json`:

```json
{
  "covered_axes": ["label_space", "temporal", "distribution"],
  "uncovered_axes": [
    {
      "axis": "sample_structure",
      "question": "Can multiple organs or lesions with overlapping or co-occurring conditions appear in the same scan?",
      "suggested_assumption_to_add": "Each anatomical target is assumed to be spatially distinct and independently segmentable."
    }
  ]
}
```

Append any new assumptions to `assumptions.json` before proceeding to Step 4.

---

### Step 4 — Innovation Candidate Generation (Dual-Track)

**Goal**: Generate candidates from BOTH Track A and Track B independently, then merge.

Produce `innovation_candidates.json` with a `track` field on every candidate.

---

#### Track A — Context Substitution Candidates

For each assumption in `assumptions.json`, generate one candidate by breaking that assumption.

For each candidate, reason through:
1. What changes structurally when this assumption is broken?
2. Why does the real-world application domain actually need this change?
3. What is the new formal problem formulation?
4. What is the core technical challenge that needs solving?
5. What would a concrete paper title look like?

Prune a Track A candidate if:
- Breaking the assumption does not create a coherent research problem
- The direction is purely an engineering optimization with no algorithmic novelty
- The broken assumption is too peripheral to affect the paper's core contribution

Target: 4–8 Track A candidates after pruning.

---

#### Track B — Insight Transfer Candidates

For each insight in `core_insights.json`, generate candidates by asking:
**"Where else does this principle apply, and has anyone applied it there yet?"**

For each `candidate_transfer_domain` in each insight, evaluate:
1. Do the `transfer_prerequisites` actually hold in this domain? Eliminate those that do not.
2. If prerequisites hold, what would a paper look like that applies this principle there?
3. What is the new problem formulation?
4. What is the core technical challenge?
5. What would a concrete paper title look like?

Also generate candidates from `counter_intuitive_design_choices`:
- The `transferable_claim` from each design choice is a hypothesis.
- Find a domain where this hypothesis has not been tested.
- That gap is a candidate.

Prune a Track B candidate if:
- The transfer prerequisites genuinely do not hold in the target domain
- The principle has already been applied in that domain (will be confirmed in Step 5)
- The candidate amounts to "apply method X to domain Y" without structural justification

Target: 3–6 Track B candidates after pruning.

---

#### Convergence Detection

After generating both track lists, check for pairs where a Track A and a Track B candidate
independently arrived at the same target domain.
Mark these with `"convergence_with": "CA3"` on the Track B entry.
Convergence is a strong novelty signal — the territory is compelling from two different angles.

---

#### Merged Output Format

```json
{
  "track_a_candidates": [
    {
      "id": "CA1",
      "track": "A",
      "source_assumption_ids": ["A1"],
      "assumption_broken": "string",
      "innovation_direction": "string",
      "real_world_motivation": "string — why the application domain actually needs this",
      "new_problem_formulation": "string",
      "core_technical_challenge": "string",
      "candidate_title": "string",
      "novelty_search_queries": ["string", "string", "string"]
    }
  ],
  "track_b_candidates": [
    {
      "id": "CB1",
      "track": "B",
      "source_insight_id": "I1",
      "principle_being_transferred": "string — the abstract principle from core_insights.json",
      "target_domain": "string — where this principle is being applied",
      "transfer_justification": "string — which prerequisites hold and why",
      "innovation_direction": "string",
      "real_world_motivation": "string",
      "new_problem_formulation": "string",
      "core_technical_challenge": "string",
      "candidate_title": "string",
      "convergence_with": "CA3 or null",
      "novelty_search_queries": ["string", "string", "string"]
    }
  ]
}
```

---

### Step 5 — Novelty Verification via Semantic Scholar

**Goal**: For every candidate (both tracks), verify that the (task × paradigm/principle) combination is sparse.

Use `SemanticScholarApi/api.py`:

```python
for candidate in all_candidates:
    for query in candidate["novelty_search_queries"]:
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
      "candidate_id": "CA1",
      "track": "A",
      "total_papers_found": 4,
      "recent_papers_2022_plus": 2,
      "sparsity_rating": "HIGH",
      "top_existing_papers": [
        {
          "title": "...",
          "year": 2023,
          "citationCount": 8,
          "venue": "MICCAI"
        }
      ],
      "verdict": "PROCEED",
      "note": "string — qualitative assessment: are found papers actually on this problem?"
    }
  ]
}
```

Sparsity rating rules:
- `HIGH` (< 5 directly relevant papers) → PROCEED
- `MEDIUM` (5–20 papers) → INVESTIGATE — does existing work leave a clear gap?
- `LOW` (> 20 papers) → DEPRIORITIZE — only keep if a very specific niche remains open

**Special rule for Track B**: When verifying Track B candidates, also run
a `principle_level_search` — queries that specifically probe whether the structural
principle (not just the task) has been applied in the target domain.
A crowded task-level result does not invalidate a Track B candidate if
the existing papers are not using this principle.

---

### Step 6 — Idea Card Generation

**Goal**: Produce `idea_cards.md` with clearly labeled Track A and Track B cards.

Include only candidates with sparsity `HIGH` or `MEDIUM`. Label each card with its track.

---

**Track A card format**:

````markdown
---

## Idea Card [Track A] — CA1

**Innovation Direction**: [direction name]
**Type**: Context Substitution — assumption broken: [axis name]

**Assumption Broken**
> "[exact assumption text]"

**Why the Real World Needs This**
[2–3 sentences grounded in the specific application domain.
Not "it's an interesting direction" — explain the concrete operational gap.]

**New Problem Formulation**
[Old formulation] → [New formulation]

**Core Technical Challenge**
[The primary algorithmic problem that needs solving. Be specific.]

**Literature Density**: [★ rating] ([N] papers found)
**Verdict**: [PROCEED / INVESTIGATE]

**Candidate Paper Title**
> "[Title]"

```json
{
  "candidate_id": "CA1",
  "track": "A",
  "status": "PROCEED",
  "autoscolar_queries": ["query1", "query2"],
  "seed_paper_ids": ["paperId_xxx"]
}
```

---
````

**Track B card format**:

````markdown
---

## Idea Card [Track B] — CB1

**Innovation Direction**: [direction name]
**Type**: Insight Transfer — principle transferred to [target domain]

**Principle Being Transferred**
> "[Abstract principle from core_insights.json]"

**Why This Principle Applies Here**
[Explain which transfer prerequisites hold in the target domain and why.
This is the intellectual core of the card — be rigorous, not hand-wavy.]

**What the Seed Paper Proved**
[One sentence: what the seed paper demonstrated that makes this transfer credible.]

**New Problem Formulation**
[What a paper in the target domain would need to set up and solve.]

**Core Technical Challenge**
[What needs to be solved to realize this transfer.]

**Literature Density**: [★ rating] ([N] papers found)
**Verdict**: [PROCEED / INVESTIGATE]

**Candidate Paper Title**
> "[Title]"

```json
{
  "candidate_id": "CB1",
  "track": "B",
  "status": "PROCEED",
  "autoscolar_queries": ["query1", "query2"],
  "seed_paper_ids": ["paperId_xxx"]
}
```

---
````

**Convergence section** (include if any Track A + Track B pair share a target domain):

```markdown
## Convergence Signals

The following pairs independently arrived at the same target domain from different reasoning paths.
Convergence means the territory is compelling from both a deployment-gap angle (Track A)
and a structural-principle angle (Track B).

| Track A | Track B | Shared Target Domain | Why It Converges |
|---------|---------|----------------------|-----------------|
| CA3 | CB2 | Video temporal segmentation | A: static distribution assumption broken; B: restrained attention principle transfers |
```

**Summary table** at the end:

```markdown
## Summary Table

| ID | Track | Direction | Sparsity | Verdict |
|----|-------|-----------|----------|---------|
| CA1 | A | Open-set segmentation | ★☆☆☆☆ | ✅ Proceed |
| CA2 | A | Continual domain adaptation | ★★☆☆☆ | ✅ Proceed |
| CB1 | B | Restrained attention → video dense prediction | ★★☆☆☆ | ✅ Proceed |
| CB2 | B | Conv decoder principle → point cloud segmentation | ★★★☆☆ | ⚠️ Investigate |
```

---

## Handoff to AutoScholar Citation Pipeline

After the user selects a card to develop:

- `candidate_title` → seed for `search_keyword_prep.md`
- `autoscolar_queries` → initial query set for `semantic_scholar_search.yaml`
- `seed_paper_ids` from novelty verification → seed papers for `recommendation_auto_correct.py`

---

## Example Invocation

```
User provides: paper title + abstract (or full paper)

Agent workflow:
1. Write input to paper/seed_paper.md
2. Step 1   → paper/parsed_paper.json
3. Step 1.5 → paper/core_insights.json          ← Track B source
4. Step 2   → paper/assumptions.json            ← Track A source
5. Step 3   → paper/paradigm_gap_check.json, update assumptions.json if needed
6. Step 4   → paper/innovation_candidates.json  ← both tracks, convergence flagged
7. Step 5   → paper/novelty_verification.json
8. Step 6   → paper/idea_cards.md
9. Present idea_cards.md to user
```

---

## Quality Checklist (Agent Self-Review Before Presenting Output)

**Track A**
- [ ] At least 8 assumptions mined in Step 2
- [ ] All 9 paradigm axes checked in Step 3
- [ ] Each Track A card has real-world motivation grounded in the application domain (not generic)

**Track B**
- [ ] At least 2 core insights extracted in Step 1.5
- [ ] Each Track B card explicitly states which transfer prerequisites hold and why
- [ ] No Track B card amounts to "apply X to Y" without structural justification
- [ ] Track B novelty verification includes principle-level search queries

**Both tracks**
- [ ] Novelty verification ran via Semantic Scholar for every candidate (not guessed)
- [ ] LOW sparsity candidates excluded or marked DEPRIORITIZE
- [ ] Each card has a concrete paper title
- [ ] Convergence section present if any Track A / Track B pairs share a target domain
- [ ] Summary table present and accurate
- [ ] Each card contains the machine-readable JSON block for AutoScholar handoff
