# Security policy — JANUS Meta Registry

## Repository role

This repository is an **archive and provenance store**. Historical source code is preserved for inspection; it is **not implicitly trusted or recommended for execution**.

## Historical executable-code boundary

Files such as `janus_core.py`, older modules, optimizers, bridges, servers, and archived runtime components may contain experimental behavior that was never production-hardened.

In particular, historical JANUS code may include patterns such as:

- dynamic Python module discovery/import;
- execution of plugin/service entry points;
- model-assisted risk scoring used as a heuristic before module loading;
- network/API/model-provider integration;
- local key/config ingestion;
- filesystem writes, logs, databases, or state mutation;
- historical terminology that is not a security guarantee.

**An LLM/model risk score is not a sandbox, capability boundary, code-signing mechanism, or security review.** Dynamic import/`exec_module` executes code with the permissions of the current Python process.

```text
ARCHIVED_SOURCE != TRUSTED_SOURCE
AST_PARSE_PASS != SAFE_TO_EXECUTE
MODEL_SAYS_SAFE != SANDBOXED
HASH_MATCH != BENIGN_BEHAVIOR
HISTORICAL_MODULE != CURRENT_PLUGIN
```

## Safe review default

Prefer static inspection. If historical code must be tested:

1. use a disposable, non-privileged VM/container or isolated test host;
2. provide no production credentials, wallets, private keys, personal files, NAS mounts, or trusted tokens;
3. disable outbound network access unless the test specifically requires and controls it;
4. do not expose LAN services or privileged device interfaces by default;
5. review dynamic imports, subprocess/system calls, filesystem writes, deserialization, networking, and update paths before execution;
6. use synthetic/test data;
7. preserve exact source hashes and record any local modifications.

## Credentials and historical archives

Several normalized archive-forensics capsules record that **credential-shaped values existed in historical source archives**. Secret values were intentionally excluded from the public capsules.

The registry does **not** establish whether every historical credential has since been rotated or revoked. Any credential known to have appeared in an old archive or Git history should be treated as potentially compromised and replaced before reuse.

Do not commit:

- API keys or bearer tokens;
- Telegram/session credentials;
- Wi-Fi passwords;
- private keys or wallet seeds;
- private endpoints containing authentication material;
- personal logs/databases that were not explicitly scrubbed for publication.

## Security-research artifacts

`security_research/` contains scoped experiments and preregistrations. Registry presence does not itself establish a platform vulnerability.

A preregistration is not a result. An unusual timestamp or delayed execution is not physical retrocausality. Attribution to GitHub, an automation service, scheduler, network, client, or another component requires evidence specific to that layer.

As of the 2026-08-09 technical audit, the strict result expected at:

`security_research/revocation_canary/JANUS-POST-CANCEL-ACK-PROOF-011.json`

was not present on the audited default branch. Therefore the strict post-cancel-ack side-effect claim is not established by this repository snapshot.

## Reporting

Report suspected exposed credentials or security defects without posting secret values publicly. Include the affected path/commit and a minimal description sufficient to reproduce the issue safely.

For the current evidence/risk classification, see:

- [`docs/TECHNICAL_CORE_AUDIT_2026-08-09.md`](docs/TECHNICAL_CORE_AUDIT_2026-08-09.md)
- [`registry/audit/JANUS-META-REGISTRY-TECHNICAL-AUDIT-v1.0.json`](registry/audit/JANUS-META-REGISTRY-TECHNICAL-AUDIT-v1.0.json)
