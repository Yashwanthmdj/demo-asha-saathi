"""Minimal local Gemma 4 client via Ollama (stdlib only, no cloud)."""
import json
import os
import time
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("ASHA_MODEL", "gemma4:e2b-it-qat")
TIMEOUT = int(os.environ.get("ASHA_LLM_TIMEOUT", "120"))


class LLMError(Exception):
    pass


def available():
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=2) as r:
            names = [m["name"] for m in json.load(r).get("models", [])]
        return MODEL in names, names
    except Exception:
        return False, []


def chat_json(system, user, schema, images=None, max_tokens=512, temperature=0.2):
    """Call Gemma with a JSON schema constraint. Returns (dict, ms).

    Raises LLMError on transport failure or unparseable output so the agent
    can retry / fall back.
    """
    msg = {"role": "user", "content": user}
    if images:
        msg["images"] = images
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, msg],
        "stream": False,
        "format": schema,
        "think": False,
        "keep_alive": "60m",
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            out = json.load(r)
    except Exception as e:
        raise LLMError(f"local model unreachable: {e}")
    ms = int((time.time() - t0) * 1000)
    text = out.get("message", {}).get("content", "")
    try:
        return json.loads(text), ms
    except json.JSONDecodeError:
        raise LLMError(f"invalid JSON from model: {text[:200]}")


def warm_up():
    """Load the model into memory at startup so the first visit is fast."""
    try:
        chat_json("Reply with JSON.", "ok", {"type": "object", "properties": {"ok": {"type": "boolean"}}}, max_tokens=8)
    except LLMError:
        pass
