"""Validate ASHA Saathi on real antenatal records (UCI Maternal Health Risk).

    python3 eval_maternal.py            # rules on all rows + full Gemma agent on 12-row stratified sample
    python3 eval_maternal.py --rules    # rules only (instant)

Metric: the dataset's "high risk" is not identical to our RED ("refer today"), so we
report ESCALATION RECALL - share of high-risk women sent to a facility (YELLOW or RED) -
and over-referral of low-risk women. Results -> data/eval_results.md
"""
import json
import os
import sys
import time

os.environ.setdefault("ASHA_DB", os.path.join(os.path.dirname(__file__), "data", "eval.db"))

import dataset  # noqa: E402
import protocols as P  # noqa: E402

LABELS = ["high risk", "mid risk", "low risk"]


def table(counts):
    lines = ["| Dataset label | n | → RED | → YELLOW | → GREEN | escalated (Y+R) |", "|---|---|---|---|---|---|"]
    for lab in LABELS:
        c = counts.get(lab, {})
        n = sum(c.values())
        if not n:
            continue
        esc = c.get("RED", 0) + c.get("YELLOW", 0)
        lines.append(f"| {lab} | {n} | {c.get('RED', 0)} | {c.get('YELLOW', 0)} | {c.get('GREEN', 0)} | {esc}/{n} ({100 * esc / n:.0f}%) |")
    return "\n".join(lines)


def rules_eval():
    counts = {}
    for r in dataset.load():
        case = dataset.to_case(r)
        obs = dict(case["vitals"], pregnant=True, age_months=case["age_years"] * 12, symptoms=[])
        lvl, _ = P.rules_triage(obs)
        counts.setdefault(case["label"], {}).setdefault(lvl, 0)
        counts[case["label"]][lvl] += 1
    return counts


def agent_eval():
    import agent
    import store
    if os.path.exists(os.environ["ASHA_DB"]):
        os.remove(os.environ["ASHA_DB"])
    store.db()
    counts, rows = {}, []
    for r in dataset.sample():
        case = dataset.to_case(r)
        pid = store.ins("INSERT INTO patients(name,age_months,sex,village,pregnant,created) VALUES(?,?,?,?,?,?)",
                        (f"UCI row {case['row']}", case["age_years"] * 12, "F", "dataset", 1, time.time()))
        events = []
        res = agent.run_visit(pid, case["complaint"], case["vitals"], None, events.append)
        overrides = [e for e in events if e["kind"] == "guardrail" and e["data"]["override"]]
        model_level = next((e["data"]["triage"] for e in events if e["kind"] == "decision"), None)
        counts.setdefault(case["label"], {}).setdefault(res["triage"], 0)
        counts[case["label"]][res["triage"]] += 1
        rows.append({"row": case["row"], "label": case["label"], "vitals": case["vitals"], "gemma": model_level,
                     "final": res["triage"], "guardrail_override": bool(overrides), "handoff": res["handoff"],
                     "seconds": round(res["total_ms"] / 1000, 1), "degraded": res["degraded"]})
        print(json.dumps(rows[-1]), flush=True)
    return counts, rows


if __name__ == "__main__":
    out = ["# ASHA Saathi - validation on UCI Maternal Health Risk (real antenatal records)\n"]
    rc = rules_eval()
    out += ["## Protocol guardrail alone - all 1,014 records\n", table(rc), ""]
    print(table(rc))
    if "--rules" not in sys.argv:
        ac, rows = agent_eval()
        secs = sorted(r["seconds"] for r in rows)
        out += ["## Full on-device agent (Gemma 4 E2B + guardrail) - stratified sample of 12\n", table(ac), "",
                f"- Gemma's own decision was escalated by the guardrail in **{sum(r['guardrail_override'] for r in rows)}/{len(rows)}** cases",
                f"- Human handoff triggered in **{sum(r['handoff'] for r in rows)}/{len(rows)}** cases",
                f"- Median time per visit: **{secs[len(secs) // 2]} s** on an 8 GB laptop (Apple A18 Pro), fully offline", "",
                "| CSV row | label | BP | BS | HR | Gemma | final | override | handoff | s |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            v = r["vitals"]
            out.append(f"| {r['row']} | {r['label']} | {v['bp_systolic']:.0f}/{v['bp_diastolic']:.0f} | {v['blood_sugar']} | {v['heart_rate']:.0f} | {r['gemma']} | {r['final']} | {'yes' if r['guardrail_override'] else ''} | {'yes' if r['handoff'] else ''} | {r['seconds']} |")
    out += ["", "Note: the dataset's 'high risk' label is not identical to our RED ('refer today'); escalation = YELLOW or RED (sent to a facility)."]
    if "--rules" not in sys.argv:  # a quick rules-only run must not overwrite the full results
        with open(os.path.join(os.path.dirname(__file__), "data", "eval_results.md"), "w") as f:
            f.write("\n".join(out) + "\n")
        print("\nwrote data/eval_results.md")
