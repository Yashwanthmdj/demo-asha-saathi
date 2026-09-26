"""Probe Gemma 4 E2B's on-device image understanding on ASHA-relevant photos.

Skin: ahmed-ai/skin-lesions-classification-dataset (Measles, Chickenpox, HFMD, Healthy)
Eyes: Yahaira/anemia-eyes (inner-eyelid photos, Anemia / NoAnemia)
Each image gets ONE Gemma call (the same call the SENSE phase makes for a photo).

    python3 eval_images.py
"""
import base64
import json
import os
import time

import llm

HERE = os.path.dirname(__file__)
SKIN = {"type": "object", "properties": {
    "description": {"type": "string"},
    "rash_type": {"type": "string", "enum": ["measles", "chickenpox", "hand-foot-mouth", "normal skin", "other"]},
    "needs_referral": {"type": "boolean"}}, "required": ["description", "rash_type", "needs_referral"]}
EYE = {"type": "object", "properties": {
    "description": {"type": "string"},
    "pallor": {"type": "boolean"}}, "required": ["description", "pallor"]}
SYS = "You are assisting a community health worker in rural India. Look carefully at the photo. Reply only with JSON."
TRUTH_SKIN = {"Measles": "measles", "Chickenpox": "chickenpox", "HFMD": "hand-foot-mouth", "Healthy": "normal skin"}

if __name__ == "__main__":
    man = json.load(open(os.path.join(HERE, "data", "images", "manifest.json")))
    rows = []
    for m in man:
        b64 = base64.b64encode(open(os.path.join(HERE, m["file"]), "rb").read()).decode()
        skin = m["label"] in TRUTH_SKIN
        prompt = ("Photo of a patient's skin. Describe the lesions in one sentence and classify the rash." if skin else
                  "Photo of a patient's lower inner eyelid (conjunctiva) pulled down. Is the conjunctiva pale (pallor, sign of anaemia) "
                  "rather than healthy pink-red? Describe the colour in one sentence.")
        t0 = time.time()
        try:
            out, _ = llm.chat_json(SYS, prompt, SKIN if skin else EYE, images=[b64], max_tokens=150)
        except llm.LLMError as e:
            out = {"error": str(e)[:80]}
        pred = out.get("rash_type") if skin else ("Anemia" if out.get("pallor") else "NoAnemia") if "pallor" in out else None
        truth = TRUTH_SKIN.get(m["label"], m["label"])
        rows.append({"file": os.path.basename(m["file"]), "label": m["label"], "pred": pred, "correct": pred == truth,
                     "desc": out.get("description", out.get("error", ""))[:90], "s": round(time.time() - t0, 1)})
        print(json.dumps(rows[-1]), flush=True)

    def acc(sel):
        r = [x for x in rows if sel(x)]
        return f"{sum(x['correct'] for x in r)}/{len(r)}"
    md = ["# ASHA Saathi - on-device image understanding probe (Gemma 4 E2B, QAT)\n",
          "| Task | correct |", "|---|---|",
          f"| Skin rash type (measles / chickenpox / HFMD / healthy) | {acc(lambda x: x['label'] in TRUTH_SKIN)} |",
          f"| Measles recognised | {acc(lambda x: x['label'] == 'Measles')} |",
          f"| Anaemia pallor from eyelid photo | {acc(lambda x: x['label'] in ('Anemia', 'NoAnemia'))} |", "",
          "| image | truth | Gemma | ok | s | Gemma's description |", "|---|---|---|---|---|---|"]
    md += [f"| {r['file']} | {r['label']} | {r['pred']} | {'✅' if r['correct'] else '❌'} | {r['s']} | {r['desc']} |" for r in rows]
    open(os.path.join(HERE, "data", "eval_images_results.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md[:6]))
