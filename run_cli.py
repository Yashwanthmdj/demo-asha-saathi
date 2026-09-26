"""Headless demo: run the ASHA Saathi agent on the demo cases and print the trace.

Used by the Kaggle notebook (public live demo) and for quick local testing:
    python3 run_cli.py            # all demo cases
    python3 run_cli.py 2          # just case #2
"""
import json
import sys

import agent
import store

CASES = [
    ("Sick infant (expect RED)", 1, "Fever since 2 days, breathing very fast, not breastfeeding since morning, very sleepy",
     {"temperature_c": 39.2, "resp_rate": 58, "weight_kg": 7.8}),
    ("Pregnancy headache (expect RED)", 2, "7 months pregnant. Severe headache since yesterday, blurred vision, swelling of face and feet",
     {"bp_systolic": 152, "bp_diastolic": 102}),
    ("Diarrhoea (expect YELLOW)", 3, "Loose motions for 3 days, 6 times a day, very thirsty, drinking eagerly, sunken eyes, playing a little",
     {"temperature_c": 37.8, "weight_kg": 12}),
    ("Telugu mild cough (expect GREEN)", 5, "రెండు రోజులుగా జలుబు, దగ్గు. బాగా ఆడుకుంటున్నాడు, అన్నం తింటున్నాడు",
     {"temperature_c": 37.9, "resp_rate": 30, "weight_kg": 12}),
]

ICON = {"SENSE": "①", "DECIDE": "②", "ACT": "③", "CHECK": "④", "DONE": "✔", "ERROR": "✖"}


def show(ev):
    d = ev["data"]
    if ev["kind"] == "result":
        print(f"\n  ==> TRIAGE {d['triage']} | handoff={d['handoff']} | {d['llm_calls']} Gemma calls, {d['total_ms'] / 1000:.1f}s total")
        print("  Plan:", *[f"\n    - {s}" for s in d["plan"].get("care_plan", [])])
        print("  Telugu:", d["plan"].get("telugu_summary", ""))
        return
    print(f"  {ICON.get(ev['phase'], '·')} {ev['phase']:<6} {ev['kind']:<12} {json.dumps(d, ensure_ascii=False)[:180]}")


if __name__ == "__main__":
    store.db()
    pick = [int(a) - 1 for a in sys.argv[1:]] or range(len(CASES))
    for i in pick:
        name, pid, text, vitals = CASES[i]
        print(f"\n=== Case {i + 1}: {name} ===")
        agent.run_visit(pid, text, vitals, None, show)
