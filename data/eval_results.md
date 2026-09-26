# ASHA Saathi - validation on UCI Maternal Health Risk (real antenatal records)

## Protocol guardrail alone - all 1,014 records

| Dataset label | n | → RED | → YELLOW | → GREEN | escalated (Y+R) |
|---|---|---|---|---|---|
| high risk | 272 | 159 | 106 | 7 | 265/272 (97%) |
| mid risk | 336 | 62 | 110 | 164 | 172/336 (51%) |
| low risk | 406 | 68 | 86 | 252 | 154/406 (38%) |

## Full on-device agent (Gemma 4 E2B + guardrail) - stratified sample of 12

| Dataset label | n | → RED | → YELLOW | → GREEN | escalated (Y+R) |
|---|---|---|---|---|---|
| high risk | 6 | 1 | 5 | 0 | 6/6 (100%) |
| mid risk | 3 | 0 | 2 | 1 | 2/3 (67%) |
| low risk | 3 | 1 | 2 | 0 | 3/3 (100%) |

- Gemma's own decision was escalated by the guardrail in **0/12** cases
- Human handoff triggered in **2/12** cases
- Median time per visit: **64.2 s** on an 8 GB laptop (Apple A18 Pro), fully offline

| CSV row | label | BP | BS | HR | Gemma | final | override | handoff | s |
|---|---|---|---|---|---|---|---|---|---|
| 556 | high risk | 140/95 | 19.0 | 77 | RED | RED |  | yes | 76.0 |
| 239 | high risk | 90/60 | 11.0 | 78 | YELLOW | YELLOW |  |  | 75.3 |
| 681 | high risk | 85/60 | 11.0 | 86 | YELLOW | YELLOW |  |  | 76.9 |
| 118 | high risk | 120/80 | 7.9 | 76 | YELLOW | YELLOW |  |  | 53.5 |
| 131 | high risk | 120/80 | 11.0 | 88 | YELLOW | YELLOW |  |  | 81.7 |
| 147 | high risk | 90/65 | 7.0 | 70 | YELLOW | YELLOW |  |  | 52.6 |
| 730 | mid risk | 110/60 | 7.0 | 70 | GREEN | GREEN |  |  | 56.3 |
| 841 | mid risk | 85/60 | 9.0 | 86 | YELLOW | YELLOW |  |  | 61.3 |
| 87 | mid risk | 90/60 | 6.9 | 70 | YELLOW | YELLOW |  |  | 64.2 |
| 560 | low risk | 120/95 | 7.5 | 66 | RED | RED |  | yes | 65.7 |
| 260 | low risk | 90/60 | 6.9 | 70 | YELLOW | YELLOW |  |  | 49.6 |
| 38 | low risk | 120/80 | 6.1 | 75 | YELLOW | YELLOW |  |  | 58.3 |

Note: the dataset's 'high risk' label is not identical to our RED ('refer today'); escalation = YELLOW or RED (sent to a facility).
