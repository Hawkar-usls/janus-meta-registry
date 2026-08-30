# TECHNICAL BLAME-SHIFTING / RHETORIC FINGERPRINT — OUTREACH ANNEX v1.2

**Recipients:** FBI, ODNI/FMIC, State CDP + R/CFIMI

**Do not attach to:** Meta Threads integrity complaint. CISA remains HOLD pending a technical foreign network trigger.

## Core finding

An open-source TOPA/Spider pass across Habr and Reddit finds a **recurring multi-year rhetoric family** that shifts responsibility for Russian users losing access to Western platforms away from Russian network/policy intervention and toward the foreign platform, Western moderation, sanctions, platform exit, or allegedly degraded foreign infrastructure.

This is a discourse finding, not an account-attribution finding. No specific Reddit or Habr account is identified here as a bot, state asset, or coordinated operator without additional evidence.

## Recurrent rhetoric families

### RF1 — Reciprocal censorship

Canonical form:

> Russia is blocking or may block YouTube because YouTube/the West blocked Russian media first.

Public Reddit examples in March 2022 explicitly framed a possible future Russian YouTube block as a consequence of YouTube restricting Russian media and described YouTube as suppressing content outside a Western agenda.

Examples:
- https://www.reddit.com/r/AskARussian/comments/ticzcz
- https://www.reddit.com/r/AskARussian/comments/tioclc

This frame converts domestic censorship from an originating policy choice into retaliation.

### RF2 — Google Global Cache / infrastructure exculpation

Canonical form:

> YouTube is slow because Google left Russia or stopped maintaining Google Global Cache; Russia/Roskomnadzor is not the cause.

The GGC explanation was publicly advanced by Rostelecom/Russian officials in 2024. The same explanation circulated in public discussions, while technical counterevidence pointed toward deliberate throttling/filtering.

Examples/context:
- https://habr.com/ru/news/828418/
- https://habr.com/ru/news/834188/
- https://www.reddit.com/r/technology/comments/1edjz4d

Important control: GGC degradation was technically plausible and real capacity/maintenance concerns existed before the 2024 slowdown. Therefore GGC references are not false by definition. The concern is the repeated use of the explanation despite observations that did not fit a simple cache-failure model.

### RF3 — Platform self-blocking / Western agenda

Canonical form:

> YouTube/Google itself blocks Russia or Russian viewpoints, so later Russian restrictions are secondary, justified, or caused by the platform.

This appears in 2022 Reddit discussions and overlaps with real Western-platform actions against Russian state media. Those real moderation/sanctions actions are preserved as negative controls; they do not establish the cause of later network-level inaccessibility inside Russia.

### RF4 — Two-sided iron curtain

Canonical form:

> Western/American sites also block Russian visitors, so Russian digital isolation is fundamentally bilateral rather than driven primarily by Russian state controls.

A 2025 AskARussian thread documents real cases of U.S./Western sites blocking Russian visitors and mixed debate about which side causes which restriction:
- https://www.reddit.com/r/AskARussian/comments/1l7443t/why_do_american_sites_block_russian_visitors/

This rhetoric can contain a true factual core. The manipulation risk arises when genuine Western geoblocking is used to erase independently documented Russian blocking/throttling.

### RF5 — 'The company left by itself'

Canonical form:

> The platform left Russia or stopped operating voluntarily, therefore loss of service is the company's own choice rather than a consequence of Russian legal/policy pressure.

Public discussion in 2022 already identified the inverse possibility: a platform can be pressured until exit and authorities can then describe the resulting isolation as voluntary foreign withdrawal.

Example:
- https://www.reddit.com/r/UkraineRussiaReport/comments/w43x6k

## Reddit technical rebuttal controls

The Reddit corpus is not one-directional. It contains strong technical rebuttals and is therefore useful as a control rather than simply a collection of pro-Russian claims.

- AskARussian, August 2024: users identify RKN-controlled DPI as a throttling layer and note provider heterogeneity: https://www.reddit.com/r/AskARussian/comments/1eqn8gy
- AmneziaVPN, July 2024: public technical discussion identifies YouTube throttling and argues overnight degradation does not fit ordinary cache aging: https://www.reddit.com/r/AmneziaVPN/comments/1e1m61f
- Minecraft, August 2024: a widely viewed thread corrects a mistaken assumption that Google itself reduced bandwidth and instead points to Russian blocking: https://www.reddit.com/r/Minecraft/comments/1enytol
- Reddit itself imposed broad restrictions on .ru links in March 2022, including collateral effects on anti-war sources: https://www.reddit.com/r/ModSupport/comments/t66l5f/reddit_blocked_all_domains_under_russian_ccTLD_ru/

The last example is a crucial falsifier against over-attribution: some claims that Western platforms restricted Russian content are factually true.

## Relation to the researcher's longitudinal account-cluster observation

The submitting researcher reports manually reviewing multiple long-lived accounts and finding repeated variants of the same technical/exculpatory rhetoric across their post histories.

The new open-source Reddit/Habr pass independently confirms that **the rhetoric family itself recurs across platforms and years**. This increases the value of the researcher's cluster observation as a collection lead, but it does not independently establish that the accounts share operators or Russian state direction.

The strongest next attribution bridges would be:

- distinctive technical phrases repeated across multiple old accounts;
- chronology showing the phrase before a later access restriction;
- exact wording or link reuse across platforms;
- synchronized posting windows;
- shared external media/URLs;
- known contractor/operator overlap;
- platform or law-enforcement telemetry linking account operation.

## Analytic model

`REAL_OR_ALLEGED_WESTERN_PLATFORM_ACTION`

→ `RUSSIAN_POLICY_OR_NETWORK_PRESSURE`

→ `EXPLANATION EMPHASIZES WESTERN PLATFORM / GOOGLE / INFRASTRUCTURE FAULT`

→ `USERS REPEAT RECIPROCAL OR TECHNICAL EXCULPATION FRAME`

→ `RESPONSIBILITY FOR ACCESS LOSS SHIFTS AWAY FROM DOMESTIC CONTROL LAYER`

This is best described as **technical attribution manipulation / blame shifting** when supported by a mismatch between the public explanation and independent network evidence.

## Claim ceiling

**Confirmed:** the same broad blame-shifting rhetoric families recur on Habr and Reddit across multiple years.

**Confirmed:** the 2024 GGC explanation was publicly advanced while substantial independent evidence pointed toward deliberate Russian throttling.

**Confirmed:** Western platforms also imposed real restrictions on Russian state media, .ru links, monetization and some Russian users/content; these are negative controls.

**Not established:** that specific Reddit/Habr accounts are bots.

**Not established:** a common operator across those accounts or platforms.

**Not established:** Russian state direction of the specific accounts.

**Rejected:** the claim that every assertion blaming Google/the West is false by definition.

## Recipient relevance

**FBI:** useful as an account-attribution / influence-operation lead if repeated personas can later be linked technically to known operators.

**ODNI/FMIC:** useful as a longitudinal strategic-deception and causal-attribution pattern.

**State / R/CFIMI:** useful as a foreign-information-manipulation pattern in which access restrictions and the explanation for those restrictions can be manipulated simultaneously.
