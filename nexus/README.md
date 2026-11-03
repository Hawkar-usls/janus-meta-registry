# JANUS NEXUS — public evidence console

GitHub Pages URL: https://hawkar-usls.github.io/janus-meta-registry/nexus/

## Architecture

- Host: existing Hawkar-usls/janus-meta-registry Pages site, no new server, worker, or NAS process.
- UI: nexus/index.html, nexus/styles.css, nexus/app.js; vanilla JavaScript, no external libraries.
- Evidence: public data/autonomy_loop/LATEST.json, CHECKPOINT.json, ROADMAP.md and the receipt referenced by LATEST.json.
- Refresh: on load, on manual request, on tab visibility, and every two minutes while visible.
- PWA: sw.js caches only the static UI shell. Evidence is always fetched from the network.
- Authority delta: ZERO. No tokens, API writes, remote commands, model launches, paid actions, CAS updates, or auto-merges.

## Interpretation and trust

The system status is the snapshot's reported status, NOT proof that software is currently running. A cited source means a commit/receipt appears in public evidence; it does not attest process health. Stale (>2 hours), missing or mismatched evidence is clearly marked. Never infer AUTONOMY_FULL from a healthy website, a collector success, or a source reference.

The displayed native-model promotion counter is not a count of independently validated DADDY_KEYMASTER champion CAS promotions.

## Security invariants

1. Only accept receipt paths within the predefined data/autonomy_loop/receipts/ directory and 24 lowercase hex stem.
2. Latest JSON schema and receipt phase/status must agree.
3. Insert untrusted strings using textContent, never as HTML.
4. No private-repository sources, auth secrets, GitHub write API or arbitrary remote URLs.
5. On fetch failure, replace metrics with UNKNOWN; do not present old numbers as live.
6. The dashboard does not change the source-of-truth or grant new authority.
7. Data fetches are restricted by a same-origin Content Security Policy.

## Deployment

This folder lives in the existing registry Pages repository. A reviewed merge to main uses the existing Pages publishing configuration. No separate Pages site, workflow, or permanent server is required.

For preview from the repository root: python -m http.server 8080
Then open http://localhost:8080/nexus/. Direct file:// URLs cannot fetch JSON.

## Maintenance

Roadmap metrics and phases are optional and gracefully degrade if ROADMAP.md changes. Primary state always comes from LATEST.json and its receipt. Avoid introducing a second worker that writes competing autonomy snapshots.
