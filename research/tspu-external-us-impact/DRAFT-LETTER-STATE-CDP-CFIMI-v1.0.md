# DRAFT — U.S. Department of State / CDP + CFIMI

**Status:** NOT SENT

**Suggested subject:** Partner-Resilience Warning: Network Isolation Infrastructure as an Amplifier of Foreign Information Manipulation

To the U.S. Department of State — Bureau of Cyberspace and Digital Policy and Counter Foreign Information Manipulation and Interference personnel,

I am submitting an unclassified early-warning concern about the intersection of two issues the Department already treats as serious: authoritarian control of Internet access and foreign state information manipulation.

The core concern is that a future foreign TSPU-like or centrally controlled DPI environment could do more than censor individual websites. In a severe crisis mode, such infrastructure can potentially deny ordinary public Internet, preserve approved local services through an allowlist, selectively degrade foreign platforms, and thereby change the **relative information environment** before any propaganda message is evaluated on its merits.

I am **not** alleging that Russia currently operates a synchronized global TSPU system outside Russia. Public evidence does not support that claim. I am proposing a partner-resilience and early-warning problem that can be monitored with falsifiable indicators.

## Historical mechanism

Russia and Russian-backed forces have repeatedly treated control of information distribution as strategically important during conflict.

In Crimea and parts of Donetsk and Luhansk in 2014, Ukrainian/local broadcast and cable distribution was seized or pressured, competing sources were removed, and Russian/aligned sources were inserted. This was not simply the production of propaganda; it was a change in what information the population could physically receive.

After the 2022 invasion, the mechanism expanded into Internet infrastructure. Cloudflare measured occupied Ukrainian networks being rerouted onto Russian upstreams. The functional principle remained similar: control the distribution layer, then the available information environment changes with it.

## Modern Russian capability

Independent technical research has established that TSPU is widely deployed, in-path and centrally controlled inside Russia. Censored Planet documented its architecture across privately owned ISPs. FOCI 2026 showed large-scale SNI-dependent QUIC censorship, highlighting policy flexibility. Human Rights Watch has documented escalating Russian censorship and isolation capability.

Russia has also demonstrated regional/mobile shutdowns and, by 2025-2026, a **deny-except-allowlist** model in which selected approved services remain reachable during broader mobile Internet restrictions.

For foreign-policy purposes, this creates an important asymmetry: a population can lose access to U.S. media, U.S. government information, international platforms, independent journalism and ordinary external communications while selected domestic services remain available. The U.S. services themselves may remain fully operational.

## Foreign technology proliferation

Russian SORM and surveillance technologies have been exported to multiple countries. Recorded Future / Insikt Group identified at least eight Russian SORM vendors exporting into Central Asia and Latin America and at least fifteen likely telecom customers, with broader export activity in other regions.

This is **not** evidence that those countries contain Russian-operated TSPU nodes. SORM and TSPU are different systems, and host governments can use surveillance technology independently. However, the proliferation matters for partner-country resilience because it embeds opaque surveillance/control technology into telecom infrastructure and may create vendor-access risk. Recorded Future assesses that Russian-component foreign systems may present some risk of Russian access while noting that the degree of Moscow's actual access is unclear.

## Why this matters to U.S. diplomacy and information integrity

The Department's Framework to Counter Foreign State Information Manipulation recognizes information manipulation as a transnational security threat and emphasizes common operating pictures, partner capacity, resilient information ecosystems, independent media and multilateral cooperation.

The additional risk I am asking the Department to consider is **technical information isolation as an amplifier**.

A useful functional sequence is:

`external/open sources become less reachable`

→ `approved/local sources remain available`

→ `ordinary cross-border communication becomes harder`

→ `the relative exposure share of state-aligned narratives rises`

→ `external observers receive slower and less representative information from the affected society`.

This mechanism does not require every citizen to believe propaganda, and available research shows media effects are heterogeneous. But removing or degrading competing sources changes the environment in which persuasion, crisis communication and public diplomacy operate.

## Strategic U.S. consequences

A successful technical information-isolation event abroad could:

- reduce direct U.S. communication with foreign publics;
- isolate local journalists, civil society and independent media from international platforms;
- disrupt U.S. businesses, diplomats and partners that depend on national public telecom networks;
- increase the relative reach of state-approved information sources;
- make local restrictions appear to foreign users as failures of U.S. services;
- and create an observability gap in which U.S.-side service health remains normal while foreign access deteriorates.

## Proposed partner-resilience indicators

Rather than infer foreign coordination from similar rhetoric, I suggest monitoring a technical composite:

- simultaneous foreign-vantage testing of U.S./open sources and local/state-approved substitutes;
- separate mobile and fixed-network measurements;
- DNS/TLS/QUIC/basic reachability and route/path observations;
- provider-side U.S. service health as a negative control;
- identification of Russian-origin surveillance/control vendors without equating vendor origin with state command;
- independent replication across networks;
- and evidence of common external control before attributing synchronization to Russia.

The strongest claim supported by the open evidence is therefore not "Russia has built a global TSPU." It is:

**Russia has repeatedly integrated information-distribution control with influence operations in conflict, possesses a sophisticated centrally controlled domestic network-isolation capability, exports adjacent surveillance technologies, and has a documented long-running foreign influence apparatus. The possibility that these layers could converge abroad is sufficiently concrete to justify partner-resilience monitoring, while the critical external-control bridge remains unproven.**

I have assembled an open-source research package with confidence levels, negative controls, corrections where evidence weakened our own hypothesis, and clear attribution thresholds. I would be grateful if it could be routed to the appropriate CDP and foreign information manipulation / partner-resilience personnel for review.

Respectfully,

[Name]
Independent researcher, Ukraine
[Contact information]

## Public evidence anchors

- State Department Framework to Counter Foreign State Information Manipulation: https://2021-2025.state.gov/the-framework-to-counter-foreign-state-information-manipulation/
- U.S. International Cyberspace & Digital Policy Strategy: https://2021-2025.state.gov/united-states-international-cyberspace-and-digital-policy-strategy/
- Censored Planet, TSPU: https://censoredplanet.org/tspu
- FOCI 2026, QUIC/SNI censorship: https://www.petsymposium.org/foci/2026/foci-2026-0010.php
- Human Rights Watch, Russian censorship/TSPU isolation: https://www.hrw.org/report/2025/07/30/disrupted-throttled-and-blocked/state-censorship-control-and-increasing-isolation
- Cloudflare, occupied Ukrainian network rerouting: https://blog.cloudflare.com/one-year-of-war-in-ukraine/
- Recorded Future / Insikt Group, Russian SORM exports/access risk: https://www.recordedfuture.com/research/tracking-deployment-russian-surveillance-technologies-central-asia-latin-america

**Routing note:** This draft is intended for State Department cyberspace/digital-policy and foreign-information-manipulation channels. It is not yet approved for sending.
