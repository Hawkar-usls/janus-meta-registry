# THE MAGIC KEY

**The Magic Key** is a JANUS meta-registry research branch for treating JSON as more than a transport syntax.

The branch asks a precise question: can a JSON object become a **constraint-defined meta-object** in which data, schema cues, provenance, graph relations, falsifiable tests, and a declarative state machine coexist without collapsing the boundary between **data** and **executable authority**?

## Seed intuition

The user-provided Trinity relation diagram is used only as a structural example. Its useful feature is not theology; it is the pattern:

- several nodes share a positive relation (`IS -> GOD`);
- those same nodes remain distinct through negative relations (`IS NOT -> each other`);
- the identity of a node therefore depends on the **whole constraint pattern**, not one label.

THE MAGIC KEY generalizes this into **constraint-defined identity**.

## Core research object

A **magic key** is defined here as a minimal or near-minimal subset of frozen constraints that still uniquely distinguishes one registered state/object from all alternatives.

That yields falsifiable questions:

1. Does positive + negative constraint closure recover identity better than IDs alone under perturbation?
2. Can JSON be projected to a labeled graph and back without losing canonical semantic distinctions?
3. Can instance data and schema constraints swap roles and round-trip usefully?
4. Can we measure **semantic collisions** separately from cryptographic hash collisions?
5. Can one JSON file describe a safe declarative algorithm while remaining non-executable data?

## Algorithm inside JSON

`the_magic_key.v1.json` embeds a declarative `MAGIC_KEY_META_LOOP` derived from the JANUS algorithm spiral:

`SEARCH_GRAMMAR + REPRESENTATION_GRAMMAR + INTERFACE_GRAMMAR`

TOPA/Spider discovers antecedents; candidate representation keys are generated and ranked; falsification and reverse projection follow; a result is frozen only after a holdout.

The file does **not** execute itself. An external interpreter must implement a tiny allowlisted operation vocabulary. Shell, eval/exec, arbitrary network, secret access and arbitrary file writes are forbidden.

## Internal TOPA + Spider result

The meta-registry already contains strong antecedents for canonicalization, provenance, observer separation, reversible gates, JSON-native event records, hash lineage and representation-grammar search. Those are explicitly **not claimed as new**.

The synthesis candidates unique to this branch are narrower:

- identity as closure of positive **and negative** JSON constraints;
- the minimal distinguishing constraint subgraph as a machine-checkable `MAGIC_KEY`;
- one auditable artifact combining dataset + schema declaration + research program + declarative state machine;
- data/schema role-swap experiments;
- semantic-collision resistance as a separate metric from cryptographic collision resistance.

External novelty is **UNESTABLISHED** until a dedicated outside prior-art sweep is run.

## First gates

Run in order:

1. `E1_CANONICALIZATION_INVARIANCE`
2. `E6_JSON_GRAPH_JSON_REVERSIBILITY`
3. `E7_INTERPRETER_BOUNDARY`
4. `E3_CONSTRAINT_CLOSURE`
5. `E4_MINIMAL_DISTINGUISHING_SUBGRAPH_MAGIC_KEY`

Only then expand the search externally.
