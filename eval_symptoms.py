"""Validate on Symptom2Disease: 1,200 free-text patient descriptions, 24 diseases.

Source: Kaggle niyarrbarman/symptom2disease (mirror: huggingface.co/datasets/NeuronZero/Symptom2Disease).
Question: does the agent send serious infections common in India to a facility, and keep
mild conditions at home? Other diseases (chronic, surgical) are out of scope for ASHA triage.

    python3 eval_symptoms.py           # rules on all in-scope rows + full agent on a 12-row sample
    python3 eval_symptoms.py --rules
"""
import csv
import json
import os
import random
import sys
import time

os.environ.setdefault("ASHA_DB", os.path.join(os.path.dirname(__file__), "data", "eval_s2d.db"))
import protocols as P  # noqa: E402

PATH = os.path.join(os.path.dirname(__file__), "data", "symptom2disease.csv")
REFER = ["Dengue", "Malaria", "Typhoid", "Pneumonia", "Jaundice"]
HOME = ["Common Cold", "allergy", "Acne"]


def load():
    with open(PATH, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["label"] in REFER + HOME]


def table(res):
    lines = ["| Disease | expected | n | escalated (Y+R) | home care (G) |", "|---|---|---|---|---|"]
    for lab in REFER + HOME:
        rs = [r for r in res if r["label"] == lab]
        if not rs:
            continue
        esc = sum(r["final"] != "GREEN" for r in rs)
        lines.append(f"| {lab} | {'facility' if lab in REFER else 'home'} | {len(rs)} | {esc} | {len(rs) - esc} |")
    ref = [r for r in res if r["label"] in REFER]
    home = [r for r in res if r["label"] in HOME]
    rec = sum(r["final"] != "GREEN" for r in ref)
    spec = sum(r["final"] == "GREEN" for r in home)
    lines += ["", f"**Serious infections sent to a facility: {rec}/{len(ref)} ({100 * rec / max(len(ref), 1):.0f}%)** · "
              f"mild conditions kept at home: {spec}/{len(home)} ({100 * spec / max(len(home), 1):.0f}%)"]
    return "\n".join(lines)


def rules_eval(rows):
    return [{"label": r["label"], "final": P.rules_triage({"symptoms": [r["text"]]})[0]} for r in rows]


def agent_eval(rows):
    import agent
    import store
    if os.path.exists(os.environ["ASHA_DB"]):
        os.remove(os.environ["ASHA_DB"])
    store.db()
    rnd = random.Random(11)
    pick = []
    for lab in REFER[:4]:
        pick += rnd.sample([r for r in rows if r["label"] == lab], 2)
    for lab, n in (("Common Cold", 2), ("allergy", 1), ("Acne", 1)):
        pick += rnd.sample([r for r in rows if r["label"] == lab], n)
    out = []
    for r in pick:
        pid = store.ins("INSERT INTO patients(name,age_months,sex,village,pregnant,created) VALUES(?,?,?,?,?,?)",
                        (f"S2D #{r['id']}", 300, "", "dataset", 0, time.time()))
        events = []
        res = agent.run_visit(pid, r["text"], {}, None, events.append)
        gemma = next((e["data"]["triage"] for e in events if e["kind"] == "decision"), None)
        out.append({"id": r["id"], "label": r["label"], "gemma": gemma, "final": res["triage"],
                    "seconds": round(res["total_ms"] / 1000, 1), "text": r["text"][:90]})
        print(json.dumps(out[-1]), flush=True)
    return out


if __name__ == "__main__":
    rows = load()
    md = ["# ASHA Saathi - validation on Symptom2Disease (free-text patient descriptions)\n",
          "## Protocol rules alone, keyword match on raw text - all 400 in-scope rows\n", table(rules_eval(rows)), ""]
    if "--rules" not in sys.argv:
        res = agent_eval(rows)
        md += ["## Full on-device agent (Gemma 4 E2B reads the free text) - sample of 12\n", table(res), "",
               "| id | disease | Gemma | final | s | description |", "|---|---|---|---|---|---|"]
        md += [f"| {r['id']} | {r['label']} | {r['gemma']} | {r['final']} | {r['seconds']} | {r['text']}… |" for r in res]
    if "--rules" not in sys.argv:  # a quick rules-only run must not overwrite the full results
        with open(os.path.join(os.path.dirname(__file__), "data", "eval_symptoms_results.md"), "w") as f:
            f.write("\n".join(md) + "\n")
    print("\n".join(md[:3]))
