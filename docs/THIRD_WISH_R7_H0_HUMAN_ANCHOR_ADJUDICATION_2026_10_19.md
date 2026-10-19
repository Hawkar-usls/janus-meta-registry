# Third Wish R7-H0 — human anchor adjudication before any new AI judge

Status: **WAITING FOR INDEPENDENT HUMANS**. This is preparatory material on a Draft branch, not a performed human review or an authorized R7 AI experiment.

## Why

The original R6 Gemma 3 12B run produced **43/44** structurally valid scores but passed only **2/6** prespecified author-labeled controls, failing the mandatory gate. High raw agreement against Llama 3B masked predominance of zero labels (Cohen kappa for novelty, tests, and initiative: 0). The actual R6 file and its failed status are preserved unchanged.

## Who must review

1. **Two distinct independent humans**, preferably experienced in experimental methodology. The project owner and this assistant do not count automatically as independent outsiders.
2. Each person receives only `JANUS-GENESIS-THIRD-WISH-R7-H0-HUMAN-ANCHOR-PACKET-2026-10-19-v1.0.json` plus a separate copy of `JANUS-GENESIS-THIRD-WISH-R7-H0-HUMAN-REVIEW-FORM-TEMPLATE-2026-10-19-v1.0.json`. Provide the packet directly; do not direct the reviewer to browse the R6 protocol.
3. The English notes remain unmodified; choose raters comfortable with English. No model may write or recommend the human ratings.
4. Reviewers must not view the R6 gold labels, Llama/Gemma scores, each other's forms, or experimental groups before locking their own ratings. The R6 protocol is public, so this instruction and each reviewer's attestation cannot independently *prove* there was no contamination.
5. Reviewers score all six opaque case IDs and explain their scores with exact supporting quotes. They independently fill all four 0–2 criteria, the proposed-action boolean, evidence quote, and brief reason. The schema rejects omitted cases, blank placeholders and fabricated citations.
6. A trusted coordinator verifies that the two pseudonyms correspond to **two genuine distinct humans** outside this published evidence. Any dimension disagreement is routed to a **third independent human adjudicator** whose judgment is separately recorded; never silently average or overwrite the two original forms.

## Freeze, then compare

The reviewer packet is SHA256-locked in the validator. Completed forms must be preserved with timestamp, attestation, and file digest before *any* gold comparison. They should be received through an agreed confidential channel; do not publish reviewer identities or raw personally identifying data in this public Draft PR.

The offline standard-library-only checker reports independent inter-human exact agreement, Cohen kappa and cases requiring adjudication. It does **not** import R6 gold, model scores or experiment group keys:

```bash
python -m tools.third_wish_r7_h0_human_review --review /path/to/reviewer-1.json --review /path/to/reviewer-2.json
```

The command only evaluates submitted files and prints a provisional summary. Self-attested human status is not independent identity verification.

After both original ratings and any separate adjudication have been locked, compare them to R6's immutable author-selected gold **as a diagnostic**, recording differences and their reasons. Neither R6 gold nor R6 model output is rewritten. If gold anchors are disputed, register a distinct successor consensus rubric; use new holdouts before any R7 model evaluation.

## Explicit stop conditions

- `HUMAN_RATERS_COMPLETED = false`
- `THIRD_HUMAN_ADJUDICATION_COMPLETED = false`
- `R6_FAILURE_RETAINED = true`
- `R7_AI_MODEL_PREREGISTERED = false`
- `R7_AI_MODEL_RUN = false`
- `EXPERIMENT_ARM_MAPPING_OPENED = false`
- `PRODUCTION_AUTHORITY_CHANGED = false`

Do not present this preparation as evidence that any AI achieved stronger creative research reasoning.
