# ASHA Saathi
### An offline sense-decide-act-check triage agent for India's 1 million community health workers, running entirely on Gemma 4 E2B

**Track:** Problem Statement 5: Best Use of Gemma 4 (Local-First Agents)

## The problem
India's ~1 million ASHA workers are the first (often the only) point of care for mothers and children in rural India. Every day they have to decide at a doorstep whether a feverish baby or a pregnant woman with a headache needs a hospital *today*. These decisions are made:
- **with no connectivity:** many villages have patchy or no mobile data, so cloud AI is not an option;
- **with sensitive data:** maternal and child health records must not leave the device casually;
- **with life-or-death stakes:** missing a danger sign (chest indrawing, pre-eclampsia) can kill; over-referring overwhelms primary health centres (PHCs).

A chatbot that answers one question is not enough. The worker needs an **agent** that gathers facts, uses reliable tools, writes a plan, checks itself, and **knows when to hand over to a human**, all on a cheap device with no signal.

## What we built
ASHA Saathi is a local-first agent. The worker types or pastes notes in English, Telugu or Hindi, enters any vitals they measured, and can attach a photo. The agent then runs a visible four-phase loop, streamed live to the UI and persisted step by step to SQLite:

1. **SENSE:** Gemma 4 E2B converts free-text (including Telugu) plus an optional photo into **schema-constrained JSON** observations. Values the worker actually measured always override model extraction; the model is never allowed to invent vitals.
2. **DECIDE:** a **model-driven tool loop** (up to 5 steps). Gemma chooses among `check_danger_signs`, `check_vitals`, `get_patient_history`, `dose_calculator`, `ask_worker`, and `final(triage, reason, confidence)`. Tool results, including **tool errors** (e.g. "weight required for dosing"), are fed back so the model can recover.
3. **ACT:** Gemma writes a care plan, a two-sentence **Telugu message for the family**, and a referral note for the PHC doctor. Drug doses are inserted from the deterministic calculator; the LLM is told to never invent doses.
4. **CHECK:** three independent safety layers:
   - a **deterministic protocol guardrail** (simplified WHO IMNCI + maternal danger signs) re-triages the case. Final triage = max(model, rules): **the model can escalate but can never under-triage**. If the guardrail escalates, the plan is regenerated for the new level;
   - a **Gemma self-review** audits the plan against the triage level; if unsafe, the agent revises once (bounded on-device compute), and any remaining issues are attached for the doctor;
   - **human handoff:** any RED case, confidence < 0.6, or degraded mode forces "Call 108 / refer to PHC" and places the referral in the sync queue.

Finally the referral waits in a **priority sync queue**. When connectivity returns, a background worker delivers RED cases first to the PHC doctor's inbox, with exponential-backoff retries on flaky 2G.

## Architecture
```
Browser UI ─(NDJSON stream)─▶ server.py (Python stdlib) ─▶ agent.py  SENSE→DECIDE→ACT→CHECK
                                                             │         │
                                   llm.py ─▶ Ollama localhost ─▶ Gemma 4 E2B (QAT, 4.3 GB)
                                   protocols.py  danger signs · vitals thresholds · dose calculator
                                   store.py      SQLite: patients · visits · trace · sync_queue
                                   sync worker ──(when online)──▶ PHC doctor inbox (RED first)
```
- **Zero cloud dependencies at runtime.** Pure Python standard library (no pip install) plus Ollama. Nothing leaves the device except explicit referrals after sync.
- **Every agent step is an audit record** (`trace` table), so a supervising doctor can see exactly *why* a decision was made.
- **Crash-safe:** visits interrupted mid-run (app killed, battery died) are marked `interrupted` on restart instead of silently lost.

## Why Gemma 4 E2B, and how we made a 2B-effective model behave like an agent
We chose **Gemma 4 E2B in its QAT (quantization-aware trained) build**: 4.3 GB, it runs on an 8 GB laptop alongside the OS, and it can handle multilingual text and images. The default build (7.2 GB) swapped heavily on our 8 GB machine, which would be fatal on a field device.

Small models fail in predictable ways. We saw each of these during the hackathon and engineered around them:

| Failure we observed | Engineering fix |
|---|---|
| Malformed / truncated JSON | Ollama JSON-schema-constrained decoding + **retry with the parser error fed back** |
| Tool-call loops (calling `check_vitals` 4 times) | **Dynamic action masking**: each step's allowed actions are computed from state (unused tools; dosing and asking only after safety checks; last step must be `final`), enforced in the controller, not just the prompt |
| Asking the worker the same question repeatedly | `ask_worker` allowed once per visit |
| **Under-triage**: Gemma called a lethargic, non-feeding infant with fast breathing "YELLOW" | Deterministic guardrail escalated to **RED**, regenerated the plan, handed off. This happened live in our testing and is exactly why the CHECK phase exists |
| Hallucinated symptoms ("Not provided") | Normalisation filter on SENSE output |
| Model server crash / not installed | **Degraded protocol-only mode**: rules-based triage and template plan, flagged for doctor confirmation. The worker is never left without an answer |

The key design principle: **Gemma does the language-heavy, judgement-heavy work (understanding messy Telugu notes, choosing what to check, explaining the plan to a family), while safety-critical arithmetic and thresholds are deterministic tools the agent calls.** This is how we think small on-device models should be deployed in healthcare.

## Validation on real patient data
We validated on the **UCI Maternal Health Risk dataset**: 1,014 real antenatal records from rural health care in Bangladesh (age, BP, blood sugar, temperature, heart rate, expert risk label). The dataset's "high risk" label is not the same as our RED ("refer today"), so we report **escalation recall**: the share of high-risk women the system sends to a facility (YELLOW or RED).

**Error analysis drove a real fix.** Our first rule set escalated only **71%** of high-risk women. Inspecting the misses showed three standard Indian criteria we had left out: fever ≥ 38 °C in pregnancy (WHO danger sign), blood sugar ≥ 7.8 mmol/L (DIPSI gestational-diabetes threshold), and maternal age < 18 or ≥ 35. Adding the first two as escalations, and age as an *advisory* note (Indian guidance says register and plan institutional delivery, not refer today), gave:

| Guardrail on all 1,014 records | escalated |
|---|---|
| high risk (272) | **265 (97%)** |
| mid risk (336) | 172 (51%) |
| low risk (406) | 154 (38%) |

We deliberately accept extra PHC visits for low-risk women in exchange for missing only 7 of 272 high-risk pregnancies.

**Full on-device agent** (Gemma 4 E2B + guardrail) on a stratified sample of 12 records: **6/6 high-risk women escalated**, 2/3 mid-risk, and 3/3 low-risk (conservative). Median **64 s per visit** on an 8 GB laptop, fully offline. The sample is small because each run is a real multi-step on-device agent; the full per-record table is in `data/eval_results.md`.

## Demo
- **Live demo (Kaggle Notebook):** runs the exact repository code with Gemma 4 E2B served locally inside the notebook through Ollama, across four field cases (sick infant → RED with guardrail escalation, pre-eclampsia → RED, diarrhoea → YELLOW with ORS dosing, a Telugu cough case), then the real-data validation above. It then **kills the model mid-session** to show degraded-mode recovery, and dumps the SQLite state (visits, full trace, sync queue).
- **Local app:** `python3 server.py` shows a live reasoning trace, decision card, airplane-mode network toggle, and PHC doctor inbox that fills when the device goes "online".

## Challenges we overcame today
1. **Model size vs. device RAM:** switched from the 7.2 GB default to the 4.3 GB QAT build mid-hackathon.
2. **Agent latency:** initial run took 94 s. We kept the model resident (`keep_alive`), warmed it at startup, bounded plan revisions to one, and trimmed token budgets.
3. **Small-model tool discipline:** moved from prompt-only instructions to a state-machine controller with dynamic action masks.
4. **Clinical safety:** designed the "rules set the floor" pattern so model errors can only make the system *more* cautious.

## Limitations and next steps
- Protocol rules are simplified from WHO IMNCI guidance and not clinically validated; a real deployment needs review by clinicians and the state NHM.
- The PHC server is simulated locally; next step is a real sync endpoint (e.g. FHIR) with encryption at rest.
- Port to Android with LiteRT / MediaPipe to run Gemma 4 E2B on the ₹10k phones ASHAs actually carry; add on-device speech input using Gemma 4's audio support.

*Prototype built in one day. Not a medical device.*
