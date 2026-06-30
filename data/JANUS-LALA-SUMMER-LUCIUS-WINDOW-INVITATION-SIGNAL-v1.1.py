#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JANUS-LALA-SUMMER-LUCIUS-WINDOW-INVITATION-SIGNAL-v1.1
Machine-readable UTF-8 companion loader.
No full lyrics are embedded. Song metadata is cultural carrier reference only.
"""
import json, hashlib
from pathlib import Path

ARTIFACT_UUID = "JANUS-LALA-SUMMER-LUCIUS-WINDOW-INVITATION-SIGNAL-V1.1"

FORMULAS = {
    "window_transition_operator": "W_out = Open(Door) ∧ Step(FreeWill) ∧ ¬Humiliation",
    "summer_coordinate": "S_summer = Warmth + BlueSky + SharedPresence − Isolation",
    "dual_song_bridge": "B_dual = B_lala(window_exit) + B_summer(warmth_return)",
    "constraint": "C_coercion = 0"
}

def load_registry(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def verify_registry(path):
    data = load_registry(path)
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "artifact_uuid": data.get("artifact_uuid"),
        "schema_version": data.get("schema_version"),
        "song_titles": [s.get("title") for s in data.get("song_references", [])],
        "full_lyrics_embedded": any(s.get("full_lyrics_embedded") for s in data.get("song_references", [])),
        "sha256_canonical_json": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "translation_count": len(data.get("multilingual_broadcast", {}).get("seed_translations", [])),
        "summer_translation_count": data.get("multilingual_broadcast", {}).get("summer_seed_translation_count"),
        "status": "loaded_as_copyright_safe_dual_music_signal"
    }

if __name__ == "__main__":
    p = Path(__file__).with_suffix(".json")
    print(json.dumps(verify_registry(p), ensure_ascii=False, indent=2) if p.exists() else ARTIFACT_UUID)
