# ASHA Saathi
### An offline sense-decide-act-check triage agent for India's 1 million community health workers, running entirely on Gemma 4 E2B

**Track:** Problem Statement 5: Best Use of Gemma 4 (Local-First Agents)

## The problem
India's ~1 million ASHA workers are often the only point of care for rural mothers and children. At a doorstep they must decide whether a feverish baby or a pregnant woman with a headache needs a hospital *today*, and they decide **without connectivity**, holding **sensitive health data**, with **life-or-death stakes**: a missed danger sign can kill, and over-referral overwhelms primary health centres (PHCs). A chatbot is not enough. They need an **agent** that gathers facts, uses reliable tools, checks itself, and **knows when to hand over to a human**, on a cheap device with no signal.

## What we built
The worker types **or speaks** notes in English, Telugu or Hindi, enters any measured vitals, and can attach a photo. The agent runs a visible four-phase loop, streamed live and persisted step by step to SQLite:

1. **SENSE:** Gemma 4 E2B turns free text (any of the three languages) plus an optional photo into **schema-constrained JSON**. Measured values always override model extraction; the model never invents vitals.
2. **DECIDE:** a **model-driven tool loop** (≤5 steps) over `check_danger_signs`, `check_vitals`, `get_patient_history`, `dose_calculator`, `ask_worker`, `final(triage, reason, confidence)`. Tool errors (e.g. "weight required for dosing") are fed back so the model can recover.
3. **ACT:** Gemma writes a care plan, a referral note, and a short **message for the family in the worker's chosen language**, which is also **read aloud** with on-device text-to-speech. Doses come only from the deterministic calculator, and the plan's first step is forced to match the triage level ("Call 108" / "PHC within 24 h").
4. **CHECK:** three safety layers:
   - a **deterministic protocol guardrail** (WHO IMNCI, MoHFW high-risk pregnancy, maternal danger signs): final triage = max(model, rules), so **the model can escalate but never under-triage**;
   - a **Gemma self-review** of the plan, with one bounded revision;
   - **human handoff** for any RED case, confidence < 0.6, or degraded mode, and the referral goes into a priority sync queue.

**Connectivity-optional extras** (they never block the offline core): real-time **nearest hospitals** (OpenStreetMap search, Google Maps directions and an embedded map, cached in SQLite for offline reuse); a full **visit report shared by WhatsApp or SMS** to a number the worker enters (the worker presses send; SMS works on 2G); a live **dashboard**; and **"bring your own dataset"**: upload any CSV, columns are auto-mapped, and rows run through the identical agent.

## Architecture
```
Browser UI ─(NDJSON stream)─▶ server.py (Python stdlib) ─▶ agent.py  SENSE→DECIDE→ACT→CHECK
                                   llm.py ─▶ Ollama localhost ─▶ Gemma 4 E2B (QAT, 4.3 GB)
                                   protocols.py  danger signs · vitals · pregnancy criteria · doses
                                   store.py      SQLite: patients · visits · trace · sync_queue · map cache
                                   services.py   (online only) hospitals · geocoding · report text
                                   sync worker ──(when online)──▶ PHC doctor inbox (RED first, backoff)
```
- **No cloud AI at all.** Pure Python standard library plus Ollama. Patient data leaves only in explicit referrals or reports.
- **Every agent step is an audit record**, so a doctor can see *why* a decision was made.
- **Crash-safe:** visits interrupted mid-run are marked `interrupted` on restart.

## Making a small on-device model behave like an agent
We use **Gemma 4 E2B QAT (4.3 GB)**. The default 7.2 GB build swapped heavily on our 8 GB laptop. Failures we hit today, and our fixes:

| Failure observed | Fix |
|---|---|
| Malformed / truncated JSON | Schema-constrained decoding + **retry with the parser error fed back** |
| Tool-call loops (`check_vitals` ×4) | **Dynamic action masking** in the controller: only unused tools, dosing after safety checks, last step must be `final` |
| **Under-triage**: a lethargic, non-feeding infant called "YELLOW" | Guardrail escalated to **RED**, regenerated the plan, handed off, live in testing |
| Model server down | **Protocol-only degraded mode**, flagged for doctor confirmation |

Design principle: **Gemma does the language- and judgement-heavy work; safety-critical thresholds and arithmetic are deterministic tools it calls.**

## Validation on real data (three public datasets)
**1. UCI Maternal Health Risk:** 1,014 real antenatal records from rural Bangladesh. The dataset's "high risk" is not our RED, so we report **escalation recall** (sent to a facility). Error analysis drove a real fix: our first rules escalated only **71%** of high-risk women. The misses revealed missing Indian criteria: fever ≥ 38 °C in pregnancy, blood sugar ≥ 7.8 mmol/L (DIPSI), and maternal age (made *advisory*, per guidance). Result on all rows: **265/272 high-risk (97%)** escalated, 51% of mid-risk and 38% of low-risk. We accept extra PHC visits to miss only 7 high-risk pregnancies. **Full agent, 12-record sample: 6/6 high-risk escalated**, median 64 s per visit, offline.

**2. Symptom2Disease:** 1,200 patient-written free-text descriptions. Keyword rules alone sent only **7/250 (3%)** dengue, malaria, typhoid, pneumonia and jaundice cases to a facility, because patients don't write protocol keywords. **With Gemma reading the text, the agent escalated 8/8 sampled serious infections.** Honest limitation: it also escalated all 4 mild cases (cold, allergy, acne), so it is sensitive but over-cautious.

**3. Image probe:** 24 photos (measles, chickenpox, HFMD, healthy skin; anaemic vs. normal eyelids). E2B **describes** lesions sensibly but **cannot diagnose** them: 3/14 rash types and 3/10 pallor calls were correct, with a bias toward "abnormal". We therefore treat photos only as descriptive evidence feeding the rules ("fever + rash" escalates), never as a diagnosis. Measuring this changed our design.

All tables: `data/eval_*results.md`; scripts: `eval_maternal.py`, `eval_symptoms.py`, `eval_images.py`.

## Demo
- **Kaggle Notebook:** runs the repo code with Gemma 4 E2B served by Ollama inside the notebook: four field cases, the maternal validation, then **kills the model** to show degraded-mode recovery and dumps the SQLite state.
- **Local app** (`python3 server.py`): dashboard, live reasoning trace, voice in/out, one-click real-dataset cases, airplane-mode toggle, hospitals, report sharing, and the PHC inbox filling when the device goes online.

## Challenges we overcame today
1. **RAM:** moved from the 7.2 GB to the 4.3 GB QAT build.
2. **Latency:** 94 s → about 60 s with a resident, warmed model, bounded revisions and trimmed token budgets.
3. **Tool discipline:** prompt-only instructions → state-machine controller with action masks.
4. **Safety:** "rules set the floor", so model errors only make the system *more* cautious.
5. **Flaky public map servers:** mirror fallback plus an SQLite cache.

## Limitations and next steps
- Rules are simplified from public guidance, not clinically validated; deployment needs clinician and NHM review.
- Over-referral of mild cases; next step is calibrating Gemma on de-identified ASHA notes.
- Voice input uses the browser's speech service (online); next step is Gemma 4's native on-device audio. Telugu text-to-speech depends on installed device voices.
- The PHC server is simulated; next step is a FHIR endpoint with encryption at rest, and an Android port via LiteRT.

*Prototype built in one day. Not a medical device.*
