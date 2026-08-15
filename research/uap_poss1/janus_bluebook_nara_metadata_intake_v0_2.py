#!/usr/bin/env python3
"""JANUS Blue Book NARA metadata intake v0.2.

NARA's public bulk page places textual/microfilm ZIPs under a format-specific
subdirectory. Reuse the v0.1 fail-transparent parser while correcting only the
public archive resolver; scientific/date semantics are unchanged.
"""
import janus_bluebook_nara_metadata_intake_v0_1 as base

base.RUNNER_ID = "JANUS-BLUEBOOK-NARA-METADATA-INTAKE-v0.2"
base.NARA_ZIP_URL = "https://catalog.archives.gov/medialz/bulk-downloads/uaps/zips/textual-and-microfilm/595466.zip"

if __name__ == "__main__":
    base.main()
