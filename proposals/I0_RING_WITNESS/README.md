# JANUS I0 — Ring Witness

## The Witness at the Horizon

Ring Witness is a proposed passive Linux eBPF observation layer for JANUS I0.

Its purpose is not to control SHA-256, replace Native Gate, or modify proof semantics. Its purpose is to provide an independent operating-system witness for what the runtime says happened.

## Why it exists

JANUS already records application-level events such as:

- admission;
- submission;
- finalization;
- exposure;
- wave epoch;
- drain and vacuum boundaries.

Those records are essential, but the runtime should not have to testify about itself alone.

A passive kernel witness can help distinguish:

- work admitted but not yet submitted;
- work submitted but not scheduled;
- work scheduled but preempted;
- work completed but waiting in IPC;
- work observed by the root process but not yet FINALIZED;
- a true reconnect from a merely delayed application record.

## Architecture

```text
Native Gate
  runtime admission executor

TimeShift / Through the Horizon
  coordinator and decision layer

Look-Away Observer
  durable application evidence

Ring Witness
  independent OS-level attestation

SystemMonitor
  physical-cost sensor layer
```

V0.1 is strictly passive:

```text
Linux runtime
→ eBPF CO-RE hooks
→ BPF ring buffer
→ user-space collector
→ hash-linked Ring Witness ledger
→ comparison with JANUS Observer
```

No work is blocked, reprioritized, accelerated or modified.

## First experiment

**Internal Observer versus Kernel Ring Witness**

The experiment should compare a continuous baseline, Native Gate HOLD/drain, Through-the-Horizon FREEZE/HOLD/THAW/REOPEN, and a timestamp-matched sham.

A PASS requires:

- stable process and session lineage;
- independent observation of reconnects;
- admissible worker execution lineage for each submitted batch;
- no unexplained worker epoch;
- explicit clock uncertainty;
- fail-closed treatment of missing correlations;
- no control action originating from Ring Witness.

## Research questions

Ring Witness may help JANUS separate five boundaries that application counters currently compress:

1. admission horizon;
2. submission horizon;
3. scheduler horizon;
4. completion horizon;
5. Observer horizon.

It may also strengthen:

- Hidden Capacity Atlas;
- Horizon Echo;
- Foam Fingerprint;
- phase-lag cartography;
- runtime carryover and wave-memory controls.

## Enforcement boundary

No enforcement is authorized in V0.1.

Possible future guards such as BPF LSM or cgroup policy require a separate safety review after passive observation is validated. `bpf_override_return()` must never be treated as a universal mechanism for arbitrary kernel functions.

## Current sequencing

The immediate JANUS I0 priority remains closing the A18.43 Through-the-Horizon Windows BEACON. Ring Witness is a parallel future Linux line and must not destabilize or delay that work.

## Claim limits

This proposal does not claim:

- a working Linux implementation;
- arbitrary kernel hot patching;
- energy savings;
- hardware-lifetime extension;
- SHA-256 memory or weakness;
- valid-proof advantage;
- mining advantage or profitability.

The first deliverable is an auditable design contract and safe Linux laboratory plan.
