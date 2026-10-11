# A18.43 V0.2.5 Fail-Closed / V0.2.6 Offline Status

## Result

V0.2.5 remains a preserved failed live BEACON. Its exact cause was a mixed counter-authority sample: native append-only ledgers already contained two reopened submissions, while the shadow checkpoint still reported the pre-reopen submitted total. The first reopened exposure therefore produced a false `REOPEN_EXPOSURE_EXCEEDS_SUBMISSIONS` interlock.

The supervisor intentionally stopped the child with Ctrl+Break. Exit `0xC000013A` is not classified as a spontaneous runtime crash. The authoritative accounting is:

```text
18 submitted = 17 completed + 1 unfinished
2,244,000 checked = 2,244,000 committed exact exposure
```

No evidence establishes what happened inside the second reopened worker after future registration, so that state remains unknown rather than being guessed.

## V0.2.6

V0.2.6 replaces the stale submitted checkpoint as decision authority with validated unique `SUBMIT_REGISTERED` records from the native gate event hash chain. It also separates legacy externally observed T0 from true pre-open zero, requires full per-batch lineage, and holds the terminal barrier for at least two observations and 100 ms.

Offline validation passed 17/17 gates, including 35 supervisor self-tests, 19 regressions reconstructed from the real V0.2.5 timeline, 1000 persistent cycles, 5000 illegal transitions, and a fresh archive extraction that passed all 17 gates again.

## Live Boundary

No V0.2.6 live BEACON was run. The root policy has no A18.43 V0.2.6 live exception. Capacity and wave-memory stages therefore remain not run. A reviewed policy amendment and a fresh explicit operator authorization are required before any real-pool contact.

## Claim Boundary

This record establishes an operational diagnosis and an offline-tested repair. It does not establish SHA-256 weakness or memory, valid-proof advantage, mining advantage, profitability, whole-system energy saving, or hardware-lifetime extension.
