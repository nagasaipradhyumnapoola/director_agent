"""Real-model end-to-end check: can the agent call route/recipe by itself?"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from director.agent import run_agent  # noqa: E402
from director.keychain import get_secret  # noqa: E402
from director.store import Store  # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "llama-3.3-70b-fp8-fast"
PROVIDER = sys.argv[2] if len(sys.argv) > 2 else "proxy"
BASE = "http://127.0.0.1:31415/v1"
SECRET = "provider/freellm"


def main() -> int:
    store = Store.open(ROOT)
    try:
        key = get_secret(store.project_id, SECRET)
        if not key:
            raise SystemExit("no proxy key in keychain")

        def model_fn(prompt: str) -> str:
            messages = [
                {"role": "system", "content": "Return exactly one JSON object. No prose. Use the tools in the prompt."},
                {"role": "user", "content": prompt},
            ]
            if PROVIDER == "ollama":
                payload = json.dumps(
                    {"model": MODEL, "messages": messages, "stream": False, "options": {"temperature": 0.1, "num_predict": 300}}
                ).encode("utf-8")
                request = urllib.request.Request(
                    "http://127.0.0.1:11434/api/chat",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=300) as response:
                    parsed = json.loads(response.read().decode("utf-8"))
                return str(parsed["message"]["content"])
            payload = json.dumps(
                {"model": MODEL, "messages": messages, "temperature": 0.1, "max_tokens": 300}
            ).encode("utf-8")
            request = urllib.request.Request(
                BASE + "/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            return str(parsed["choices"][0]["message"]["content"])

        result = run_agent(
            store,
            "Route a design task and compute slugify for 'Straße'; then finish.",
            model_fn=model_fn,
            max_steps=5,
            timeout=90,
        )
        transcript = json.dumps(result["transcript"])
        output = {
            "model": MODEL,
            "status": result["status"],
            "steps": result["steps"],
            "used_route": '"tool": "route"' in transcript,
            "used_recipe": '"tool": "recipe"' in transcript,
            "transcript": result["transcript"],
        }
        out = ROOT / "benchmarks" / "results" / "agent_e2e.json"
        out.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps({k: output[k] for k in ("model", "status", "steps", "used_route", "used_recipe")}, indent=2))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
