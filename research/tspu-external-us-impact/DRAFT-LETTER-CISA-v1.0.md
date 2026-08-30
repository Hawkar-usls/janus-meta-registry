# DRAFT — CISA

**Status:** NOT SENT

**Suggested subject:** Early-Warning Network Resilience Concern: Foreign TSPU-Like Denial / Allowlist Capability and U.S. Service Reachability Abroad

To the Cybersecurity and Infrastructure Security Agency,

I am submitting an unclassified network-resilience concern focused on a class of public-network control capability that I believe deserves foreign-vantage monitoring: centralized DPI / routing / policy infrastructure capable of selectively denying ordinary Internet access, preserving allowlisted services, and controlling which external destinations remain reachable.

I am **not** reporting a confirmed ongoing cyber incident and I am **not** alleging that Russia currently controls a synchronized foreign TSPU network. The purpose of this submission is to identify a specific, testable resilience risk before an incident exists.

## Technical basis

Independent measurement research has established that Russia's TSPU system is widely deployed, in-path and centrally controlled across privately owned ISPs. Censored Planet documented the architecture and its ability to roll out censorship measures centrally. FOCI 2026 documented large-scale SNI-dependent QUIC censorship, showing that the system can adapt policy to modern protocols.

Human Rights Watch has documented the Russian government's ability to manipulate, filter and reroute traffic through TSPU-related infrastructure and to carry out regional Internet isolation/shutdown behavior. Russian authorities have also publicly operated a mobile **deny-except-allowlist** model in which broad mobile Internet access is restricted while selected approved services remain available.

This is operationally different from a simple outage. A user inside the affected network may lose U.S. cloud, communications, media, software, developer or social services while selected domestic services remain healthy. U.S.-side provider dashboards can remain green throughout the event.

There is also a historical routing precedent. Cloudflare measured more than twenty occupied Ukrainian networks whose upstream connectivity shifted onto Russian networks during the war. That demonstrates that information-access conditions can change when the path itself is moved into a different control jurisdiction.

Separately, Russian SORM and surveillance technologies have been exported into multiple foreign telecom environments. This is not equivalent to TSPU and does not establish Russian command, but it creates a foreign telecom-dependency surface that merits technical mapping. Recorded Future / Insikt Group assesses that Russian-component foreign SORM systems may present vendor/Russian access risk, while stating that the degree of actual Moscow access remains unclear.

## Resilience problem

The failure mode I believe deserves monitoring is:

`ordinary public Internet denied or selectively degraded`

while

`approved/local services remain reachable`

and possibly

`external U.S./open services fail only from affected foreign networks`.

For public-safety, diplomatic, logistics, commercial, humanitarian, civil-society, and military-adjacent workflows that depend on national mobile or ISP infrastructure, this can create immediate communications denial even when the underlying U.S. service is healthy.

I do **not** claim that this would automatically disable hardened military communications. Dedicated tactical radio, protected satellite links, dedicated military networks, and other paths that do not traverse the affected public network must be treated separately.

## Proposed defensive collection signature

I believe the following composite should be treated as more meaningful than any single censorship report:

- foreign-vantage reachability loss to a stable basket of U.S./open services;
- simultaneous testing of approved/local/state-aligned services;
- mobile and fixed-network controls measured separately;
- DNS, TLS, QUIC and basic reachability measured together;
- AS-path / traceroute / route-origin observations and RPKI state;
- provider-side service health as a negative control;
- matched alternate-network or alternate-path controls;
- repeated measurements from independent vantage points;
- device/vendor/control-plane evidence before attributing the event to any foreign state.

A particularly important warning pattern would be broad external-service failure combined with continued access to an explicit local allowlist. That would distinguish a policy event from many ordinary infrastructure failures.

## Why this is relevant to CISA

CISA's own emergency communications guidance emphasizes resilient and secure communications, route diversity, redundancy, and alternative paths. The concern described here is fundamentally a **communications resilience and dependency problem**, not a request for CISA to assess propaganda content.

If a foreign government or external actor could centrally constrain the public-network paths used by U.S. personnel, businesses, partners, or foreign critical-infrastructure counterparts, the United States could experience operational consequences abroad without an outage inside U.S. infrastructure.

I have assembled a supporting open-source package containing historical controls, TSPU technical literature, foreign SORM/DPI deployment evidence, route-risk targets, negative controls, and explicit attribution thresholds. I would be grateful if this could be routed to the appropriate communications resilience / cyber threat / international partner team for technical review.

Respectfully,

[Name]
Independent researcher, Ukraine
[Contact information]

## Public evidence anchors

- CISA National Emergency Communications Plan: https://www.cisa.gov/national-emergency-communications-plan
- CISA Russia Threat Overview: https://www.cisa.gov/topics/cyber-threats-and-advisories/advanced-persistent-threats/russia
- Censored Planet, TSPU: https://censoredplanet.org/tspu
- FOCI 2026, Russian QUIC/SNI censorship: https://www.petsymposium.org/foci/2026/foci-2026-0010.php
- Human Rights Watch, TSPU / isolation / censorship: https://www.hrw.org/report/2025/07/30/disrupted-throttled-and-blocked/state-censorship-control-and-increasing-isolation
- Cloudflare, occupied Ukrainian network rerouting: https://blog.cloudflare.com/one-year-of-war-in-ukraine/
- Recorded Future, Russian SORM exports/access risk: https://www.recordedfuture.com/research/tracking-deployment-russian-surveillance-technologies-central-asia-latin-america

**Routing note:** CISA accepts cyber/anomalous activity reporting through https://www.cisa.gov/report and CISA Central. This draft is an early-warning/research submission, not a claim of a current incident, and is not yet approved for sending.
