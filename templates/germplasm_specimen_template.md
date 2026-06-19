# Germplasm Specimen Card: [Common Name / Cultivar]

> Public-safe research record. Observation does not establish cultivar identity,
> genetic modification, disease resistance, or permission to move plant material.

## 1. Meta And Status

- **System ID:** `REGM-MUSA-YYYYMMDD-XXXX`
- **Record version:** `v0.1`
- **Status:** `UNVERIFIED_HYPOTHESIS`
- **TR4 resistance:** `UNKNOWN`
- **GM status:** `UNVERIFIED`
- **Last verified commit:** `[commit hash]`
- **Evidence cutoff:** `[UTC timestamp]`

## 2. Origin And Chain Of Custody

- **Declared name:** `[seller or local name]`
- **Declared originator:** `originator_lead: unverified`
- **Public source region:** `[country/region only]`
- **Exact coordinates:** `PRIVATE_NOT_IN_PUBLIC_REPOSITORY`
- **Acquisition date:** `[YYYY-MM-DD or UNKNOWN]`
- **Propagation at acquisition:** `[seed/sucker/tissue culture/unknown]`
- **Custody event log:** `[link to sanitized passage log]`
- **Phytosanitary certificate:** `[NONE/UNKNOWN/sanitized ID]`
- **MTA status:** `RESTRICTED_PENDING_CLEARANCE`

Do not publish a home address, exact private coordinates, seller personal data,
or unsanitized phytosanitary documents.

## 3. Botanical And Phenotypic Profile

- **Taxonomy:** `Musa spp. - identification pending`
- **Working genome-group hypothesis:** `[e.g. AAA/Cavendish candidate; unverified]`
- **Ploidy:** `UNKNOWN`
- **Current propagation method:** `[method]`
- **Pseudostem height:** `[m, date, method]`
- **Leaf morphology:** `[description and image IDs]`
- **Inflorescence:** `[description or NOT_OBSERVED]`
- **Fruit:** `[description or NOT_OBSERVED]`
- **Growth conditions:** `[light, temperature, substrate, irrigation]`

## 4. Passage And Living-State History

Every vegetative generation or in-vitro passage receives a stable child ID.

| Date UTC | Parent ID | Child ID | Passage | Method | Operator | Observable change | Evidence |
|---|---|---|---:|---|---|---|---|
| | | | | | | | |

- Never overwrite an earlier state.
- Record contamination, stress, flowering, fruiting, treatment, and phenotype drift.
- A passage event is not evidence of stable inheritance until replicated.

## 5. Genomic And Epigenomic Identification

- **Ploidy verification:** `PENDING`
- **Cultivar-oriented fingerprint:** `NOT_STARTED`
- **Reference accessions:** `[authenticated comparison IDs]`
- **Candidate analyses:**
  - [ ] Flow cytometry for ploidy.
  - [ ] Laboratory-selected SSR panel and/or SNP/DArT profiling.
  - [ ] Whole-genome comparison only when justified and properly controlled.
  - [ ] Methylation or other epigenomic assay with passage-matched controls.

Primer sequences must come from a validated laboratory protocol and named
reference. Ordinary DNA barcoding alone is not sufficient to distinguish close
Cavendish clones.

## 6. Rhizosphere And Endophyte Layer

- **Sampling status:** `NOT_STARTED`
- **Compartment:** `[bulk soil/rhizosphere/rhizoplane/root endosphere]`
- **Substrate batch:** `[sanitized batch ID]`
- **Sampling date and passage:** `[UTC, sample ID]`
- **Negative controls:** `[field blank/extraction blank/library blank]`
- **Positive or mock control:** `[ID where appropriate]`
- **Assay:** `[16S/ITS/shotgun metagenomics/culture-dependent]`
- **Environmental covariates:** `[temperature, moisture, pH, treatment]`
- **Derived profile:** `[public-safe link]`
- **Raw sequence location:** `[external controlled archive accession, not Git]`

Microbiome association does not establish causation. Host genotype, substrate,
passage, environment, batch effects, and contamination must be controlled.

## 7. Phytopathology And TR4 Evaluation

**STRICT PROHIBITION: no domestic or unlicensed Foc TR4 acquisition, culture,
transport, or inoculation.**

- **Authorised facility:** `NONE_ASSIGNED`
- **National phytosanitary approval:** `NOT_OBTAINED`
- **Containment protocol:** `NOT_APPROVED`
- **In-vitro screen:** `NOT_STARTED`
- **Contained whole-plant challenge:** `NOT_STARTED`
- **Susceptible control:** `[authenticated accession]`
- **Resistant/tolerant control:** `[authenticated accession]`
- **Predeclared endpoints:** `[disease index, vascular symptoms, survival, pathogen load]`
- **Replication/blinding:** `[design]`

Reference: [FAO TR4 prevention, preparedness and response guidelines](https://doi.org/10.4060/cc4865en).

## 8. Upgrade Gate

Upgrade to `TR4_RESISTANT_GERMPLASM_CANDIDATE` requires:

1. Traceable sample and laboratory accession IDs.
2. Authenticated identity or clearly bounded unresolved identity.
3. Authorised replicated challenge with predefined endpoints and controls.
4. Reproducible resistance or tolerance estimate across independent propagules.
5. Independent review or replication.

Genetic distinctness is informative but is not itself required or sufficient for
phenotypic resistance. A genebank accession is desirable for preservation, but
is not a substitute for the evidence above.

## 9. Evidence Anchors

- **Sanitized photographs:** `[evidence/photos/<sample-id>/]`
- **Derived genotype summaries:** `[data/derived/<sample-id>/]`
- **Sanitized laboratory reports:** `[evidence/lab/<sample-id>/]`
- **External raw-data accessions:** `[ENA/SRA/controlled repository IDs]`
- **Manifest with hashes:** `[manifests/<sample-id>.json]`

## 10. Interpretation Boundary

- Commercial names are not authenticated cultivar identities.
- Compact growth, cold tolerance, and indoor fruiting do not establish TR4 resistance.
- Sequence similarity does not exclude epigenetic, mosaic, microbiome, or
  environment-dependent effects.
- Registry metadata records evidence; it does not modify biology.
