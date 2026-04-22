# Paper Materials Submission

## 1. Paper Identity
- working_title: RobustPromptGate
- domain: NLP
- task: prompt-based classification under domain shift

## 2. Algorithm (fixed, not to be changed by this module)

### Input
Source-domain prompts, target-domain unlabeled samples, and a frozen large language model.

### Method / Pipeline
We learn a lightweight gating module that routes each sample to domain-adaptive prompt experts and calibrates abstention when the model is uncertain.

### Output
Task predictions together with calibrated abstention scores.

### Key Novelty Claim(s) (作者自认)
- novelty_1: A routing-and-abstention design that improves domain-shift robustness without updating the frozen backbone.
- novelty_2: A calibration mechanism that exposes when prompt experts disagree.

## 3. Experiments (fixed facts)

### Exp-1: Cross-domain benchmark
- purpose: Validate robustness across sentiment and intent datasets.
- datasets: Amazon Reviews, MultiDomain Sentiment, CLINC150
- baselines: vanilla prompt tuning, prompt ensembling, entropy thresholding
- metrics: accuracy, macro-F1, AUROC
- key_results: Improves macro-F1 by 2.8-4.1 points and AUROC by 3.5 points on average across three target settings.
- side_findings: Gains are largest on tail intents with high prompt disagreement.

### Exp-2: Calibration analysis
- purpose: Show that the abstention signal tracks domain mismatch.
- datasets: Amazon Reviews, CLINC150
- baselines: max-probability thresholding
- metrics: ECE, abstention precision
- key_results: Reduces ECE by 21% and raises abstention precision from 0.62 to 0.74.
- side_findings: Visual analysis shows a cleaner separation between in-domain and shifted samples.

## 4. Target Journals
- journal_1: Pattern Recognition   priority: high
- journal_2: Machine Learning with Applications   priority: medium

## 5. Existing Drafts (optional)
- current_abstract:
- current_intro_p1:
- figure_1_caption:
- prior_rejection_feedback:
