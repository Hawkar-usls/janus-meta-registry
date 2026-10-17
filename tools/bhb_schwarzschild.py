#!/usr/bin/env python3
"""BHB R0: exact-decimal Schwarzschild radial-collision benchmark.

The local orthonormal frame belongs to a static observer at r > r_s.
Both equal-mass particles have conserved specific energy e=1 (rest at
infinity), with radial velocity beta = sqrt(r_s/r) in this frame.

An outgoing e=1 *geodesic* next to an eternal Schwarzschild horizon
originates in the white-hole sector, not from an ordinary collapsing BH.
Thus the head-on case is a kinematic counterfactual, not a prediction of
an accessible high-energy source or its luminosity at infinity.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, localcontext


RATIOS = ["10", "2", "1.1", "1.01", "1.0001", "1.000001", "1.000000000001"]
PROTON_REST_GEV = Decimal("0.938272")  # declared nominal mass-energy, not an experimental input


def compact(value: Decimal, digits: int = 12) -> str:
    """Round numeric output for readability, without binary float conversion."""
    return format(value, f".{digits}g")


def run() -> dict:
    with localcontext() as ctx:
        ctx.prec = 70
        m = PROTON_REST_GEV
        results = []
        max_redshift_error = Decimal(0)
        max_invariant_error = Decimal(0)
        preceding = None

        for ratio_text in RATIOS:
            ratio = Decimal(ratio_text)
            lapse2 = (ratio - 1) / ratio  # f(r) = 1 - r_s/r
            beta2 = 1 / ratio
            beta = beta2.sqrt()
            gamma = 1 / lapse2.sqrt()

            # Physical control: two radial infallers with identical e=1.
            infall_infall_gev = 2 * m

            # Counterfactual: one radial infaller, one outgoing e=1 geodesic.
            head_on_gev = 2 * m * gamma

            # Independent local invariant s = m^2 + m^2 + 2 m^2 gamma_rel,
            # gamma_rel=(1+beta^2)/(1-beta^2).
            gamma_rel = (1 + beta2) / (1 - beta2)
            invariant_gev = (2 * m * m * (1 + gamma_rel)).sqrt()
            invariant_error = abs(head_on_gev - invariant_gev)
            max_invariant_error = max(max_invariant_error, invariant_error)

            # Pure kinematic redshift identity, NOT predicted energy escape:
            # sqrt(f) E_cm = 2 m, for symmetric e=1 head-on test case.
            redshift_identity_gev = head_on_gev * lapse2.sqrt()
            redshift_error = abs(redshift_identity_gev - 2 * m)
            max_redshift_error = max(max_redshift_error, redshift_error)

            assert Decimal(0) < beta < 1
            assert invariant_error < Decimal("1e-50")
            assert redshift_error < Decimal("1e-50")
            assert preceding is None or head_on_gev > preceding
            preceding = head_on_gev

            results.append({
                "r_over_rs": ratio_text,
                "lapse_squared": compact(lapse2),
                "beta_over_c_local_static_frame": compact(beta, 18),
                "one_minus_beta_over_c": compact(1 - beta, 12),
                "infall_infall_Ecm_GeV": compact(infall_infall_gev),
                "infall_outgoing_Ecm_GeV": compact(head_on_gev),
                "kinematic_redshift_identity_GeV": compact(redshift_identity_gev),
            })

        return {
            "artifact_uuid": "BHB-BLACK-HOLE-BOOM-R0-2026-10-17-v1.0",
            "title": "BHB - Black Hole Boom",
            "date_utc": "2026-10-17",
            "schema_id": "janus.physics.bhb.schwarzschild_radial_collision.v1",
            "version": "v1.0",
            "classification": "REPRODUCIBLE_ANALYTIC_BENCHMARK__NO_ASTROPHYSICAL_DETECTION",
            "model": {
                "spacetime": "Eternal Schwarzschild vacuum, nonrotating, uncharged; test particles; G=c=1 for dimensionless kinematics",
                "region": "r>r_s (outside horizon only)",
                "collision": "Equal-mass radial geodesics at one event, e1=e2=1 (rest at infinity)",
                "mass_energy_each_particle_GeV": compact(m),
                "mass_energy_label": "nominal proton rest energy (GeV), illustrative",
                "formula_lapse": "f=1-r_s/r",
                "formula_local_speed": "beta=sqrt(r_s/r)",
                "formula_same_direction": "E_cm=2*m*c^2",
                "formula_head_on": "E_cm=2*m*c^2/sqrt(1-r_s/r)",
                "formula_relative_gamma": "gamma_rel=(1+beta^2)/(1-beta^2)",
                "worldline_warning": "Outgoing e=1 geodesic near an eternal Schwarzschild horizon implies a white-hole-origin trajectory. Not an ordinary collapsing black-hole outflow.",
            },
            "rows": results,
            "verification": {
                "decimal_precision_digits": 70,
                "all_subluminal": True,
                "co_infall_constant_center_of_mass_energy": True,
                "head_on_monotonic_near_horizon": True,
                "local_minkowski_invariant_check": "PASS",
                "redshift_identity_check": "PASS",
                "max_invariant_absolute_error_GeV": compact(max_invariant_error, 5),
                "max_redshift_identity_absolute_error_GeV": compact(max_redshift_error, 5),
                "numerical_role": "Evaluation of known GR kinematic formulae; not N-body, GRMHD, Monte Carlo or numerical Einstein evolution",
            },
            "gates": {
                "SCHWARZSCHILD_KINEMATICS": "PASS_ANALYTIC_WITH_NUMERIC_CROSSCHECK",
                "ORDINARY_BH_OUTGOING_GEODESIC_PROVENANCE": "FAIL_UNDER_E1_RADIAL_FREE_FALL_ASSUMPTIONS",
                "ACTUAL_LOCAL_COLLISION_RATE": "OPEN_UNMODELED",
                "ESCAPING_RADIATION_ENERGY_AND_SPECTRUM": "OPEN_UNMODELED",
                "KERR_BSW_ROTATING_BLACK_HOLE": "NOT_TESTED",
                "NEW_PHYSICS_OR_EXPLOSION_DETECTION": "NOT_ESTABLISHED",
            },
            "claim_ceiling": "An idealized, counter-propagating pair can have increasing local E_cm as r approaches r_s, but this is neither attainable outgoing flow from an ordinary Schwarzschild horizon nor a measured/escaping boom. Two identical infallers have finite E_cm=2mc^2.",
            "limitations": [
                "Only radial e=1 geodesics and Schwarzschild; ignores spin, backreaction, finite size, scattering cross sections, quantum fields and emission transport.",
                "The static local frame ceases to exist at the horizon; r=r_s is not sampled and no infinite-energy collision is claimed.",
                "E_cm is local invariant center-of-mass energy; multiplying by sqrt(f) is an algebraic check, not a general escape-energy law for collision products.",
                "Outgoing geodesic's white-hole provenance makes the head-on benchmark non-realistic for an ordinary astrophysical collapsing Schwarzschild black hole.",
            ],
            "sources": [
                {"title": "Kerr Black Holes as Particle Accelerators to Arbitrarily High Energy", "doi": "10.1103/PhysRevLett.103.111102", "arxiv": "0909.0169", "role": "Distinct Kerr BSW mechanism; not implemented in R0"},
                {"title": "Kinematic censorship and high energy particle collisions in the Schwarzschild background", "arxiv": "2411.01989", "role": "White-hole provenance and finite-event caveats for head-on Schwarzschild collisions"},
                {"title": "Full set of scenarios of high energy collision in the Schwarzschild background and kinematic censorship", "arxiv": "2609.14701", "role": "2026 classification and caution about physically realized outgoing streams"},
            ],
            "janus_integrations": {
                "registry": "Hawkar-usls/janus-meta-registry",
                "discovered_related_repositories": ["Hawkar-usls/Janus-Cosmos", "Hawkar-usls/TOPA", "Hawkar-usls/Janus-HELIOS", "Hawkar-usls/Janus-Demiurge"],
                "existing_reusable_gr_geodesic_module_identified": False,
                "code_path": "tools/bhb_schwarzschild.py",
                "provenance_kind": "FRESH_DETERMINISTIC_R0_BENCHMARK",
            },
            "next_gate": "BHB-R1: Kerr equatorial geodesics, finite spin a/M<1, critical angular-momentum accessibility, admissible outgoing provenance, and escaped-energy ray tracing; preserve negative controls.",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true", help="compact machine-readable JSON")
    args = parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True))
