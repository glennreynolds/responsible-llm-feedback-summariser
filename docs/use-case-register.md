# AI use-case register entry: Heartbeat Insights

*Written in the style of an organisational AI use-case register entry, to show the information I would expect to capture at intake and before go-live.*

| Field | Entry |
|---|---|
| Use case | Summarise anonymous staff check-in comments into themes for team leaders |
| Business owner | People leader receiving the summary (in this demo: the author) |
| Technical owner | Author |
| Lifecycle stage | **Proof of value.** Synthetic data only, not in operational use |
| AI type | Generative AI (LLM). Theme proposal plus constrained classification |
| Decision impact | **Informs, does not decide.** No decision about any individual is made or supported. Output is a team-level summary only |
| Data | Free-text staff comments (personal information possible, sensitive information possible), team name. No identity is collected |
| Providers | Local model (Ollama) or cloud LLM API behind a common interface. Cloud use requires redaction |
| Risk rating (indicative) | Medium. Workforce data, re-identification risk in small teams, potential for unfair characterisation of groups |

## Intended use and out of scope

**Intended:** helping a leader see recurring themes across many comments, with counts they can trace back to evidence, as a starting point for conversations with staff.

**Out of scope:** identifying or profiling any individual; performance management; any automated action; inferring wellbeing or health; comparing individuals; any team with fewer than *k* responses.

## Risks and controls

| # | Risk | Likelihood / impact | Control | Residual |
|---|---|---|---|---|
| R1 | A respondent is re-identified from a small group | Med / High | Groups with fewer than *k*=5 are dropped before analysis. Counts ≤2 are suppressed, including zeros. No quotes by default | Low–Med (writing style, unique details) |
| R2 | Personal information is sent to an external provider | Med / High | Redaction runs first. The pipeline refuses to send unredacted text to an external provider. Output is re-scanned | Low–Med (rule-based redaction has gaps) |
| R3 | Model invents themes or evidence | Med / Med | Citations are checked against real IDs. Themes need human approval. Counts come from per-comment assignments | Low |
| R4 | Groups are characterised unfairly (e.g. non-native English speakers read as more negative) | Med / Med | Counterfactual tests on name, gender and English fluency, with pass thresholds. The prompt tells the model to ignore fluency | Med until tested on a real model and real-like data |
| R5 | Leaders over-rely on the summary | Med / Med | The report states its method and limits, and that it supports rather than replaces leaders' judgement. Sentiment is shown as indicative | Med |
| R6 | Results can't be reconstructed later | Low / Med | Hash-chained audit log of every model call, review decision and release, with model and prompt versions | Low |
| R7 | Silent change in model behaviour after a provider update | Med / Med | Model and prompt version recorded. Evaluation is re-run on any change, and results are tied to the version | Med (needs scheduled re-evaluation) |

## Go-live criteria (not yet met)

1. Evaluation thresholds met **on the chosen production model**: theme accuracy ≥80%, sentiment ≥75%, all counterfactual dimensions ≥95% consistent, accuracy gap ≤5%.
2. Evaluation set expanded and labelled by at least two people, with agreement measured.
3. Privacy impact assessment completed, and the redaction approach reviewed by privacy.
4. Agreed retention period for comments, artefacts and audit log. Audit log shipped to write-once storage.
5. Staff told, in the check-in itself, that comments may be summarised with AI assistance and how.
6. Named owner for re-running evaluation after model or prompt changes.

## Monitoring once live

- Proportion of comments classified as "other" (taxonomy drift)
- Rate of validation failures and retries per provider/model
- Reviewer edit and reject rate on proposed themes (a proxy for model quality)
- Quarterly re-run of the counterfactual suite
