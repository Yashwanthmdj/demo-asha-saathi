"""Deterministic clinical guardrails (simplified WHO IMNCI + maternal danger signs).

These rules are the agent's safety floor: whatever Gemma decides, the final
triage can never be *less* severe than what these rules say. They also power
"degraded mode" when the local model is unavailable.

DEMO ONLY - not a medical device. Thresholds are simplified from public
WHO/IMNCI guidance for illustration.
"""

SEVERITY = {"GREEN": 0, "YELLOW": 1, "RED": 2}


def worse(a, b):
    return a if SEVERITY[a] >= SEVERITY[b] else b


def _has(symptoms, *keywords):
    text = " ".join(symptoms).lower()
    return any(k in text for k in keywords)


def fast_breathing_threshold(age_months):
    if age_months is None:
        return None
    if age_months < 2:
        return 60
    if age_months < 12:
        return 50
    if age_months < 60:
        return 40
    return 30


def check_vitals(obs):
    """Tool: interpret raw vitals against age-specific thresholds."""
    findings = []
    age_m = obs.get("age_months")
    rr = obs.get("resp_rate")
    temp = obs.get("temperature_c")
    spo2 = obs.get("spo2")
    sbp, dbp = obs.get("bp_systolic"), obs.get("bp_diastolic")

    thr = fast_breathing_threshold(age_m)
    if rr and thr:
        if rr >= thr:
            findings.append({"level": "YELLOW", "finding": f"Fast breathing: {rr}/min (threshold {thr}/min for age)"})
        else:
            findings.append({"level": "GREEN", "finding": f"Breathing rate {rr}/min is normal for age"})
    if temp:
        if age_m is not None and age_m < 2 and (temp >= 37.5 or temp < 35.5):
            findings.append({"level": "RED", "finding": f"Young infant with abnormal temperature {temp}°C"})
        elif temp >= 39.0:
            findings.append({"level": "YELLOW", "finding": f"High fever {temp}°C"})
        elif temp >= 37.5:
            findings.append({"level": "GREEN", "finding": f"Fever {temp}°C"})
    if spo2:
        if spo2 < 90:
            findings.append({"level": "RED", "finding": f"Low oxygen SpO2 {spo2}%"})
        elif spo2 < 94:
            findings.append({"level": "YELLOW", "finding": f"Borderline oxygen SpO2 {spo2}%"})
    if sbp and dbp:
        if sbp >= 160 or dbp >= 110:
            findings.append({"level": "RED", "finding": f"Severe high BP {sbp}/{dbp}"})
        elif sbp >= 140 or dbp >= 90:
            lvl = "RED" if obs.get("pregnant") else "YELLOW"
            findings.append({"level": lvl, "finding": f"High BP {sbp}/{dbp}" + (" in pregnancy (pre-eclampsia risk)" if obs.get("pregnant") else "")})
    # Indian MoHFW high-risk pregnancy criteria (added after error analysis on UCI data)
    if obs.get("pregnant"):
        if temp and temp >= 38.0 and temp < 39.0:
            findings.append({"level": "YELLOW", "finding": f"Fever {temp}°C in pregnancy - maternal danger sign"})
        if age_m is not None and (age_m < 18 * 12 or age_m >= 35 * 12):
            findings.append({"level": "GREEN", "finding": f"Advisory: maternal age {age_m // 12} years - register as high-risk pregnancy, plan institutional delivery"})
        if obs.get("blood_sugar") and 7.8 <= obs["blood_sugar"] < 11.1:
            findings.append({"level": "YELLOW", "finding": f"Blood sugar {obs['blood_sugar']} mmol/L ≥ 7.8 (DIPSI) - possible gestational diabetes"})
    hr = obs.get("heart_rate")
    if hr and (age_m is None or age_m >= 144):  # adult threshold only
        if hr > 120:
            findings.append({"level": "RED", "finding": f"Severe tachycardia {hr}/min"})
        elif hr > 100:
            findings.append({"level": "YELLOW", "finding": f"Tachycardia {hr}/min"})
    bs = obs.get("blood_sugar")
    if bs:
        if bs >= 11.1:
            lvl = "YELLOW"
            findings.append({"level": lvl, "finding": f"High random blood sugar {bs} mmol/L" + (" (possible gestational diabetes)" if obs.get("pregnant") else "")})
        elif bs < 3.0:
            findings.append({"level": "RED", "finding": f"Low blood sugar {bs} mmol/L"})
    return findings


def check_danger_signs(obs):
    """Tool: scan symptoms for protocol danger signs. Returns list of findings."""
    s = obs.get("symptoms", []) or []
    age_m = obs.get("age_months")
    f = []

    def add(level, text):
        f.append({"level": level, "finding": text})

    # General danger signs (any age, esp. child < 5y)
    if _has(s, "convuls", "fits", "seizure", "fit "):
        add("RED", "Convulsions - general danger sign")
    if _has(s, "unable to drink", "not able to drink", "cannot drink", "not feeding", "unable to breastfeed", "not breastfeeding", "stopped feeding"):
        add("RED", "Unable to drink / breastfeed - general danger sign")
    if _has(s, "vomits everything", "vomiting everything"):
        add("RED", "Vomits everything - general danger sign")
    if _has(s, "lethargic", "unconscious", "not waking", "very sleepy", "drowsy"):
        add("RED", "Lethargic or unconscious - general danger sign")
    if _has(s, "chest indrawing", "chest in-drawing", "ribs pulling"):
        add("RED", "Chest indrawing - severe pneumonia sign")
    if _has(s, "stridor"):
        add("RED", "Stridor in calm child")
    if _has(s, "chest pain"):
        add("RED", "Chest pain - possible cardiac emergency")
    if _has(s, "difficulty breathing", "breathless", "short of breath"):
        add("YELLOW", "Difficulty breathing")

    # Dehydration / diarrhoea
    if _has(s, "sunken eyes") and _has(s, "skin pinch", "lethargic", "unable to drink"):
        add("RED", "Severe dehydration signs")
    elif _has(s, "sunken eyes", "restless", "irritable", "thirsty"):
        if _has(s, "diarr", "loose motion", "watery stool"):
            add("YELLOW", "Some dehydration with diarrhoea")
    if _has(s, "blood in stool", "bloody stool"):
        add("YELLOW", "Blood in stool - dysentery")
    if _has(s, "diarr", "loose motion") and _has(s, "14 days", "two weeks", "2 weeks"):
        add("YELLOW", "Persistent diarrhoea (14+ days)")

    # Maternal danger signs
    if obs.get("pregnant") or _has(s, "pregnan"):
        if _has(s, "bleeding", "blood from vagina", "spotting"):
            add("RED", "Vaginal bleeding in pregnancy")
        if _has(s, "headache") and _has(s, "blurred", "vision", "swelling", "swollen"):
            add("RED", "Severe headache with visual change / swelling - pre-eclampsia")
        elif _has(s, "swelling of face", "swollen face", "swollen hands", "face swelling"):
            add("YELLOW", "Swelling of face/hands in pregnancy")
        if _has(s, "baby not moving", "reduced fetal", "less movement", "no fetal movement", "baby moving less"):
            add("RED", "Reduced fetal movements")
        if _has(s, "water broke", "leaking fluid", "waters broke"):
            add("RED", "Leaking amniotic fluid")
        if _has(s, "severe abdominal pain", "severe stomach pain", "severe belly pain"):
            add("RED", "Severe abdominal pain in pregnancy")

    # Young infant
    if age_m is not None and age_m < 2 and _has(s, "yellow palms", "yellow soles", "jaundice"):
        add("RED", "Young infant jaundice extending to palms/soles")

    # Skin / wound
    if _has(s, "spreading redness", "pus", "red streak"):
        add("YELLOW", "Possible skin infection")
    if _has(s, "snake bite", "dog bite", "burn"):
        add("RED", "Bite / burn - needs facility care")
    return f


def rules_triage(obs):
    """Deterministic triage used as safety floor and as offline fallback."""
    findings = check_danger_signs(obs) + check_vitals(obs)
    level = "GREEN"
    for x in findings:
        level = worse(level, x["level"])
    return level, findings


# Pre-referral / home-care doses (simplified IMNCI style, weight based).
DRUGS = {
    "paracetamol": {"mg_per_kg": 15, "freq": "every 6 hours if fever ≥38.5°C (max 4 doses/day)", "days": 3},
    "amoxicillin": {"mg_per_kg": 40, "freq": "twice daily", "days": 5},
    "ors": {"ml_per_kg": 75, "freq": "over 4 hours (Plan B), then after each loose stool", "days": None},
    "zinc": {"fixed": True, "freq": "once daily", "days": 14},
    "iron_folic_acid": {"fixed": True, "freq": "once daily", "days": 180},
}


def dose_calculator(drug, weight_kg, age_months=None):
    """Tool: weight-based dose. Returns dict or error (agent must recover)."""
    d = (drug or "").lower().strip().replace(" ", "_").replace("-", "_")
    if d in ("ors_solution", "oral_rehydration_salts", "oral_rehydration_solution"):
        d = "ors"
    if d in ("ifa", "iron", "folic_acid"):
        d = "iron_folic_acid"
    if d not in DRUGS:
        return {"error": f"Drug '{drug}' is not on the ASHA formulary. Allowed: {', '.join(DRUGS)}"}
    info = DRUGS[d]
    if d == "zinc":
        mg = 10 if (age_months is not None and age_months < 6) else 20
        return {"drug": "zinc", "dose": f"{mg} mg", "frequency": info["freq"], "days": info["days"]}
    if d == "iron_folic_acid":
        return {"drug": "iron_folic_acid", "dose": "60 mg iron + 500 mcg folic acid (1 tab)", "frequency": info["freq"], "days": info["days"]}
    if not weight_kg:
        return {"error": "weight_kg is required for weight-based dosing - ask the worker to weigh the patient"}
    if d == "ors":
        return {"drug": "ORS", "dose": f"{round(info['ml_per_kg'] * weight_kg)} ml", "frequency": info["freq"]}
    mg = round(info["mg_per_kg"] * weight_kg)
    if d == "paracetamol":
        mg = min(mg, 1000)
    return {"drug": d, "dose": f"{mg} mg", "frequency": info["freq"], "days": info["days"]}
