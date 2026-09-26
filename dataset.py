"""Real-world validation data: UCI Maternal Health Risk dataset (Ahmed et al.).

1,014 antenatal records from rural Bangladesh health care (IoT risk monitoring):
Age, SystolicBP, DiastolicBP, BS (blood sugar, mmol/L), BodyTemp (°F), HeartRate, RiskLevel.
Source: https://archive.ics.uci.edu/dataset/863/maternal+health+risk (CC BY 4.0)
"""
import csv
import os
import random

PATH = os.path.join(os.path.dirname(__file__), "data", "maternal_health_risk.csv")


def load():
    with open(PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        r["row"] = i + 2  # line number in the CSV, for traceability
    return rows


def to_case(r):
    """Map a dataset row to what an ASHA worker would record at a home visit."""
    vitals = {
        "bp_systolic": float(r["SystolicBP"]),
        "bp_diastolic": float(r["DiastolicBP"]),
        "temperature_c": round((float(r["BodyTemp"]) - 32) * 5 / 9, 1),
        "heart_rate": float(r["HeartRate"]),
        "blood_sugar": float(r["BS"]),
    }
    complaint = "Pregnant woman, antenatal home visit. No specific complaints reported. Vitals measured by ASHA."
    return {"age_years": int(r["Age"]), "vitals": vitals, "complaint": complaint, "label": r["RiskLevel"], "row": r["row"]}


def sample(n_high=6, n_mid=3, n_low=3, seed=7):
    rows = load()
    rnd = random.Random(seed)
    out = []
    for label, n in (("high risk", n_high), ("mid risk", n_mid), ("low risk", n_low)):
        out += rnd.sample([r for r in rows if r["RiskLevel"] == label], n)
    return out
