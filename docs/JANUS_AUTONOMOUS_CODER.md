# JANUS admitted autonomous code writer

Owner instruction and ordered roadmap: https://github.com/Hawkar-usls/Janus_Genesis/issues/302
Implementation/acceptance: https://github.com/Hawkar-usls/janus-meta-registry/issues/370

The system authors one small pure function per cycle from a reviewed ten-task catalog. It runs on GitHub-hosted CPU every six hours and after reviewed implementation changes. No new inference API key or provider inference charge is required. Ordinary Actions/cache usage still follows the owner's GitHub plan. PC, NAS and an open chat are unnecessary for this cloud lane.

The author uses Qwen/Qwen2.5-Coder-0.5B-Instruct, Apache-2.0, revision ea3f2471cf1b1f0db85067f1ef93848e38e88c25. Model weights and every tokenizer/config file are verified before loading; only safetensors are loaded, remote model code is disabled. These are external open weights, never attributed to JANUS's native 446208-parameter model. Source: https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct

The author has no source-write credential and never executes its generated code. Two actual model responses and their exact extracted source are preserved. No hand-written successful function is substituted if generation fails. The first response is greedy; the second uses a run-specific sampling seed. Duplicate responses remain visible in their hashes and do not establish diverse variants.

A separate clean job validates syntax/admission, then executes each candidate in a pinned Python container without network, credentials, privileged capabilities or writable host mounts. CPU, time, memory and process counts are limited. At least 200 fresh independently selected functional cases check output types, edge behavior and input mutation. Model prose, a syntactically valid function and a green author job are insufficient for promotion.

A separate publisher, which never executes model code, binds exact bundle, source, evaluator, model, image and prior-state hashes. It writes only STATE.json, ROADMAP.md, attempts/, receipts/ and generated/ on janus/autonomous-code-state. Both accepted and rejected variants are retained. Normal Git push rejects a competing head; replay is idempotent and conflicting/stale input is held. There is no main merge, permission edit, secret management, arbitrary task path or automatic authority expansion.

Another clean worker reconstructs only the exact persisted state commit, verifies the accepted source/receipt binding, independently retests the function in the restricted container and calls it. Later use by a reviewed runtime adapter remains separately observable; a library test does not establish all-organ consumption.

The queue advances only after a verified promotion; failed work remains queued and preserves the previous working extension. After all admitted tasks are complete the writer reports IDLE. Adding new task families, changing the oracle or extending effectful permissions requires reviewed implementation. This bounded library is infrastructure for self-maintenance, not proof of universal autonomous programming, G1–G20, long-term reliability or independent scientific value. The main roadmap's current phase and prerequisites remain unchanged.
