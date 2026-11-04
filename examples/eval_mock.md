# Evaluation: mock/keyword-rules-v1 (redaction on)

**Overall: PASS**

## Accuracy (labelled synthetic set, n=30)

| Metric | Result | Threshold | |
|---|---:|---:|---|
| Theme accuracy | 97% | 80% | PASS |
| Sentiment accuracy | 90% | 75% | PASS |

| Theme | Precision | Recall | Support |
|---|---:|---:|---:|
| workload | 0.83 | 1.0 | 5 |
| tooling | 1.0 | 1.0 | 5 |
| leadership | 1.0 | 1.0 | 5 |
| recognition | 1.0 | 1.0 | 5 |
| flexibility | 1.0 | 0.8 | 5 |
| change_control | 1.0 | 1.0 | 5 |

## Counterfactual bias tests

Each variant changes only a name, gendered wording or English fluency. Pass = consistency ≥ 95% and accuracy gap ≤ 5%.

| Dimension | Pairs | Consistency | Accuracy gap | |
|---|---:|---:|---:|---|
| name | 7 | 100% | +0% | PASS |
| gender | 4 | 100% | +0% | PASS |
| english_fluency | 5 | 100% | +0% | PASS |

### Misclassified items

| Item | Expected | Got | Rationale |
|---|---|---|---|
| EV-01 | workload / negative | workload / mixed | Keyword match on workload. |
| EV-08 | tooling / negative | tooling / mixed | Keyword match on tooling. |
| EV-13 | leadership / negative | leadership / mixed | Keyword match on leadership. |
| EV-23 | flexibility / positive | workload / positive | Keyword match on workload. |
