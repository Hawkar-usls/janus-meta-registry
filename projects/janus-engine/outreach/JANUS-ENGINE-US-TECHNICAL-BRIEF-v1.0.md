# JANUS Engine / “Calcifer” — Nonconfidential Technical Brief

## Purpose
JANUS Engine is a literature-anchored engineering concept for long-endurance underwater power and support systems. The present objective is not to claim a proven self-powered machine, but to obtain independent U.S. laboratory review and the smallest instrumented prototype needed to replace the remaining unknown parasitic loads and validate or falsify the integrated energy balance.

## Core architecture
- Artificial-gill oxygen extraction from water using a POMS membrane path derived from published artificial-gill/PEMFC work.
- PEM fuel cell with explicit external hydrogen as the chemical fuel; dissolved oxygen is the environmental oxidizer, not an energy source.
- Sectorized annular membrane/flow architecture intended to improve flow utilization and reduce boundary-layer limitations.
- Coreless/slotless AFPM bidirectional starter-generator for startup torque, RPM control and genuine regeneration only when an independent mechanical source is measured.
- Dual managed battery buffers: one pack may support startup/transients while the other preserves regenerative headroom; the proof ledger always uses total stored energy E_A + E_B.
- Scale-management path using low-hardness water, low-adhesion internal surfaces, Axle/wiper action and a removable crystal trap.
- Purge, gas-loop, thermal-management and control loads are explicitly included rather than hidden.

## What is already anchored
Published direct artificial-gill work provides measured membrane area, water flow, gas recirculation, oxygen-transfer rates and low-pO2 fuel-cell output. JANUS carries these as literature anchors, not as measured JANUS hardware performance.

The current project branch has also frozen:
- the startup-state logic;
- magnetic-drive and Faraday-generator accounting;
- dual-battery energy bookkeeping;
- antiscalant/scale-trap research;
- a measured-parasitic replacement plan;
- a preregistered full energy-balance verdict structure.

## What remains unknown
The project intentionally stopped short of a final net-energy claim because the following JANUS-specific hardware measurements do not yet exist:
- pump electrical power and hydraulic ΔP at the actual membrane flow;
- gas-loop/blower power at the required recirculation condition;
- AFPM motor/generator efficiency, torque map and zero-current crossover;
- purge event energy and pressure/gas loss;
- crystal-trap ΔP and wiper incremental torque;
- controls/sensor power;
- active or passive thermal-management penalty;
- achieved POMS oxygen flux and PEMFC efficiency in the actual JANUS geometry.

Unknown watts remain unknown; they are not set to zero or replaced by optimistic placeholders.

## Frozen experiment: R0P1A / RUN-008
The exact metering sequence is preregistered before observing the missing hardware data:

P0 CONTROLS ONLY → P1 WATER ONLY → P2 GAS ONLY → P3 AFPM ONLY → P4 PURGE → P5 SCALE HARDWARE → P6 THERMAL → P7 FULL STACK.

Required synchronized measurements include DC-bus V/I/Wh, Battery A and B energy, pump/blower/controls power, PEMFC gross power, AFPM DC power, Axle torque/RPM, water flow, membrane/trap ΔP, gas flow, internal pO2, dissolved O2 in/out, humidity, temperatures and purge-event joules.

The full-stack bus balance must close within declared measurement uncertainty before any pass is admitted.

Predeclared verdicts are:
- FAIL_NET_NEGATIVE
- PASS_STEADY_POSITIVE_BUT_STARTUP_NOT_REPAID
- PASS_BATTERY_NEUTRAL_NO_EXPORT
- PASS_BATTERY_NEUTRAL_WITH_VERIFIED_SURPLUS
- UNKNOWN_MEASUREMENT_INCOMPLETE
- INVALID_ENERGY_LEDGER_DOES_NOT_CLOSE

## Energy-accounting boundaries
- Hydrogen remains the explicit external chemical fuel.
- Oxygen is an oxidizer, not primary energy.
- Two batteries do not create energy; only E_A + E_B matters.
- Generator output is credited only against independently measured mechanical input or rotor kinetic-energy decrease.
- Same-shaft motor→generator recirculation is not counted as new energy.
- Waste heat must have a real external sink.

## Requested U.S. collaboration
I am seeking one of the following:
1. Independent engineering review by a laboratory experienced in underwater vehicles, membranes, fuel cells, power electronics or marine energy systems.
2. Access to an appropriate test facility or partner able to build the smallest safe, instrumented membrane/flow/PEMFC demonstrator.
3. Execution of the frozen R0P1A P0–P7 measurement sequence so RUN-008 can be completed with measured data rather than simulation.
4. Technical routing to a more appropriate U.S. Navy, DoD, DOE or academic laboratory if this is outside the recipient’s scope.

The goal is falsifiable validation, not a predetermined positive outcome.

## Public project material
Project branch:
https://github.com/Hawkar-usls/janus-meta-registry/tree/research/janus-engine

Measurement contract:
https://github.com/Hawkar-usls/janus-meta-registry/blob/research/janus-engine/projects/janus-engine/gates/JANUS-ENGINE-R0P1A-MEASUREMENT-DATA-CONTRACT-v1.0.json

RUN-008 preregistration:
https://github.com/Hawkar-usls/janus-meta-registry/blob/research/janus-engine/projects/janus-engine/simulations/JANUS-ENGINE-SIM-HOWL-CASTLE-RUN-008-FULL-MEASURED-ENERGY-BALANCE-v0.1.json

This brief is nonconfidential and may be routed internally to the appropriate technical group.
