"""Buat file Excel SINTETIS (anonim) yang meniru DUA format file client: roadmap (A) dan laporan WellPlan (B).

Bukan data client. Dipakai untuk pengembangan, tes, dan demo sebelum data asli
tersedia / disetujui untuk dipakai dengan alat AI (Pasal 11).

Model fisik: soft-string sederhana (Johancsik). Data "aktual" dibangkitkan dengan
friction factor "sebenarnya" yang bergantung pada tipe sumur, section, kedalaman,
ditambah offset rig dan noise pengukuran, supaya ada pola yang bisa dipelajari ML.

Contoh:
    python scripts/make_sample_data.py --out data/sample --wells 15

Struktur keluaran sama dengan folder Training client: <tipe>/<sumur>/<file per section>.
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
    # kurva WellPlan dihitung terpisah per set FF (_compute_plan)
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
        "plan": None,
        "actual": actual,
        "interval": (top, bottom),
        "mu": mu,
    }


def _plan_at(plan: dict, key: str, ff: float) -> np.ndarray:
    """Kurva WellPlan untuk FF sembarang (interpolasi linear antar FF sintetis)."""
    ffs = sorted(plan[key])
    arr = np.vstack([plan[key][f] for f in ffs])
    return np.array([np.interp(ff, ffs, arr[:, k]) for k in range(arr.shape[1])])


def _compute_plan(data: dict, ffs: list[float]) -> None:
    """Hitung ulang kurva WellPlan untuk set FF yang diminta (tiap 100 ft)."""
    spec, sv = data["spec"], data["sv"]
    plan = {"md": sv[1:, 0], "pu": {}, "so": {}, "toff": {}, "ton": {}}
    bit_torque = SECTION_PLAN[spec.section][2]
    rot = []
    for ff in ffs:
        pu, so, toff = [], [], []
        for k in range(1, len(sv)):
            a, b, c, t = soft_string(sv, k, ff, spec.section)
            pu.append(a)
            so.append(b)
            toff.append(t)
            if ff == ffs[0]:
                rot.append(c)
        plan["pu"][ff], plan["so"][ff] = np.array(pu), np.array(so)
        plan["toff"][ff] = np.array(toff)
        plan["ton"][ff] = np.array(toff) + bit_torque
    plan["rot"] = np.array(rot)
    data["plan"] = plan


def write_roadmap_file(
    data: dict, path: Path, ffs: list[float], include_actual: bool = True
) -> None:
    """Format A: Drag, Torque, T&D Actual Reading, Casing Shoe (tata letak file client)."""
    spec, plan = data["spec"], data["plan"]
    top, bottom = data["interval"]
    # roadmap client: hanya beberapa kedalaman (~ tiap 1000 ft) di interval section
    md = plan["md"]
    pick = [i for i, d in enumerate(md) if d >= top and (d - top) % 1000 < 100 or d == md[-1]]
    pick = sorted(set(pick))
    wb = Workbook()
    ws = wb.active
    ws.title = "Drag"
    ws.append(["Calibrate", None, "PICK UP", "SLACK OFF", "ROTATE"])
    ws.append([None, None, 10, 2, 2.5])
    ws.append(["WellPlan Result"])
    ops = [
        "Run Measured Depth using:",
        "Tripping In using:",
        "Tripping Out using:",
        "Rotating Off Bottom using:",
    ]
    head, ffrow, unitrow = [], [], []
    for ff in ffs:
        head += ops + [None]
        ffrow += [f"open hole friction factor: {ff:.2f}"] * len(ops) + [None]
        unitrow += ["(ft)", "(kip)", "(kip)", "(kip)", None]
    head += ["Graph reference", "Tripping Out using:"]
    ws.append(head)
    ws.append(ffrow + [None, f"open hole friction factor: {ffs[0]:.2f}"])
    ws.append(unitrow + [None, "(kip)"])
    for i in pick:
        row = []
        for ff in ffs:
            row += [
                float(md[i]),
                round(float(_plan_at(plan, "so", ff)[i]), 1),
                str(round(float(_plan_at(plan, "pu", ff)[i]), 1)),  # angka sebagai teks
                round(float(plan["rot"][i]), 1),
                None,
            ]
        row += [None, round(float(_plan_at(plan, "pu", ffs[0])[i]) + 10, 1)]
        ws.append(row)

    ws = wb.create_sheet("Torque")
    ws.append(["WellPlan Result"])
    ws.append(["Calibrate On Bot Torque", None, 530])
    ws.append(["Calibrate Off Bot Torque", None, 930])
    ops = ["Run Measured Depth using:", "Rotating On Bottom using:", "Rotating Off Bottom using:"]
    head, ffrow, unitrow = [], [], []
    for ff in ffs:
        head += ops + [None]
        ffrow += [f"open hole friction factor: {ff:.2f}"] * len(ops) + [None]
        unitrow += ["(ft)", "(ft-lbf)", "(ft-lbf)", None]
    ws.append([None] * len(head) + ["Graph Reference"])
    ws.append(head[:-1] + [None, "Rotating On Bottom using:"])
    ws.append(ffrow[:-1] + [None, f"open hole friction factor: {ffs[0]:.2f}"])
    ws.append(unitrow[:-1] + [None, "(ft-kip)"])
    for i in pick:
        row = []
        for ff in ffs:
            row += [
                float(md[i]),
                round(float(_plan_at(plan, "ton", ff)[i]), 1),
                round(float(_plan_at(plan, "toff", ff)[i]), 1),
                None,
            ]
        ws.append(row[:-1] + [None, round(float(_plan_at(plan, "ton", ffs[0])[i]) + 530, 1)])

    ws = wb.create_sheet("T&D Actual Reading")
    ws.append([None, f"Well: {spec.name}"])
    ws.append([None, "Actual Block Weight (Klbs):", None, 20, "Section:", _frac(spec.section)])
    ws.append([None, None, None, None, "Run:", "#200"])
    ws.append(
        [
            None,
            "Depth (ft)",
            "Actual Pick Up Weight (Klbs)",
            "Actual Slack Off Weight (Klbs)",
            "Actual Rotating Weight Run (Klbs)",
            "Actual torque off bottom Run (Lbs-ft)",
            "Actual torque on bottom Run (Lbs-ft)",
        ]
    )
    if include_actual:
        for r in data["actual"]:
            ws.append(
                [None, round(r["depth"])]
                + [
                    None if r[k] is None else round(r[k], 0 if k in ("toff", "ton") else 1)
                    for k in ("pu", "so", "rot", "toff", "ton")
                ]
            )

    ws = wb.create_sheet("Casing Shoe")
    ws.append([])
    ws.append([None, "Depth", "Value", None, "Depth", "Value"])
    for v in range(-200, 400, 50):
        ws.append([None, 35, v, None, 35, v * 100 if v > 0 else v])
    wb.save(path)


def _frac(sec: float) -> str:
    return {17.5: '17-1/2"', 12.25: '12-1/4"', 8.5: '8-1/2"', 6.125: '6-1/8"'}.get(sec, f'{sec}"')


def write_wellplan_file(data: dict, path: Path, include_actual: bool = True) -> None:
    """Format B: laporan WellPlan (Summary, Tripping Load Analysis, Off Bottom Torque
    analysis, Rotary Drill Buckling Outputs, Survey Outputs, Drilling Data, Tripping  Data)."""
    spec, sv, dls, plan = data["spec"], data["sv"], data["dls"], data["plan"]
    top, bottom = data["interval"]
    ffs = [0.2, 0.3, 0.4, 0.5]
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([])
    ws.append([])
    ws.append([None, "Torque and Drag Load Cases"])
    ws.append([])
    ws.append([None, None, "Client:", None, "ANON"])
    ws.append([None, None, "Field:", None, "FLD-X"])
    ws.append([None, None, "Rig:", None, "RIG-1"])
    ws.append([None, None, "Well:", None, spec.name])
    ws.append([])
    ws.append([None, "BHA & WELLBORE DATA"])
    ws.append(
        [
            None,
            "Drilling Bit Depth Range:",
            f"{top} - {bottom} (ft)",
            None,
            None,
            "Bit Depth (single-point):",
            None,
            None,
            f"{bottom} (ft)",
        ]
    )
    ws.append(
        [
            None,
            "Tripping Range:",
            f"0 - {bottom} (ft)",
            None,
            None,
            "Block Weight:",
            None,
            None,
            "21 (1000 lbf)",
        ]
    )
    ws.append(
        [
            None,
            "Depth Increment:",
            "100 (ft)",
            None,
            None,
            "Single Depth Analysis \nMud Weight:",
            None,
            None,
            f"{MUD_PPG} (lbm/gal)",
        ]
    )
    ws.append([])
    ws.append([None, "BHA DESCRIPTION"])
    ws.append(
        [
            None,
            "Component Name",
            "Steel Grade",
            "Length",
            "Cum Length",
            "ID",
            "OD",
            "Max OD",
            "Lin Weight",
        ]
    )
    ws.append([None, None, None, "ft", "ft", "in", "in", "in", "lbm/ft"])
    comps = [
        (f'{spec.section}" PDC Bit', 1.0, 2.25, 5.75, spec.section, 128.0),
        ("Motor", 24.0, 5.5, 6.75, spec.section - 0.1, 89.7),
        ("NMDC", 30.5, 2.75, 6.5, 6.75, 90.1),
        ("MWD", 37.4, 2.8, 6.5, 6.5, 91.3),
        ('30 x 5" HWDP', 900.0, 3.0, 5.0, 6.5, 49.3),
        ('5" 19.50 DP To Surface', max(bottom - 993, 100), 4.276, 4.855, 6.625, 19.5),
    ]
    cum = 0.0
    for name, ln, i_d, od, mod, lw in comps:
        cum += ln
        ws.append([None, name, "G-105", ln, round(cum, 2), i_d, od, mod, lw])
    ws.append([])
    ws.append([None, "WELLBORE DESCRIPTION"])
    ws.append([None, "Section Name", "Length", "Cum Length", "Diameter"])
    ws.append([None, None, "ft", "ft", "in"])
    if top > 0:
        ws.append([None, "Casing Run", top, top, spec.section + 0.2])
    ws.append([None, f'{spec.section}" BHA Run', bottom - top, bottom, spec.section])
    ws.append([])
    ws.append([None, "FRICTION FACTORS"])
    ws.append(
        [
            None,
            None,
            "Cased Hole Translational (Slide)",
            "Open Hole Translational (Slide)",
            "Cased Hole Rotational",
            "Open Hole Rotational",
        ]
    )
    ws.append([None, "Base Set", 0.3, 0.4, 0.3, 0.4])
    for k, ff in enumerate(ffs, start=1):
        ws.append([None, f"Set {k}", ff, ff, ff, ff])

    md = plan["md"]
    ws = wb.create_sheet("Tripping Load Analysis")
    for _ in range(3):
        ws.append([])
    ws.append([None, "Tripping Load Analysis Output"])
    ws.append(
        [None, "Bit Depth"]
        + [f"CSG {f} OPH {f} Trip IN" for f in ffs[::-1]]
        + ["Rotate Off Bottom"]
        + [f"CSG {f} OPH {f} Trip Out" for f in ffs]
    )
    ws.append([None, "ft"] + ["1000 lbf"] * 9)
    for i, d in enumerate(md):
        ws.append(
            [None, str(int(d))]
            + [round(float(_plan_at(plan, "so", f)[i]), 3) for f in ffs[::-1]]
            + [round(float(plan["rot"][i]), 3)]
            + [round(float(_plan_at(plan, "pu", f)[i]), 3) for f in ffs]
        )

    ws = wb.create_sheet("Off Bottom Torque analysis")
    for _ in range(3):
        ws.append([])
    ws.append([None, "Off Bottom Torque Output"])
    ws.append([None, "Bit Depth"] + [f"CSG {f} OPH {f}" for f in ffs] + ["Solution Converged"])
    ws.append([None, "ft"] + ["1000 ft.lbf"] * 4)
    for i, d in enumerate(md):
        ws.append(
            [None, str(int(d))]
            + [round(float(_plan_at(plan, "toff", f)[i]) / 1000, 3) for f in ffs]
            + ["YES"]
        )

    ws = wb.create_sheet("Rotary Drill Buckling Outputs")
    for _ in range(4):
        ws.append([])
    ws.append([None, "Rotary Drilling Buckling Outputs"])
    ws.append([])
    ws.append([])
    ws.append(
        [
            None,
            "Measured Depth",
            "Buckling (Yes/No)",
            "Sinusoidal Buckling Margin",
            "Helical Buckling Margin",
            "Buckling Point from the bit",
            "Hookload",
            "Surface Torque",
        ]
    )
    ws.append([None, "ft", None, "1000 lbf", "1000 lbf", "ft", "1000 lbf", "1000 ft.lbf"])
    for i, d in enumerate(md):
        if d >= top:
            ws.append(
                [
                    None,
                    float(d),
                    "NO",
                    70.0,
                    90.0,
                    500.0,
                    round(float(plan["rot"][i]) - 15, 3),
                    round(float(_plan_at(plan, "ton", 0.4)[i]) / 1000, 3),
                ]
            )

    ws = wb.create_sheet("Survey Outputs")
    for _ in range(4):
        ws.append([])
    ws.append([None, None, "DETAIL SURVEY OUTPUTS"])
    ws.append([])
    ws.append([None, "Tortuosity Model:", "RANDOM_DEPENDENT_INC_AZM"])
    ws.append([None, "Start Depth", "End Depth", "Magnitude", "Period"])
    ws.append([None, "ft", "ft", "deg", "ft"])
    ws.append([None, 0, top, 1, 100])
    ws.append([])
    ws.append([])
    ws.append([None, "Measured Depth", "Inclination", "Azimuth", "Dog-Leg\nSeverity"])
    ws.append([None, "ft", "deg", "deg", "deg/100ft"])
    for i in range(len(sv)):
        ws.append(
            [
                None,
                round(float(sv[i, 0]), 2),
                round(float(sv[i, 1]), 3),
                round(float(sv[i, 2]), 3),
                round(float(dls[i]), 3),
            ]
        )

    ws = wb.create_sheet("Drilling Data")
    ws.append(["Drilling Parameter Record Sheet"])
    ws.append(["*data will be plotted in Drilling Loads Plot"])
    ws.append(
        [
            "Depth",
            "Slack Off Weight",
            "Rotating Weight",
            "Pick/Up Weight",
            "Rotary RPM",
            "Off-btm Torque",
            "Break Off Torque",
            "On-btm Torque",
        ]
    )
    if include_actual:
        for r in data["actual"]:
            ws.append(
                [
                    str(round(r["depth"])),
                    None if r["so"] is None else str(round(r["so"])),
                    None if r["rot"] is None else str(round(r["rot"])),
                    None if r["pu"] is None else str(round(r["pu"])),
                    "70",
                    None if r["toff"] is None else round(r["toff"] / 1000, 1),
                    None,
                    None if r["ton"] is None else round(r["ton"] / 1000, 1),
                ]
            )

    ws = wb.create_sheet("Tripping  Data")
    ws.append(["Tripping Hookload Record Sheet"])
    ws.append(["*data will be plotted in Tripping Loads Plot"])
    ws.append([None, "TRIP #1", None, None, "TRIP #2", None, None, "TRIP #3"])
    ws.append(
        [
            "Trip Depth",
            "Trip#1 Slack off",
            "Trip#1 Pick Up",
            "Trip Depth",
            "Trip#2 Slack off",
            "Trip#2 Pick Up",
            "Trip Depth",
            "Trip#3 Slack off",
            "Trip#3 Pick Up",
        ]
    )
    for name in ("Drilling Loads Plot", "Torque Plot", "Plots"):
        wb.create_sheet(name)
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


SECTIONS_BY_TYPE = {"J": [12.25, 8.5], "S": [12.25, 8.5], "Horizontal": [17.5, 12.25, 8.5]}


def section_spec(spec: WellSpec, section: float) -> WellSpec:
    return WellSpec(
        spec.name,
        spec.well_type,
        section,
        spec.td_ft,
        spec.kop_ft,
        spec.hold_inc,
        np.random.default_rng(spec.rng.integers(1 << 30)),
    )


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
        is_new = i >= args.wells
        fmt = "B" if spec.well_type == "Horizontal" or i % 2 else "A"
        folder = args.out / spec.well_type / f"{spec.name}{' BARU' if is_new else ''}"
        folder.mkdir(parents=True, exist_ok=True)
        for sec in SECTIONS_BY_TYPE[spec.well_type]:
            sspec = section_spec(spec, sec)
            data = build_well(sspec)
            if fmt == "A":
                ffs = [0.1, 0.3, 0.5] if i % 3 else [0.3, 0.4, 0.5]
                _compute_plan(data, ffs)
                name = f"P_{spec.name}_{sec:g}in TnD Roadmap.xlsx"
                write_roadmap_file(data, folder / name, ffs, include_actual=not is_new)
            else:
                _compute_plan(data, [0.2, 0.3, 0.4, 0.5])
                name = f"P_{spec.name}_BHA_{sec:g}in_TnD.xlsm"
                write_wellplan_file(data, folder / name, include_actual=not is_new)
            print(
                f"{spec.well_type}/{folder.name}/{name}: aktual={0 if is_new else len(data['actual'])}"
            )


if __name__ == "__main__":
    main()
