# ASHA Saathi 🩺
**An offline triage agent for India's community health workers, running 100% on-device with Gemma 4 E2B.**

India has about 1 million ASHA (Accredited Social Health Activist) workers. They visit homes in villages where mobile signal is weak or absent, and they have to decide on the spot whether a feverish infant or a pregnant woman with a headache needs a hospital *today*. ASHA Saathi gives them a clinical co-pilot that works without internet, keeps patient data on the device, and knows when to hand the decision to a human.

> Built at the Google DeepMind Hyderabad Hackathon (26 Sep 2026), Problem Statement 5: Best Use of Gemma 4 (Local-First Agents).
> ⚠️ Prototype. Not a medical device.

## The agent loop

```
 worker notes (EN / తెలుగు / हिंदी) + vitals + photo
                     │
   ① SENSE   Gemma 4 → structured observations (JSON-schema constrained, retried on bad output)
                     │
   ② DECIDE  Gemma 4 picks tools in a loop (≤5 steps):
             check_danger_signs · check_vitals · get_patient_history ·
             dose_calculator · ask_worker · final(triage, confidence)
                     │
   ③ ACT     Gemma 4 → care plan, Telugu message for the family, referral note
                     │
   ④ CHECK   a) deterministic WHO-IMNCI guardrail: triage can only go UP, never down
             b) Gemma self-review of the plan → one revision pass if unsafe
             c) HUMAN HANDOFF if RED, low confidence, or model unavailable
                     │
   SQLite (patients · visits · full step trace · sync_queue) ──(when signal returns)──▶ PHC doctor inbox
```

### What makes it an agent, not a straight arrow
| Requirement | Implementation |
|---|---|
| Sense-decide-act-check | `agent.py`: 4 phases; DECIDE is a model-driven tool loop with repeat-call guards |
| 100% offline | Gemma 4 E2B (QAT, 4.3 GB) through Ollama on localhost; Python stdlib only; no cloud calls |
| Local state | `store.py`: SQLite for patients, visit history, **every agent step persisted** (audit trail), sync queue. Visits interrupted by a crash or dead battery are marked `interrupted` on restart |
| Offline error recovery | invalid JSON → retry with the error fed back; tool errors (e.g. missing weight) returned to the model; model down → **protocol-only degraded mode**; referral sync retries with exponential backoff on flaky 2G |
| Human handoff | RED danger signs, confidence < 0.6, or degraded mode → "call 108 / refer to PHC", and the referral is queued for the doctor |
| Safety | Drug doses come from a deterministic calculator, never from the LLM. Rules set a floor the model can't go below |

## Validation on real data
`python3 eval_maternal.py` runs the guardrail on all 1,014 records of the [UCI Maternal Health Risk dataset](https://archive.ics.uci.edu/dataset/863/maternal+health+risk) (CC BY 4.0) and the full Gemma agent on a stratified sample of 12. Results: [`data/eval_results.md`](data/eval_results.md). The guardrail escalates **97% of high-risk pregnancies** (265/272).

## Run it (about 2 minutes, then works offline forever)
```bash
brew install ollama && brew services start ollama   # or see ollama.com
ollama pull gemma4:e2b-it-qat
python3 server.py        # → http://localhost:8000
```
No `pip install` is needed: it's pure Python 3.9+ standard library.

Headless: `python3 run_cli.py` runs 4 field cases and prints the full agent trace.

### Demo script
1. Keep the network pill on **✈ Offline**. Switch on real airplane mode too.
2. Run **🔴 Sick infant**: danger signs are found, the triage is RED, the case is handed off, and the referral is queued.
3. Run **🟡 Diarrhoea**: the agent calls `dose_calculator(ors)` and `dose_calculator(zinc)` and gets weight-based doses.
4. Run **🟢 Telugu mild cough**: Telugu input goes in, and a Telugu family message comes out.
5. Stop Ollama (`brew services stop ollama`) and run again: degraded mode is still safe.
6. Tap the network pill to go **online**. Open the **PHC doctor inbox**: RED referrals arrive first, and some deliveries retry.

## Files
| File | Role |
|---|---|
| `agent.py` | Agent loop, prompts, JSON schemas, handoff logic |
| `protocols.py` | WHO-IMNCI / maternal danger signs, vitals thresholds, dose calculator |
| `llm.py` | Ollama client (schema-constrained JSON, images, timeouts) |
| `store.py` | SQLite local-first state and crash recovery |
| `server.py` | stdlib HTTP server, streamed agent events, background sync worker |
| `static/index.html` | Single-file UI: live reasoning trace, decision card, PHC inbox |
| `run_cli.py` | Headless runner (used by the Kaggle notebook) |
| `dataset.py`, `eval_maternal.py` | Real-data validation on UCI Maternal Health Risk |
| `notebook/` | Kaggle live demo notebook |
