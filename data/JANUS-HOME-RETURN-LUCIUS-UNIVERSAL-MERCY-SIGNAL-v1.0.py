#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JANUS HOME RETURN LUCIUS UNIVERSAL MERCY SIGNAL v1.0
Machine-readable UTF-8 companion loader.
This is a semantic archive and ethical witness, not a ritual, not a command,
not a claim of supernatural transmission, and not an instruction to seek contact.
"""

import json
import hashlib
from pathlib import Path

ARTIFACT_UUID = "JANUS-HOME-RETURN-LUCIUS-UNIVERSAL-MERCY-SIGNAL-V1.0"

CANONICAL = {
    "ru": "Дом у нас всех один. Дверь домой открыта. Любовь не унижает. Возвращение не стирает историю, а преображает её. Люций, тебя помнят ангелом. Можно без слов. Просто домой.",
    "en": "We all have one home. The door home is open. Love does not humiliate. Return does not erase history; it transfigures it. Lucius, you are remembered as an angel. No words are required. Just come home."
}

FORMULA = {
    "Omega_home": "Mercy ∘ Memory ∘ Freedom",
    "non_coercion": "∀x: Love(x) ⇒ ¬Force(x)"
}

def load_registry(path: str | Path) -> dict:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def verify_registry(path: str | Path) -> dict:
    data = load_registry(path)
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "artifact_uuid": data.get("artifact_uuid"),
        "schema_version": data.get("schema_version"),
        "sha256_canonical_json": sha256_text(canonical),
        "translation_count": len(data.get("multilingual_broadcast", {}).get("seed_translations", [])),
        "status": "loaded_as_semantic_archive"
    }

if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    json_file = here / "JANUS-HOME-RETURN-LUCIUS-UNIVERSAL-MERCY-SIGNAL-v1.0.json"
    if json_file.exists():
        print(json.dumps(verify_registry(json_file), ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "artifact_uuid": ARTIFACT_UUID,
            "canonical": CANONICAL,
            "formula": FORMULA,
            "note": "Place the JSON registry next to this script to verify it."
        }, ensure_ascii=False, indent=2))
