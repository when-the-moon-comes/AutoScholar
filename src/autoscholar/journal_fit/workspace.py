from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from autoscholar.citation.common import slugify


INPUT_TEMPLATE = """# Paper Materials Submission

## 1. Paper Identity
- working_title:
- domain:
- task:

## 2. Algorithm (fixed, not to be changed by this module)

### Input

### Method / Pipeline

### Output

### Key Novelty Claim(s) (作者自认)
- novelty_1:
- novelty_2:

## 3. Experiments (fixed facts)

### Exp-1: Main experiment
- purpose:
- datasets:
- baselines:
- metrics:
- key_results:
- side_findings:

## 4. Target Journals
- journal_1:  priority: high

## 5. Existing Drafts (optional)
- current_abstract:
- current_intro_p1:
- figure_1_caption:
- prior_rejection_feedback:
"""


def derive_paper_id(working_title: str) -> str:
    normalized = working_title.strip() or "untitled-paper"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    slug = slugify(normalized) or "untitled-paper"
    return f"{slug}-{digest}"


class JournalFitWorkspace:
    def __init__(self, base_dir: Path, paper_id: str):
        self.base_dir = base_dir.resolve()
        self.paper_id = paper_id
        self.root = (self.base_dir / ".autoscholar" / paper_id).resolve()

    def ensure_layout(self) -> "JournalFitWorkspace":
        for directory in (
            self.root,
            self.raw_dir,
            self.figures_dir,
            self.journals_dir,
            self.narratives_dir,
            self.skeletons_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def figures_dir(self) -> Path:
        return self.raw_dir / "figures"

    @property
    def journals_dir(self) -> Path:
        return self.root / "journals"

    @property
    def narratives_dir(self) -> Path:
        return self.root / "narratives"

    @property
    def skeletons_dir(self) -> Path:
        return self.root / "skeletons"

    @property
    def input_path(self) -> Path:
        return self.root / "input.md"

    @property
    def run_meta_path(self) -> Path:
        return self.root / "run_meta.json"

    @property
    def figures_manifest_path(self) -> Path:
        return self.raw_dir / "figures_manifest.json"

    @property
    def draft_pdf_path(self) -> Path:
        return self.raw_dir / "draft.pdf"

    @property
    def assets_path(self) -> Path:
        return self.root / "assets.json"

    @property
    def existing_narrative_path(self) -> Path:
        return self.root / "existing_narrative.json"

    @property
    def fit_matrix_path(self) -> Path:
        return self.root / "fit_matrix.json"

    @property
    def adversarial_review_path(self) -> Path:
        return self.root / "adversarial_review.json"

    @property
    def patches_path(self) -> Path:
        return self.root / "patches.json"

    @property
    def report_path(self) -> Path:
        return self.root / "report.md"

    def journal_profile_path(self, slug: str) -> Path:
        return self.journals_dir / f"{slug}.json"

    def narrative_path(self, index: int) -> Path:
        return self.narratives_dir / f"candidate_{index}.json"

    def skeleton_path(self, narrative_id: str, journal_slug: str) -> Path:
        return self.skeletons_dir / f"skeleton_{narrative_id}_{journal_slug}.md"

    def bootstrap_template(self, overwrite: bool = False) -> Path:
        self.ensure_layout()
        if overwrite or not self.input_path.exists():
            self.input_path.write_text(INPUT_TEMPLATE, encoding="utf-8")
        if overwrite and self.run_meta_path.exists():
            self.run_meta_path.unlink()
        return self.input_path

    def copy_input(self, source: Path) -> Path:
        self.ensure_layout()
        target = self.input_path
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return target

    def copy_draft_pdf(self, source: Path) -> Path:
        self.ensure_layout()
        shutil.copy2(source, self.draft_pdf_path)
        return self.draft_pdf_path
