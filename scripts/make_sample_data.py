"""Buat file Excel SINTETIS (anonim) yang meniru struktur laporan WellPlan + data aktual.

Bukan data client. Dipakai untuk pengembangan, tes, dan demo sebelum data asli
tersedia / disetujui untuk dipakai dengan alat AI (Pasal 11).

Model fisik: soft-string sederhana (Johancsik). Data "aktual" dibangkitkan dengan
friction factor "sebenarnya" yang bergantung pada tipe sumur, section, kedalaman,
ditambah offset rig dan noise pengukuran, supaya ada pola yang bisa dipelajari ML.

Contoh:
    python scripts/make_sample_data.py --out data/sample --wells 15
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from openpyxl import Workbook

FFS = [0.1, 0.3, 0.5]
STEP_FT = 100.0
BLOCK_WEIGHT_LBF = 35_000.0
MUD_PPG = 10.0
BF = 1 - MUD_PPG / 65.5
DP_PPF, BHA_PPF, BHA_LEN = 21.9, 75.0, 600.0
SECTION_PLAN = {
    # section (in): (puncak ft, dasar relatif ft, torsi bit ft-lbf, bit od)
    17.5: (0.0, 3200.0, 6000.0),
    12.25: (3200.0, 7500.0, 4500.0),
    8.5: (7500.0, None, 3000.0),
    6.125: (8500.0, None, 2000.0),
}


@dataclass
class WellSpec:
    name: str
    well_type: str
    section: float
    td_ft: float
    kop_ft: float
    hold_inc: float
    rng: np.random.Generator


def make_survey(spec: WellSpec) -> np.ndarray:
    """Kembalikan array [md, inc, azi] tiap 100 ft."""
    md = np.arange(0, spec.td_ft + STEP_FT, STEP_FT)
    inc = np.zeros_like(md)
    azi = np.full_like(md, float(spec.rng.uniform(0, 360)))
    if spec.well_type == "J":
        build = 2.5
        inc = np.clip((md - spec.kop_ft) / 100 * build, 0, spec.hold_inc)
    elif spec.well_type == "S":
        build = 2.5
        inc = np.clip((md - spec.kop_ft) / 100 * build, 0, spec.hold_inc)
        drop_start = spec.td_ft * 0.65
        drop = np.clip((md - drop_start) / 100 * 2.0, 0, spec.hold_inc - 5)
        inc = np.maximum(inc - drop, np.where(md > drop_start, 5.0, 0.0))
        inc = np.where(md < spec.kop_ft, 0.0, inc)
    else:  # Horizontal
        build = 8.0
        inc = np.clip((md - spec.kop_ft) / 100 * build, 0, 89.5)
    inc = inc + spec.rng.normal(0, 0.15, size=inc.shape) * (inc > 0)
    inc = np.clip(inc, 0, 95)
    azi = azi + np.cumsum(spec.rng.normal(0, 0.3, size=md.shape))
    return np.column_stack([md, inc, azi % 360])


def survey_tvd_dls(sv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    md, inc, azi = sv[:, 0], np.radians(sv[:, 1]), np.radians(sv[:, 2])
    tvd = np.zeros_like(md)
    dls = np.zeros_like(md)
    for i in range(1, len(md)):
        ds = md[i] - md[i - 1]
        cos_dl = np.cos(inc[i] - inc[i - 1]) - np.sin(inc[i - 1]) * np.sin(inc[i]) * (
            1 - np.cos(azi[i] - azi[i - 1])
        )
        dl = np.arccos(np.clip(cos_dl, -1, 1))
        rf = 1.0 if dl < 1e-6 else 2 / dl * np.tan(dl / 2)
        tvd[i] = tvd[i - 1] + ds / 2 * (np.cos(inc[i - 1]) + np.cos(inc[i])) * rf
        dls[i] = np.degrees(dl) / ds * 100
    return tvd, dls


def soft_string(sv: np.ndarray, bit_idx: int, mu: float | np.ndarray, hole_in: float):
    """Hitung (pick up, slack off, rotating, torsi off-bottom) di permukaan untuk bit
    di stasiun `bit_idx`. mu boleh array per elemen (FF bervariasi terhadap kedalaman)."""
    md = sv[: bit_idx + 1, 0]
    inc = np.radians(sv[: bit_idx + 1, 1])
    azi = np.radians(sv[: bit_idx + 1, 2])
    mu_arr = np.asarray(mu, dtype=float)
    mu_arr = mu_arr[: bit_idx + 1] if mu_arr.ndim else np.full(md.shape, float(mu_arr))
    t_pu = t_so = t_rot = 0.0
    torque = 0.0
    radius_ft = min(6.5, hole_in * 0.75) / 2 / 12
    for i in range(bit_idx, 0, -1):
        ds = md[i] - md[i - 1]
        from_bit = md[bit_idx] - md[i]
        w = (BHA_PPF if from_bit < BHA_LEN else DP_PPF) * BF * ds
        th = (inc[i] + inc[i - 1]) / 2
        dth = inc[i] - inc[i - 1]
        dph = azi[i] - azi[i - 1]
        dph = (dph + np.pi) % (2 * np.pi) - np.pi
        m = mu_arr[i]

        def normal(t, th=th, dth=dth, dph=dph, w=w):
            return np.hypot(t * dph * np.sin(th), t * dth + w * np.sin(th))

        n_pu = normal(t_pu)
        t_pu = t_pu + w * np.cos(th) + m * n_pu
        n_so = normal(t_so)
        t_so = t_so + w * np.cos(th) - m * n_so
        n_rot = normal(t_rot)
        t_rot = t_rot + w * np.cos(th)
        torque += m * n_rot * radius_ft
    return (
        (t_pu + BLOCK_WEIGHT_LBF) / 1000,
        (t_so + BLOCK_WEIGHT_LBF) / 1000,
        (t_rot + BLOCK_WEIGHT_LBF) / 1000,
        torque,
    )


def true_mu(spec: WellSpec, sv: np.ndarray, well_offset: float) -> np.ndarray:
    base = {"J": 0.22, "S": 0.26, "Horizontal": 0.30}[spec.well_type]
    base += {17.5: -0.02, 12.25: 0.0, 8.5: 0.03, 6.125: 0.05}[spec.section]
    inc = sv[:, 1]
    # pengaruh cutting bed di inklinasi 40-70 derajat
    bed = 0.06 * np.exp(-(((inc - 55) / 15) ** 2))
    return np.clip(base + well_offset + bed, 0.05, 0.6)


def section_interval(spec: WellSpec) -> tuple[float, float]:
    top, bottom, _ = SECTION_PLAN[spec.section]
    if bottom is None:
        bottom = spec.td_ft
    top = min(top, spec.td_ft - 1500)
    return top, min(bottom, spec.td_ft)


def build_well(spec: WellSpec) -> dict:
    top, bottom = section_interval(spec)
    sv_full = make_survey(spec)
    sv = sv_full[sv_full[:, 0] <= bottom + 1e-6]
    tvd, dls = survey_tvd_dls(sv)
    hole = spec.section
    bit_torque = SECTION_PLAN[spec.section][2]

    plan_depths = sv[1:, 0]
    plan = {"md": plan_depths, "pu": {}, "so": {}, "toff": {}, "ton": {}}
    rot = []
    for ff in FFS:
        pu, so, toff = [], [], []
        for k in range(1, len(sv)):
            a, b, c, t = soft_string(sv, k, ff, hole)
            pu.append(a)
            so.append(b)
            toff.append(t)
            if ff == FFS[0]:
                rot.append(c)
        plan["pu"][ff] = np.array(pu)
        plan["so"][ff] = np.array(so)
        plan["toff"][ff] = np.array(toff)
        plan["ton"][ff] = np.array(toff) + bit_torque
    plan["rot"] = np.array(rot)

    # Data aktual: tiap ~93 ft (satu stand) di interval section
    rng = spec.rng
    well_offset = rng.normal(0, 0.025)
    rig_offset = rng.normal(0, 2.5)  # klbf, kalibrasi deadline sensor
    mu = true_mu(spec, sv, well_offset)
    act_depths = np.arange(top + 93, bottom, 93.0)
    actual = []
    for d in act_depths:
        k = int(np.searchsorted(sv[:, 0], d))
        k = min(max(k, 1), len(sv) - 1)
        a, b, c, t = soft_string(sv, k, mu, hole)
        frac = (d - sv[k - 1, 0]) / (sv[k, 0] - sv[k - 1, 0])
        if k > 1:
            a0, b0, c0, t0 = soft_string(sv, k - 1, mu, hole)
            a, b, c, t = (
                a0 + frac * (a - a0),
                b0 + frac * (b - b0),
                c0 + frac * (c - c0),
                t0 + frac * (t - t0),
            )
        noise = lambda x, p: x * (1 + rng.normal(0, p))  # noqa: E731
        row = {
            "depth": d,
            "pu": noise(a + rig_offset, 0.015),
            "so": noise(b + rig_offset, 0.02),
            "rot": noise(c + rig_offset, 0.012),
            "toff": noise(t * 1.05, 0.06),
            "ton": noise(t * 1.05 + bit_torque * rng.uniform(0.8, 1.3), 0.08),
        }
        for key in ("pu", "so", "rot", "toff", "ton"):
            if rng.random() < 0.08:
                row[key] = None
        actual.append(row)

    return {
        "spec": spec,
        "sv": sv,
        "tvd": tvd,
        "dls": dls,
        "plan": plan,
        "actual": actual,
        "interval": (top, bottom),
        "mu": mu,
    }


def _title(ws, text: str) -> None:
    ws.append([text])
    ws.append(["Data sintetis - bukan data client"])
    ws.append([])


def write_wellplan(data: dict, path: Path, include_actual: bool = True) -> None:
    spec: WellSpec = data["spec"]
    sv, tvd, dls, plan = data["sv"], data["tvd"], data["dls"], data["plan"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    _title(ws, "Torque and Drag Analysis Report")
    ws.append(["Company:", "ANON"])
    ws.append(["Well Name:", spec.name])
    ws.append(["Field:", "FLD-X"])
    ws.append(["Hole Size (in):", spec.section])
    ws.append(["Casing Shoe (ft):", data["interval"][0]])
    ws.append(["Mud Weight (ppg):", MUD_PPG])

    ws = wb.create_sheet("Survey Outputs")
    _title(ws, "Survey Outputs")
    ws.append(["MD (ft)", "Inc (°)", "Azi (°)", "TVD (ft)", "DLS (°/100ft)"])
    for i in range(len(sv)):
        ws.append(
            [
                round(sv[i, 0], 1),
                round(sv[i, 1], 2),
                round(sv[i, 2], 2),
                round(tvd[i], 1),
                round(dls[i], 2),
            ]
        )

    ws = wb.create_sheet("Tripping Load Analysis")
    _title(ws, "Tripping Load Analysis")
    head = ["Measured Depth (ft)"]
    head += [f"Pick Up FF {ff:.2f} (kip)" for ff in FFS]
    head += [f"Slack Off FF {ff:.2f} (kip)" for ff in FFS]
    head += ["Rotating Off Bottom (kip)"]
    ws.append(head)
    for i, d in enumerate(plan["md"]):
        ws.append(
            [d]
            + [round(plan["pu"][ff][i], 2) for ff in FFS]
            + [round(plan["so"][ff][i], 2) for ff in FFS]
            + [round(plan["rot"][i], 2)]
        )

    ws = wb.create_sheet("Off Bottom Torque")
    _title(ws, "Torque Analysis")
    head = ["Measured Depth (ft)"]
    head += [f"Off Bottom Torque FF {ff:.2f} (ft-lbf)" for ff in FFS]
    head += [f"On Bottom Torque FF {ff:.2f} (ft-lbf)" for ff in FFS]
    ws.append(head)
    for i, d in enumerate(plan["md"]):
        ws.append(
            [d]
            + [round(plan["toff"][ff][i], 0) for ff in FFS]
            + [round(plan["ton"][ff][i], 0) for ff in FFS]
        )

    ws = wb.create_sheet("BHA")
    _title(ws, "Bottom Hole Assembly")
    ws.append(["No", "Description", "OD (in)", "ID (in)", "Length (ft)"])
    ws.append([1, "Bit PDC", spec.section, None, 1.5])
    ws.append([2, "Mud Motor", 6.75, 4.5, 30])
    ws.append([3, "MWD", 6.75, 3.25, 60])
    ws.append([4, "Drill Collar", 6.5, 2.81, 270])
    ws.append([5, "HWDP", 5.0, 3.0, 240])

    if include_actual:
        write_actual_sheets(wb, data)
    wb.save(path)


def write_actual_sheets(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("T&D Actual Reading")
    _title(ws, "T&D Actual Reading")
    ws.append(
        [
            "Depth (ft)",
            "Pick Up (kip)",
            "Slack Off (kip)",
            "Rotating Weight (kip)",
            "Torque Off Bottom (ft-lbf)",
            "Torque On Bottom (ft-lbf)",
        ]
    )
    for r in data["actual"]:
        ws.append(
            [r["depth"]]
            + [
                None if r[k] is None else round(r[k], 2 if k in ("pu", "so", "rot") else 0)
                for k in ("pu", "so", "rot", "toff", "ton")
            ]
        )

    rng = data["spec"].rng
    ws = wb.create_sheet("Drilling Data")
    _title(ws, "Drilling Data")
    ws.append(["Depth (ft)", "WOB (kip)", "RPM", "Torque (ft-lbf)"])
    for r in data["actual"][::2]:
        if r["ton"] is not None:
            ws.append(
                [
                    r["depth"] + 10,
                    round(rng.uniform(15, 30), 1),
                    int(rng.uniform(80, 140)),
                    round(r["ton"] * rng.uniform(0.95, 1.05)),
                ]
            )

    ws = wb.create_sheet("Tripping Data")
    _title(ws, "Tripping Data")
    ws.append(["Depth (ft)", "Hookload (kip)", "Direction"])
    for r in data["actual"][::3]:
        if r["pu"] is not None:
            ws.append([r["depth"], round(r["pu"], 1), "POOH"])
        if r["so"] is not None:
            ws.append([r["depth"], round(r["so"], 1), "RIH"])


def write_roadmap(data: dict, path: Path) -> None:
    plan = data["plan"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Drag"
    _title(ws, f"Drag Roadmap - {data['spec'].name}")
    ws.append(
        ["Depth (ft)"]
        + [f"Pick Up FF {ff:.1f} (kip)" for ff in FFS]
        + [f"Slack Off FF {ff:.1f} (kip)" for ff in FFS]
        + ["Rotating (kip)"]
    )
    for i, d in enumerate(plan["md"]):
        ws.append(
            [d]
            + [round(plan["pu"][ff][i], 2) for ff in FFS]
            + [round(plan["so"][ff][i], 2) for ff in FFS]
            + [round(plan["rot"][i], 2)]
        )
    ws = wb.create_sheet("Torque")
    _title(ws, f"Torque Roadmap - {data['spec'].name}")
    ws.append(
        ["Depth (ft)"]
        + [f"Off Bottom FF {ff:.1f} (ft-lbf)" for ff in FFS]
        + [f"On Bottom FF {ff:.1f} (ft-lbf)" for ff in FFS]
    )
    for i, d in enumerate(plan["md"]):
        ws.append(
            [d]
            + [round(plan["toff"][ff][i]) for ff in FFS]
            + [round(plan["ton"][ff][i]) for ff in FFS]
        )
    wb.save(path)


def well_specs(n: int, seed: int) -> list[WellSpec]:
    rng = np.random.default_rng(seed)
    types = ["J", "S", "Horizontal"]
    sections = [12.25, 8.5, 17.5, 8.5, 6.125]
    specs = []
    for i in range(n):
        t = types[i % 3]
        sec = sections[i % len(sections)]
        if t == "Horizontal" and sec == 17.5:
            sec = 8.5
        if t != "Horizontal" and sec == 6.125:
            sec = 12.25
        td = {
            "J": rng.uniform(9000, 11000),
            "S": rng.uniform(9000, 11000),
            "Horizontal": rng.uniform(10500, 12500),
        }[t]
        kop = rng.uniform(1500, 3000)
        if sec == 17.5:
            kop = rng.uniform(800, 1500)  # supaya section atas tidak vertikal murni
        specs.append(
            WellSpec(
                name=f"W{i + 1:02d}",
                well_type=t,
                section=sec,
                td_ft=round(td, -2),
                kop_ft=round(kop, -2),
                hold_inc=float(rng.uniform(25, 50)),
                rng=np.random.default_rng(seed + 1000 + i),
            )
        )
    return specs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data/sample"))
    ap.add_argument("--wells", type=int, default=15)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--new-wells",
        type=int,
        default=2,
        help="Jumlah sumur 'baru' (WellPlan tanpa data aktual) untuk uji prediksi",
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    specs = well_specs(args.wells + args.new_wells, args.seed)
    for i, spec in enumerate(specs):
        data = build_well(spec)
        is_new = i >= args.wells
        name = f"{spec.name}_{spec.section:g}in_{'baru_' if is_new else ''}wellplan.xlsx"
        write_wellplan(data, args.out / name, include_actual=not is_new)
        if i < 2:
            write_roadmap(data, args.out / f"{spec.name}_{spec.section:g}in_roadmap.xlsx")
        print(
            f"{name}: tipe={spec.well_type} section={spec.section} td={spec.td_ft:.0f} ft "
            f"aktual={0 if is_new else len(data['actual'])} titik"
        )


if __name__ == "__main__":
    main()
