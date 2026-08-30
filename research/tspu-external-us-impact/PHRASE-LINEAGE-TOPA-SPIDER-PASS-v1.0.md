# TOPA + Spider Phrase-Lineage Pass v1.0

**Status:** COMPLETE FOR OPEN-WEB R0 / ACCOUNT-LEVEL OPERATOR ATTRIBUTION OPEN

## Objective

Search for rare or technically specific repeated formulations and argument-order reuse around Google/YouTube access in Russia, especially:

- Google Global Cache / GGC;
- "Google left Russia";
- "Google stopped maintaining / upgrading servers";
- "YouTube/West blocked Russian media first";
- "Western agenda";
- "some services are blocked by Russia, others by Western site owners".

The pass explicitly separates:

1. official-source wording;
2. news syndication/quotation;
3. independent user restatement;
4. organic disagreement/counter-rhetoric;
5. real technical and policy negative controls.

## Main finding

The strongest repeatable signal is not one identical sentence across unrelated accounts. It is a persistent causal architecture:

`WESTERN ACTION OR COMPANY EXIT`

→ `FOREIGN PLATFORM / INFRASTRUCTURE BECOMES THE PROXIMATE CAUSE`

→ `RUSSIAN RESTRICTION OR POLICY ROLE IS MINIMIZED, JUSTIFIED, OR MADE AMBIGUOUS`.

This appears in several families:

- reciprocal censorship: YouTube blocked Russian state/media channels first;
- platform self-blocking / Western-agenda framing;
- GGC infrastructure exculpation: Google left, stopped support, therefore degradation is Google's fault;
- two-sided isolation: Russian blocking exists, but Western sites also block Russian users;
- voluntary-exit framing: the foreign company caused the service loss by leaving.

## Reddit result

Reddit contains independent examples across multiple years rather than one single repeated phrase:

- March 2022 AskARussian discussions explain anticipated Russian YouTube blocking as a response to YouTube's blocking of Russian media and invoke a "Western agenda" frame.
- March 2022 another AskARussian discussion attributes difficulty finding Putin's speech to YouTube blocking Russian media and search engines down-ranking it.
- June 2025 AskARussian discussion describes a mixed environment in which Russian authorities block some services while foreign site owners block Russian IPs for sanctions/security/political/commercial reasons.
- August 2026 discussion of Wikipedia access again invokes European blocking of Russian websites as a reciprocal comparison.

These examples confirm recurrence of the *causal templates*. They do not establish that the same operator is behind the accounts.

## GGC phrase lineage

A more technically specific lineage is visible:

1. **December 2023:** legitimate industry reporting documents aging/overloaded GGC nodes and Google's proposal for direct peering. This is a required negative control: GGC degradation is technically real and possible.
2. **July 12, 2024:** Rostelecom publicly attributes possible YouTube degradation to technical problems and expansion limits around GGC; Roskomnadzor adopts the explanation without adding an alternative.
3. **July 26, 2024:** Roskomnadzor explicitly connects declining YouTube quality to Google leaving Russia and stopping cache-infrastructure support, while in the same statement criticizing YouTube for blocking Russian channels and reserving retaliatory measures.
4. **User layer:** DFRLab later documents the same server-depreciation explanation being repeated on YouTube Community/forums, alongside users rejecting it and pointing toward throttling.
5. **Later user discussion:** Reddit continues to reproduce elements of the same technical frame, including the non-upgrade of GGC and Google's reduced Russian presence, while other users challenge the inference that YouTube itself "left" Russia.

The important distinction is that exact repetition of Rostelecom/RKN wording by news sites is normal quotation. The higher-value signal is independent near-restatement preserving the same rare technical tokens **and the same causal order**.

## Counterevidence retained

This pass does not assume that every claim blaming Google is false.

- GGC capacity/maintenance problems are technically plausible and were discussed before the July 2024 slowdown.
- Western sites genuinely block some Russian IP ranges for sanctions, security, commercial or political reasons.
- YouTube and other Western platforms genuinely restricted Russian state-media channels after the 2022 invasion.
- Organic users can independently arrive at inaccurate technical explanations without coordination.

On the other hand, Habr technical analysis found behavior consistent with DPI classification: access improved when the censor could not classify the relevant hostname while the destination IP remained the same. DFRLab reconstructed the 2024 throttling sequence and the simultaneous spread/dispute of the GGC explanation.

## Current verdict

**CONFIRMED:** recurrent rhetorical/causal families across Habr, Reddit, official statements and user-generated discussions.

**CONFIRMED:** a technically specific GGC template migrated from industry/official discourse into user-level discussion.

**NOT ESTABLISHED:** exact-copy network among independent long-lived accounts.

**NOT ESTABLISHED:** common operator, bot farm, SMM contractor or Russian-state direction for specific Reddit/Habr accounts.

## Next gate

The next pass should be account-level but privacy-preserving: do not politically profile ordinary users or publish a target list. Compare only public content for:

- rare technical n-grams;
- same argument ordering;
- uncommon punctuation/translation artifacts;
- same outbound URLs and media;
- same source-selection sequence;
- burst timing;
- phrase appearance before versus after official/public releases;
- cross-platform reuse.

A phrase match becomes materially interesting only when it is **rare + independently posted + temporally informative + not explained by quoting the same source**.

The account/operator attribution gate remains closed until there is independent infrastructure/platform evidence.
