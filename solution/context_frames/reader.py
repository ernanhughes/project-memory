"""The reader stage: the same model, prompt and temperature for every
condition, so a difference in answers is a difference in context.

Chapter 3's generator settings are reused unchanged -- llama3.1:8b at
temperature zero, with a system prompt that forbids guessing and asks
for evidence identifiers -- because the comparison contract requires the
reader to be a fixed variable. Answers are cached by the hash of the
exact prompt, so a frozen run replays without re-querying the model.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_READER = "llama3.1:8b"
DEFAULT_OLLAMA = "http://localhost:11434"
CACHE_DIR = Path(__file__).resolve().parent / ".reader-cache"

SYSTEM_PROMPT = (
    "Answer questions about a software project's recorded history and its "
    "current state. Use only the supplied project evidence. Name the evidence "
    "identifiers you rely on. If the evidence does not determine an answer, "
    "say so plainly instead of guessing. Distinguish what is current from "
    "what has been superseded, and what was decided from what was merely "
    "proposed."
)


class Reader:
    def __init__(self, model: str = DEFAULT_READER,
                 host: str = DEFAULT_OLLAMA,
                 cache_dir: Path = CACHE_DIR) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return f"ollama:{self.model}@t0"

    def available(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.host}/api/tags", timeout=3).read()
            return True
        except (urllib.error.URLError, OSError):
            return False

    @staticmethod
    def build_prompt(objective: str, query: str, context: str) -> str:
        return (f"Current objective: {objective}\n\n"
                f"Question: {query}\n\n"
                f"Project evidence:\n\n{context}\n\n"
                f"Answer the question for the stated objective.")

    def ask(self, prompt: str) -> str:
        key = hashlib.sha256(
            f"{self.model}\x00{SYSTEM_PROMPT}\x00{prompt}".encode()
        ).hexdigest()[:40]
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())["response"]
        payload = json.dumps({
            "model": self.model, "prompt": prompt, "system": SYSTEM_PROMPT,
            "stream": False, "options": {"temperature": 0.0, "seed": 7},
        }).encode()
        request = urllib.request.Request(
            f"{self.host}/api/generate", data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=600) as response:
            out = json.load(response)
        answer = out.get("response", "").strip()
        path.write_text(json.dumps({"prompt": prompt, "response": answer}))
        return answer
