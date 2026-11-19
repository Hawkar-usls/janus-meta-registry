"""Reduce one steady vacuum-cassette window and its matched impermeable blank."""
import argparse
import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path


FIELDS = (
    "t_s", "Q_water_L_s", "DO_in_mg_L", "DO_out_mg_L", "T_water_C",
    "DeltaP_POMS_Pa", "P_collector_abs_kPa", "Q_dry_gas_sccm",
    "x_O2_dry", "P_vacuum_W",
)
# sccm is dry gas referred to 273.15 K and 101325 Pa.
MG_O2_S_PER_SCCM = 31998.8 / (22413.97 * 60)


def positive(value, label):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return value


def read_window(path, max_gap):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames or any(reader.fieldnames.count(f) != 1 for f in FIELDS):
        raise ValueError(f"{path}: expected one of each column in --template")
    previous = None
    integrals = {}
    elapsed = 0.0
    for row in reader:
        try:
            if None in row:
                raise ValueError("extra CSV cells")
            r = {k: float(row[k]) for k in FIELDS}
            if not all(map(math.isfinite, r.values())):
                raise ValueError("non-finite value")
            if not 0 <= r["x_O2_dry"] <= 1:
                raise ValueError("O2 fraction outside [0,1]")
            if min(r[k] for k in ("DO_in_mg_L", "DO_out_mg_L",
                                 "Q_dry_gas_sccm", "P_vacuum_W")) < 0:
                raise ValueError("negative concentration, gas flow or power")
            q = positive(r["Q_water_L_s"], "water flow")
            positive(r["P_collector_abs_kPa"], "absolute collector pressure")
            values = {
                "water_o2_mg_s": q * (r["DO_in_mg_L"] - r["DO_out_mg_L"]),
                "collector_o2_mg_s": r["Q_dry_gas_sccm"] * r["x_O2_dry"] * MG_O2_S_PER_SCCM,
                "Q_water_L_s": q, "DeltaP_POMS_Pa": r["DeltaP_POMS_Pa"],
                "P_hydraulic_W": q * 0.001 * r["DeltaP_POMS_Pa"],
                "P_vacuum_W": r["P_vacuum_W"],
                "P_collector_abs_kPa": r["P_collector_abs_kPa"],
                "T_water_C": r["T_water_C"], "DO_in_mg_L": r["DO_in_mg_L"],
            }
            if previous is not None:
                last_t, last = previous
                dt = r["t_s"] - last_t
                if not 0 < dt <= max_gap:
                    raise ValueError("non-increasing time or gap exceeds declared maximum")
                for k in values:
                    step = (values[k] + last[k]) * dt / 2
                    integrals[k] = integrals.get(k, 0.0) + step
                elapsed += dt
            previous = r["t_s"], values
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path} line {reader.line_num}: {exc}") from exc
    positive(elapsed, f"{path}: window duration")
    return {"sha256": digest, "duration_s": elapsed,
            "vacuum_energy_J": integrals["P_vacuum_W"],
            "mean": {k: val / elapsed for k, val in integrals.items()}}


def reduce_pair(active, blank, area, flow_area):
    if active["sha256"] == blank["sha256"]:
        raise ValueError("active and blank have identical content")
    a, b = active["mean"], blank["mean"]
    water = a["water_o2_mg_s"] - b["water_o2_mg_s"]
    gas = a["collector_o2_mg_s"] - b["collector_o2_mg_s"]
    for w in (active, blank):
        w["mean_water_velocity_m_s"] = w["mean"]["Q_water_L_s"] * 0.001 / flow_area
    return {
        "status": "REDUCED_PAIR_REQUIRES_METROLOGY_REVIEW",
        "active_area_m2": area, "open_water_area_m2": flow_area,
        "active": active, "blank": blank,
        "blank_corrected": {
            "water_o2_mg_s": water, "collector_o2_mg_s": gas,
            "water_flux_mg_m2_s": water / area, "collector_flux_mg_m2_s": gas / area,
            "water_minus_collector_mg_s": water - gas,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--active", type=Path)
    parser.add_argument("--blank", type=Path)
    parser.add_argument("--area-m2", type=float, help="exposed membrane area")
    parser.add_argument("--open-water-area-m2", type=float, help="open channel cross-section")
    parser.add_argument("--max-gap-s", type=float, help="largest allowed acquisition interval")
    args = parser.parse_args()
    if args.template:
        print(",".join(FIELDS))
        return
    if any(v is None for v in (args.active, args.blank, args.area_m2,
                               args.open_water_area_m2, args.max_gap_s)):
        parser.error("supply both CSV files, both areas and the declared time gap")
    try:
        area = positive(args.area_m2, "membrane area")
        flow_area = positive(args.open_water_area_m2, "water area")
        gap = positive(args.max_gap_s, "maximum gap")
        result = reduce_pair(read_window(args.active, gap), read_window(args.blank, gap),
                             area, flow_area)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, csv.Error) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
