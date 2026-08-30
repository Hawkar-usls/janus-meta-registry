# DRAFT — FBI / Foreign Influence Task Force

**Status:** NOT SENT

**Suggested subject:** Early-Warning Submission: Russian TSPU/SORM, Public-Network Denial, and Foreign Malign Influence Risk

To the Federal Bureau of Investigation / Foreign Influence Task Force,

I am submitting an unclassified, evidence-based early-warning concern regarding the possible future convergence of three capabilities that are already separately documented: Russia's repeated control of information-distribution infrastructure during conflicts; Russia's centrally managed TSPU public-network control architecture; and Russian foreign malign influence operations targeting U.S. and foreign audiences.

I am **not** alleging that Russia is currently operating a synchronized global TSPU network outside its borders. I have not found public evidence sufficient to support that claim. My concern is narrower and falsifiable: if Russian-controlled or remotely accessible network-control infrastructure were ever established across multiple foreign telecom environments, it could create a combined communications-denial, information-isolation, and influence surface that would be materially more serious than conventional propaganda alone.

## Why I believe this merits counterintelligence review

Public evidence establishes a recurring historical mechanism. In conflicts involving Russia or Russian-backed forces, information distribution has repeatedly been treated as a strategic target: broadcast infrastructure was neutralized in Chechnya; Ukrainian television and radio distribution was seized and replaced with Russian/aligned sources in Crimea and parts of Donetsk and Luhansk in 2014; and, after the 2022 invasion, occupied Ukrainian Internet networks were rerouted through Russian upstreams, causing users to inherit Russian network-control and censorship conditions.

Separately, modern TSPU research shows that Russia now has an in-path, centrally controlled system deployed across privately owned ISPs that can impose censorship policy at scale. Censored Planet characterized TSPU as pervasive, in-path and centrally controlled. FOCI 2026 research documented large-scale SNI-dependent QUIC censorship, demonstrating policy flexibility. Human Rights Watch has documented Russia's escalating use of network manipulation and regional shutdown/isolation mechanisms.

Russia has also moved beyond simple blackout behavior. By 2025-2026, Russian authorities publicly operated a mobile **deny-except-allowlist** model in which ordinary mobile Internet can be restricted while selected approved services remain available. Operationally, that means a controller does not need to make the entire network visibly fail; it can preserve selected domestic or state-approved services while external communications disappear.

At the same time, Russian SORM/surveillance technology has proliferated abroad. Recorded Future / Insikt Group identified at least eight Russian SORM providers exporting into Central Asia and Latin America and at least fifteen likely telecom customers. Its assessment also identifies a risk that Russian-component foreign systems may retain vendor or Russian access, including concerns about backdoors and manufacturer access, while explicitly noting that the degree of Moscow's access is unclear. I therefore treat **foreign remote control as an unresolved counterintelligence question, not an established fact**.

The FBI already identifies foreign malign influence as a persistent national-security threat and leads the Foreign Influence Task Force. The Bureau and interagency partners have publicly documented and disrupted Russian government-directed influence infrastructure targeting U.S. and foreign audiences. The additional risk I am asking you to consider is whether technical control over foreign communications distribution could someday become an enabling layer for those influence operations.

## JUXTAPOSE — why I mention it only to the FBI

I previously submitted to DARPA an independent research package called **JUXTAPOSE: Exact-Backed Adaptive Search for Resilient Communications in DDIL Environments**. It is a defensive, transport-agnostic communications-resilience architecture. Its core rule is: **"learn where to look; never learn what is true."** Learning can prioritize which authorized path to test, but only fresh end-to-end measurement is allowed to establish current connectivity; failure cases and UNKNOWN states are retained rather than hidden.

I mention JUXTAPOSE here only because it helped me recognize the inverse threat model. If a defensive system must reason about reachability, path diversity, stale evidence and shared failure domains to survive degraded communications, then a centrally controlled network-policy layer can potentially create those failure domains deliberately for users who depend on the affected public network. This is not a claim that JUXTAPOSE proves anything about Russia, nor is it an offensive technique. It is simply the analytical lens that made the communications-denial dimension of TSPU clearer to me.

## The specific warning signature I believe is worth collecting

I would not attribute an event to Russia based on propaganda timing, Russian equipment, or a network outage alone. A meaningful warning would require a composite pattern such as:

- foreign-vantage loss or severe degradation of ordinary U.S./open Internet services;
- selected local or state-approved services remaining available;
- a reproducible DPI/TSPU-like protocol signature or foreign Russian-origin control-stack evidence;
- path or device localization rather than temporal coincidence;
- healthy U.S.-side provider controls;
- replication on additional networks or countries;
- and, before Russian attribution, evidence of shared Russian vendor/state control, command, remote administration, or infrastructure linkage.

The central unresolved question is therefore not whether Russia possesses censorship and influence capability; those are already established. It is whether foreign telecom deployments create a covert or latent **external control plane** that could be activated in a crisis.

## Why the U.S. nexus matters

If such a capability existed, U.S. domestic services could remain fully operational while foreign populations, U.S. personnel abroad, companies, journalists, civil-society partners, and public-network-dependent logistics lose access to those services. A deny/allowlist regime could simultaneously reduce communications with the United States and increase the relative dominance of selected local information sources. Any hidden Russian access to foreign telecom-control infrastructure would also raise a counterintelligence and supply-chain concern independent of propaganda.

I have assembled an open-source evidence package with confidence labels, negative controls, historical cases, technical fingerprints, corrections where our own hypothesis was weakened, and explicit falsifiers. I would be grateful if this submission could be routed to the appropriate Counterintelligence / Foreign Influence / Cyber personnel for review. I am not requesting that the FBI accept my hypothesis; I am asking whether the missing control-plane question is already understood or merits collection.

Respectfully,

[Name]
Independent researcher, Ukraine
[Contact information]

## Public evidence anchors

- FBI, Foreign Influence Task Force / foreign malign influence: https://www.fbi.gov/news/speeches-and-testimony/oversight-of-the-federal-bureau-of-investigation-071223
- Censored Planet, TSPU: https://censoredplanet.org/tspu
- FOCI 2026, Russian QUIC/SNI censorship: https://www.petsymposium.org/foci/2026/foci-2026-0010.php
- Human Rights Watch, Russian censorship/TSPU control: https://www.hrw.org/report/2025/07/30/disrupted-throttled-and-blocked/state-censorship-control-and-increasing-isolation
- Cloudflare, rerouting of occupied Ukrainian networks: https://blog.cloudflare.com/one-year-of-war-in-ukraine/
- Recorded Future / Insikt Group, Russian surveillance exports and access risk: https://www.recordedfuture.com/research/tracking-deployment-russian-surveillance-technologies-central-asia-latin-america

**Routing note:** FBI public submissions can be made through https://tips.fbi.gov/ or an FBI field/international office. This draft is not yet approved for sending.
