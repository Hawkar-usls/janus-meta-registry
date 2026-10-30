# JANUS autonomous roadmap loop v1

Canonical human roadmap: https://github.com/Hawkar-usls/Janus_Genesis/issues/302

The cloud workflow runs hourly and on reviewed implementation changes. GitHub schedules may be delayed. It does not rely on an owner PC, NAS, local model daemon or chat remaining alive.

The loop freezes each public Git ref, reads JSON at exact commits, records raw SHA-256 and Git blob SHA, derives current findings, regenerates an ordered roadmap and persists immutable receipts. A separate worker rereads exact source bytes and verifies the derived result before recording phase acceptance.

Live files:
- data/autonomy_loop/ROADMAP.md — automatically regenerated priorities, work/idle/degraded metrics and evidence-driven tasks.
- data/autonomy_loop/LATEST.json — last observed state and immutable receipt pointer.
- data/autonomy_loop/CHECKPOINT.json — verified continuation and accepted phases.
- data/autonomy_loop/receipts/ — preserved observations, including faults and unknown sources.

The approved order is P0.1 through P0.6, then P1 through P5. Findings can add bounded tasks inside their phase; they cannot reorder prerequisites or grant capabilities. An absent verifier or implementation remains WAIT/HOLD.

v1 implements observation, roadmap regeneration, preservation and independently verified P0.1 continuation. Later mutation handlers require reviewed executable code and their own acceptance evidence. A successful collector does not imply a code change, model synthesis, source synchronization, scientific validation or full #162 acceptance.

No provider API is called and no Rowan credits are spent. Reads are fixed to public status metadata. Runtime writes are limited to this repository's data/autonomy_loop/ surface. Model/issue text is not executed. No source-history deletion, force push, arbitrary shell command, automatic main-code merge, secret management or authority expansion is present.

