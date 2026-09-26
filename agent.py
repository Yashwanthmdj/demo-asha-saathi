"""ASHA Saathi agent: SENSE -> DECIDE (tool loop) -> ACT -> CHECK, fully offline.

Every step is emitted to the UI and persisted to SQLite (store.trace), so the
worker (and a supervising doctor later) can audit exactly why a decision was
made. Any model failure degrades to deterministic protocol rules - the agent
never leaves a worker without an answer and never under-triages.
"""
import json
import time

import llm
import protocols as P
import store

MAX_DECIDE_STEPS = 5
HANDOFF_CONFIDENCE = 0.6

SYSTEM = (
    "You are ASHA Saathi, an offline clinical decision-support agent for ASHA "
    "community health workers in rural India. Follow WHO IMNCI and maternal "
    "danger-sign protocols. Be conservative: when unsure, refer. Never invent "
    "vitals. Reply ONLY with JSON matching the schema."
)

NUM = {"type": "number"}
STR = {"type": "string"}

SENSE_SCHEMA = {
    "type": "object",
    "properties": {
        "symptoms": {"type": "array", "items": STR},
        "duration_days": NUM,
        "temperature_c": NUM,
        "resp_rate": NUM,
        "spo2": NUM,
        "bp_systolic": NUM,
        "bp_diastolic": NUM,
        "weight_kg": NUM,
        "heart_rate": NUM,
        "blood_sugar": NUM,
        "image_findings": STR,
        "missing_info": {"type": "array", "items": STR},
    },
    "required": ["symptoms", "duration_days", "temperature_c", "resp_rate", "spo2",
                 "bp_systolic", "bp_diastolic", "weight_kg", "heart_rate", "blood_sugar", "image_findings", "missing_info"],
}

TOOLS = ["check_danger_signs", "check_vitals", "get_patient_history", "dose_calculator", "ask_worker", "final"]

DECIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string", "description": "one short sentence of clinical reasoning"},
        "action": {"type": "string", "enum": TOOLS},
        "drug": STR,
        "question": STR,
        "triage": {"type": "string", "enum": ["RED", "YELLOW", "GREEN"]},
        "reason": STR,
        "confidence": NUM,
    },
    "required": ["thought", "action", "drug", "question", "triage", "reason", "confidence"],
}

ACT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": STR,
        "care_plan": {"type": "array", "items": STR},
        "watch_for": {"type": "array", "items": STR},
        "follow_up": STR,
        "telugu_summary": STR,
        "referral_note": STR,
    },
    "required": ["summary", "care_plan", "watch_for", "follow_up", "telugu_summary", "referral_note"],
}

CHECK_SCHEMA = {
    "type": "object",
    "properties": {"consistent": {"type": "boolean"}, "issues": {"type": "array", "items": STR}},
    "required": ["consistent", "issues"],
}


class Agent:
    def __init__(self, visit_id, emit):
        self.visit_id = visit_id
        self._emit = emit
        self.degraded = False
        self.llm_ms = 0
        self.llm_calls = 0

    def emit(self, phase, kind, data):
        store.log(self.visit_id, phase, kind, data)
        self._emit({"phase": phase, "kind": kind, "data": data, "ts": time.time()})

    # -- resilient model call: retry with error feedback, then give up --------
    def ask(self, phase, prompt, schema, images=None, max_tokens=512):
        if self.degraded:
            return None
        last_err = None
        for attempt in range(2):
            p = prompt if not last_err else prompt + f"\n\nYour previous reply failed: {last_err}. Reply with valid JSON only."
            try:
                out, ms = llm.chat_json(SYSTEM, p, schema, images=images, max_tokens=max_tokens)
                self.llm_ms += ms
                self.llm_calls += 1
                self.emit(phase, "llm", {"ms": ms, "attempt": attempt + 1})
                return out
            except llm.LLMError as e:
                last_err = str(e)
                self.emit(phase, "retry", {"attempt": attempt + 1, "error": last_err[:160]})
                if "unreachable" in last_err:
                    break
        self.degraded = True
        self.emit(phase, "degraded", {"message": "Local model unavailable - switching to protocol-only mode (still safe, still offline)."})
        return None

    # -- SENSE -----------------------------------------------------------------
    def sense(self, patient, complaint, form_vitals, image_b64):
        self.emit("SENSE", "start", {"complaint": complaint, "has_image": bool(image_b64)})
        prompt = (
            f"Patient: {patient['name']}, age {patient['age_months']} months, sex {patient['sex']}, "
            f"pregnant: {bool(patient['pregnant'])}.\n"
            f"ASHA worker's notes: \"{complaint}\"\n"
            + ("A photo is attached - describe clinically relevant findings in image_findings.\n" if image_b64 else "")
            + "Extract observations. Symptoms: short English phrases (translate Telugu/Hindi). "
            "Use 0 for any number not stated. List critical missing info (e.g. breathing rate, temperature, weight) in missing_info."
        )
        out = self.ask("SENSE", prompt, SENSE_SCHEMA, images=[image_b64] if image_b64 else None)
        if out is None:  # degraded: naive keyword extraction
            out = {"symptoms": [s.strip() for s in complaint.replace(";", ",").split(",") if s.strip()],
                   "missing_info": [], "image_findings": ""}
        obs = {k: (v if v not in (0, 0.0, "") else None) for k, v in out.items()}
        junk = ("not provided", "none", "none reported", "n/a", "unknown", "not stated", "not mentioned", "")
        obs["symptoms"] = [s for s in (out.get("symptoms") or []) if s.strip().lower() not in junk]
        if out.get("image_findings") and out["image_findings"].strip().lower() not in junk:
            obs["symptoms"].append(out["image_findings"])
        # Measured values typed by the worker always beat model extraction.
        for k, v in form_vitals.items():
            if v not in (None, "", 0):
                obs[k] = float(v)
        obs["age_months"] = patient["age_months"]
        obs["pregnant"] = bool(patient["pregnant"])
        self.emit("SENSE", "observations", obs)
        return obs

    # -- DECIDE: model-driven tool loop -------------------------------------------
    def run_tool(self, name, obs, step, patient):
        if name == "check_danger_signs":
            return P.check_danger_signs(obs)
        if name == "check_vitals":
            return P.check_vitals(obs)
        if name == "get_patient_history":
            h = store.patient_history(patient["id"])
            return h["previous_visits"]
        if name == "dose_calculator":
            return P.dose_calculator(step.get("drug"), obs.get("weight_kg"), obs.get("age_months"))
        return {"error": f"unknown tool {name}"}

    @staticmethod
    def allowed_actions(called, asked, dose_calls, i):
        if i == MAX_DECIDE_STEPS - 1:
            return ["final"]
        acts = [t for t in ("check_danger_signs", "check_vitals", "get_patient_history") if t not in called]
        safety_done = {"check_danger_signs", "check_vitals"} <= called
        if safety_done and dose_calls < 2:
            acts.append("dose_calculator")
        if safety_done and not asked:
            acts.append("ask_worker")
        if safety_done:
            acts.append("final")
        return acts or ["final"]

    def decide(self, obs, patient):
        self.emit("DECIDE", "start", {})
        results, called = [], set()
        asked, dose_calls = False, 0
        final = None
        for i in range(MAX_DECIDE_STEPS):
            ctx = "\n".join(f"- {r['tool']}{'(' + r['arg'] + ')' if r['arg'] else ''} -> {json.dumps(r['result'], ensure_ascii=False)}" for r in results) or "(none yet)"
            prompt = (
                f"Observations: {json.dumps(obs, ensure_ascii=False)}\n"
                f"Tool results so far:\n{ctx}\n\n"
                "Tools: check_danger_signs (protocol danger signs), check_vitals (age thresholds), "
                "get_patient_history (past visits), dose_calculator (set drug: paracetamol|amoxicillin|ors|zinc|iron_folic_acid), "
                "ask_worker (set question, only if a critical measurement is missing and safe triage is impossible), "
                "final (set triage RED/YELLOW/GREEN, reason, confidence 0-1). Any RED protocol finding means triage RED.\n"
                "Normally: check danger signs, check vitals, history, doses if treating at home, then final. "
                "Dosing hints: diarrhoea/dehydration -> ors then zinc; fast breathing without danger signs -> amoxicillin; fever >=38.5C -> paracetamol. "
                "Missing SpO2 or BP is normal for children - do not escalate just because optional vitals are missing. "
                f"Already used (do NOT repeat): {', '.join(sorted(called)) or 'none'}.\n"
                f"Step {i + 1} of {MAX_DECIDE_STEPS}. Choose ONE next action. thought = one short sentence of clinical reasoning (not the tool name)."
            )
            # Dynamic action mask: small on-device models loop, so each step may only
            # choose tools not yet used; the final step must decide.
            allowed = self.allowed_actions(called, asked, dose_calls, i)
            schema = json.loads(json.dumps(DECIDE_SCHEMA))
            schema["properties"]["action"]["enum"] = allowed
            prompt += f"\nAllowed actions now: {', '.join(allowed)}."
            step = self.ask("DECIDE", prompt, schema, max_tokens=240)
            if step is None:
                break
            action = step.get("action")
            if action not in allowed:
                forced = allowed[0]
                self.emit("DECIDE", "guard", {"message": f"Gemma chose '{action}' (not allowed now) - controller redirects to '{forced}'"})
                action = step["action"] = forced
            self.emit("DECIDE", "thought", {"step": i + 1, "thought": step.get("thought", ""), "action": action})
            if action == "final":
                if step.get("triage") not in P.SEVERITY:
                    step["triage"] = P.rules_triage(obs)[0]
                final = step
                break
            if action == "ask_worker":
                asked = True
                self.emit("DECIDE", "ask_worker", {"question": step.get("question", "")})
                results.append({"tool": "ask_worker", "arg": "", "result": "Question shown to worker; continue with available data."})
                continue
            key = action + ((step.get("drug") or "").lower() if action == "dose_calculator" else "")
            if key in called:
                results.append({"tool": action, "arg": step.get("drug", ""), "result": "Already called - use the earlier result, pick another action or final."})
                self.emit("DECIDE", "guard", {"message": f"Blocked repeated call to {action}"})
                continue
            called.add(key)
            if action == "dose_calculator":
                dose_calls += 1
            res = self.run_tool(action, obs, step, patient)
            arg = step.get("drug", "") if action == "dose_calculator" else ""
            results.append({"tool": action, "arg": arg, "result": res})
            self.emit("DECIDE", "tool", {"tool": action, "arg": arg, "result": res,
                                         "recovered": isinstance(res, dict) and "error" in res})

        if final is None:
            # Model failed or ran out of steps: run every safe tool deterministically.
            self.emit("DECIDE", "fallback", {"message": "No final decision from model - using protocol tools directly."})
            for t in ("check_danger_signs", "check_vitals"):
                if t not in called:
                    res = self.run_tool(t, obs, {}, patient)
                    results.append({"tool": t, "arg": "", "result": res})
                    self.emit("DECIDE", "tool", {"tool": t, "arg": "", "result": res})
            lvl, _ = P.rules_triage(obs)
            final = {"triage": lvl, "reason": "Protocol rules (model did not reach a decision)", "confidence": 0.5}
        self.emit("DECIDE", "decision", {"triage": final["triage"], "reason": final.get("reason", ""),
                                         "confidence": final.get("confidence", 0)})
        return final, results

    # -- ACT -----------------------------------------------------------------------
    def act(self, obs, triage, findings, tool_results, patient, issues=None):
        self.emit("ACT", "start", {"revision": bool(issues)})
        doses = [r["result"] for r in tool_results if r["tool"] == "dose_calculator" and "error" not in r["result"]]
        prompt = (
            f"Patient {patient['name']} ({patient['age_months']} months, pregnant={bool(patient['pregnant'])}).\n"
            f"Observations: {json.dumps(obs, ensure_ascii=False)}\n"
            f"FINAL TRIAGE: {triage}\nProtocol findings: {json.dumps(findings, ensure_ascii=False)}\n"
            f"Calculated doses (use exactly, do not invent others): {json.dumps(doses)}\n"
            + (f"A reviewer found these problems in your last plan - fix them: {issues}\n" if issues else "")
            + "Write for an ASHA worker: simple steps. RED = stabilise + urgent referral (call 108), no home treatment beyond pre-referral dose. "
            "YELLOW = treat + visit PHC within 24h. GREEN = home care. telugu_summary: 2 short sentences in Telugu script for the family. "
            "referral_note: 2 lines for the PHC doctor (empty if GREEN)."
        )
        plan = self.ask("ACT", prompt, ACT_SCHEMA, max_tokens=450)
        if plan is None:
            plan = template_plan(triage, findings, doses)
        plan["doses"] = doses
        self.emit("ACT", "plan", plan)
        return plan

    # -- CHECK ---------------------------------------------------------------------
    def check(self, obs, final, plan, tool_results, patient):
        self.emit("CHECK", "start", {})
        rules_level, findings = P.rules_triage(obs)
        model_level = final["triage"]
        level = P.worse(model_level, rules_level)
        self.emit("CHECK", "guardrail", {"model": model_level, "rules": rules_level, "final": level,
                                          "override": level != model_level,
                                          "findings": [f for f in findings if f["level"] != "GREEN"]})
        revised = False
        if level != model_level:
            revised = True
            # Plan was written for a less severe triage - regenerate it.
            plan = self.act(obs, level, findings, tool_results, patient,
                            issues=[f"Triage escalated from {model_level} to {level} by protocol guardrail"])

        verdict = self.ask("CHECK", (
            f"Triage: {level}. Danger findings: {json.dumps(findings, ensure_ascii=False)}\n"
            f"Plan: {json.dumps({k: plan[k] for k in ('care_plan', 'follow_up', 'watch_for')}, ensure_ascii=False)}\n"
            "Audit this plan as a senior doctor. Is it consistent with the triage level and safe? "
            "(e.g. RED must include urgent referral; no drugs beyond the calculated doses; no dangerous advice). "
            "List concrete issues, or empty if none."
        ), CHECK_SCHEMA, max_tokens=300)
        if verdict is not None:
            self.emit("CHECK", "self_review", verdict)
            if not verdict.get("consistent", True) and verdict.get("issues") and revised:
                # Budget: one rewrite per visit on-device. Remaining issues go to the doctor.
                plan["doctor_review_notes"] = verdict["issues"]
                self.emit("CHECK", "flagged", {"message": "Remaining review notes attached for the PHC doctor"})
            elif not verdict.get("consistent", True) and verdict.get("issues"):
                plan = self.act(obs, level, findings, tool_results, patient, issues=verdict["issues"])
                self.emit("CHECK", "revised", {"message": "Plan revised after self-review"})

        conf = float(final.get("confidence") or 0)
        reasons = []
        if level == "RED":
            reasons.append("RED danger sign - urgent referral required")
        if conf and conf < HANDOFF_CONFIDENCE:
            reasons.append(f"Low model confidence ({conf:.2f})")
        if self.degraded:
            reasons.append("Model unavailable - protocol-only decision must be confirmed by a doctor")
        handoff = bool(reasons)
        self.emit("CHECK", "handoff" if handoff else "cleared", {"reasons": reasons})
        return level, plan, findings, handoff, reasons


def template_plan(triage, findings, doses):
    signs = [f["finding"] for f in findings if f["level"] != "GREEN"]
    if triage == "RED":
        steps = ["Call 108 ambulance now / take to PHC or CHC immediately",
                 "Keep patient warm; continue breastfeeding or sips of fluid if able to drink",
                 "Give pre-referral dose if listed; do not delay transport"]
    elif triage == "YELLOW":
        steps = ["Give listed medicines as per dose", "Visit PHC within 24 hours", "Revisit at home in 2 days"]
    else:
        steps = ["Home care: fluids, feeding, rest", "Return immediately if any danger sign appears"]
    return {
        "summary": f"{triage} triage. " + ("; ".join(signs) if signs else "No danger signs found."),
        "care_plan": steps,
        "watch_for": ["Convulsions", "Unable to drink", "Breathing difficulty", "Becoming very sleepy"],
        "follow_up": "Revisit in 2 days" if triage != "RED" else "Confirm arrival at facility",
        "telugu_summary": {"RED": "ఇది అత్యవసరం. వెంటనే 108 కి కాల్ చేసి ఆసుపత్రికి తీసుకెళ్లండి.",
                           "YELLOW": "24 గంటల్లో PHC కి వెళ్లండి. మందులు సమయానికి ఇవ్వండి.",
                           "GREEN": "ఇంట్లో జాగ్రత్తగా చూసుకోండి. ప్రమాద సంకేతాలు కనిపిస్తే వెంటనే రండి."}[triage],
        "referral_note": ("Findings: " + "; ".join(signs)) if triage != "GREEN" else "",
    }


def run_visit(patient_id, complaint, form_vitals, image_b64, emit):
    patient = store.q("SELECT * FROM patients WHERE id=?", (patient_id,), one=True)
    vid = store.ins("INSERT INTO visits(patient_id,created,status,complaint) VALUES(?,?,?,?)",
                    (patient_id, time.time(), "running", complaint))
    a = Agent(vid, emit)
    t0 = time.time()
    obs = a.sense(patient, complaint, form_vitals, image_b64)
    final, tool_results = a.decide(obs, patient)
    plan = a.act(obs, final["triage"], P.rules_triage(obs)[1], tool_results, patient)
    level, plan, findings, handoff, reasons = a.check(obs, final, plan, tool_results, patient)

    result = {"visit_id": vid, "patient": patient, "triage": level, "plan": plan, "handoff": handoff,
              "handoff_reasons": reasons, "degraded": a.degraded, "confidence": final.get("confidence"),
              "total_ms": int((time.time() - t0) * 1000), "llm_calls": a.llm_calls, "llm_ms": a.llm_ms,
              "summary": plan.get("summary", "")}
    store.q("UPDATE visits SET status='done', observations=?, triage=?, result=? WHERE id=?",
            (json.dumps(obs, ensure_ascii=False), level, json.dumps(result, ensure_ascii=False), vid))
    if level != "GREEN":
        store.ins("INSERT INTO sync_queue(visit_id,priority,payload,created) VALUES(?,?,?,?)",
                  (vid, P.SEVERITY[level], json.dumps({
                      "patient": patient["name"], "village": patient["village"], "age_months": patient["age_months"],
                      "triage": level, "referral_note": plan.get("referral_note", ""), "summary": plan.get("summary", ""),
                      "handoff_reasons": reasons}, ensure_ascii=False), time.time()))
        a.emit("ACT", "queued", {"message": "Referral saved to offline sync queue - will reach PHC doctor when network returns",
                                 "priority": level})
    a.emit("DONE", "result", result)
    return result
