"""Template Excel untuk diisi pengguna lalu diunggah (semua teks dalam bahasa Inggris).

Struktur sheet sama dengan format A (roadmap) yang dibaca parser, ditambah sheet
'Well Info' (nama, section, tipe, block weight, casing shoe) dan 'Survey' opsional.
Baris "Calibrate" (koreksi DD) di sheet Drag/Torque opsional, posisinya sama dengan file roadmap.
Sheet 'Instructions' dan 'Example ...' diabaikan saat impor.

kind = "training"   : rencana WellPlan + data aktual (data acuan ML)
kind = "monitoring" : rencana WellPlan (+ aktual sejauh sudah dibor), hanya untuk prediction
"""

import io

import xlsxwriter

N_ROWS = 300  # baris isian per tabel
FFS = [0.1, 0.3, 0.5]
SECTIONS = ["26", "22", "17.5", "12.25", "8.5", "6.125"]

# Contoh kecil (sintetis, satuan imperial) untuk sheet Example
EX_MD = [3000, 4000, 5000, 6000, 7000]
EX_PU = {
    0.1: [110, 128, 146, 165, 183],
    0.3: [118, 140, 163, 187, 211],
    0.5: [127, 153, 181, 211, 241],
}
EX_SO = {0.1: [100, 114, 128, 141, 154], 0.3: [93, 104, 113, 121, 128], 0.5: [86, 94, 99, 102, 104]}
EX_ROT = [105, 121, 137, 153, 168]
EX_TON = {
    0.1: [4100, 4800, 5500, 6300, 7000],
    0.3: [5200, 6600, 8000, 9500, 10900],
    0.5: [6300, 8400, 10500, 12700, 14800],
}
EX_TOFF = {
    0.1: [1100, 1800, 2500, 3300, 4000],
    0.3: [2200, 3600, 5000, 6500, 7900],
    0.5: [3300, 5400, 7500, 9700, 11800],
}
EX_ACT = [
    (3093, 121, 97, 108, 2100, 4900),
    (3280, 125, 99, 111, 2400, 5300),
    (3466, 130, 101, 115, 2700, 5600),
    (3652, 134, 103, 118, 3000, 6000),
    (3838, 138, 105, 121, 3300, 6400),
]


def build_template(kind: str) -> bytes:
    with_actual = kind in ("training", "data-latih")
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    F = {
        "title": wb.add_format({"bold": True, "font_size": 14}),
        "bold": wb.add_format({"bold": True}),
        "head": wb.add_format(
            {"bold": True, "bg_color": "#eaeef2", "border": 1, "text_wrap": True, "valign": "top"}
        ),
        "ff": wb.add_format(
            {"italic": True, "bg_color": "#f4f4f2", "border": 1, "font_color": "#52514e"}
        ),
        "unit": wb.add_format(
            {"bg_color": "#f4f4f2", "border": 1, "font_color": "#52514e", "align": "center"}
        ),
        "input": wb.add_format({"bg_color": "#fffbe6", "border": 1, "border_color": "#e2e1dc"}),
        "label": wb.add_format({"bold": True, "border": 1, "bg_color": "#eaeef2"}),
        "wrap": wb.add_format({"text_wrap": True, "valign": "top"}),
        "muted": wb.add_format({"font_color": "#52514e", "italic": True}),
    }
    _instructions(wb, F, with_actual)
    _info(wb, F)
    _drag(wb, F, example=False)
    _torque(wb, F, example=False)
    if with_actual:
        _actual(wb, F, example=False)
    _survey(wb, F)
    _examples(wb, F, with_actual)
    wb.close()
    return buf.getvalue()


def _instructions(wb, F, with_actual: bool) -> None:
    ws = wb.add_worksheet("Instructions")
    ws.set_column(0, 0, 4)
    ws.set_column(1, 1, 110)
    title = (
        "Training data template (WellPlan T&D model + actual field data)"
        if with_actual
        else "Monitoring well template (WellPlan T&D model, for predicting)"
    )
    ws.write(0, 1, title, F["title"])
    steps = [
        'One file = one well section (e.g. 8.5" section). Use a separate file for each section.',
        "Fill in sheet 'Well Info': well name, well section, well type (J / S / Horizontal), "
        "block weight. Casing shoe and mud weight are optional.",
        "Fill in sheet 'Drag': depth (ft) in column 'Run Measured Depth', then hookload (kip = 1000 lbf) "
        "for Tripping In (slack off), Tripping Out (pick up) and Rotating Off Bottom (rotating weight) "
        "for each open hole friction factor (OHFF). The OHFF value in the second header row may be "
        "changed (e.g. 0.30 / 0.40 / 0.50); include OHFF 0.30 and 0.50.",
        "Fill in sheet 'Torque': depth (ft), Rotating On Bottom and Rotating Off Bottom torque (ft-lbf) "
        "for each OHFF.",
        "Optional: the DD 'Calibrate' offsets at the top of 'Drag' (PICK UP / SLACK OFF / ROTATE, klbf) "
        "and 'Torque' (On Bot / Off Bot, ft-lbf). Leave empty or 0 when there is no calibration.",
    ]
    if with_actual:
        steps.append(
            "Fill in sheet 'T&D Actual Reading': field readings per depth (ft): pick up, slack off, "
            "rotating weight (Klbs), torque off/on bottom (Lbs-ft). Leave a cell empty if it was not read. "
            "At least 8 depths inside the WellPlan depth range are needed to use the well for training."
        )
    else:
        steps.append(
            "Actual readings are not required. If the well is already being drilled, add a sheet "
            "'T&D Actual Reading' (same layout as the training template) to compare and predict ahead."
        )
    steps += [
        "Sheet 'Survey' is optional (MD ft, inclination, azimuth, DLS deg/100ft). It improves the prediction.",
        "Numbers only (dot as decimal separator); do not rename headers or insert columns. "
        "Empty rows are ignored.",
        "See the 'Example ...' sheets for a filled-in example. 'Instructions' and 'Example ...' sheets "
        "are not imported.",
        "Save as .xlsx and upload in the application: "
        + (
            "Training Data -> Upload. Select the well section and well type first."
            if with_actual
            else "Monitoring -> Upload. Select the well section and well type first. The system imports "
            "the file, predicts with the active model and shows the result (dashboard, Excel, PDF)."
        ),
    ]
    for i, t in enumerate(steps, start=2):
        ws.write(i, 0, f"{i - 1}.", F["bold"])
        ws.write(i, 1, t, F["wrap"])
        ws.set_row(i, 32)
    ws.activate()


def _info(wb, F) -> None:
    ws = wb.add_worksheet("Well Info")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 28)
    ws.set_column(2, 2, 60)
    ws.write(0, 0, "Well Info", F["title"])
    rows = [
        ("Well name", "", "Required. Well code, e.g. P_MINA25_0025"),
        ("Well section (in)", "", "Required. One of: 26, 22, 17.5, 12.25, 8.5, 6.125"),
        ("Well type", "", "Required. One of: J, S, Horizontal"),
        ("Block weight (klbf)", "", "Recommended. Block weight (Klbs)"),
        (
            "Casing shoe of previous section (ft)",
            "",
            "Optional. Shoe depth; if empty the top of the plan is used",
        ),
        ("Mud weight (ppg)", "", "Optional"),
        ("Field", "", "Optional"),
    ]
    for i, (lab, val, note) in enumerate(rows, start=2):
        ws.write(i, 0, lab, F["label"])
        ws.write(i, 1, val, F["input"])
        ws.write(i, 2, note, F["muted"])
    ws.data_validation(3, 1, 3, 1, {"validate": "list", "source": SECTIONS})
    ws.data_validation(4, 1, 4, 1, {"validate": "list", "source": ["J", "S", "Horizontal"]})
    for r in (5, 6, 7):
        ws.data_validation(
            r,
            1,
            r,
            1,
            {
                "validate": "decimal",
                "criteria": ">=",
                "value": 0,
                "error_message": "Enter a number >= 0",
            },
        )


def _number_validation(ws, r0, c0, r1, c1) -> None:
    ws.data_validation(
        r0,
        c0,
        r1,
        c1,
        {
            "validate": "decimal",
            "criteria": "between",
            "minimum": -1e6,
            "maximum": 1e7,
            "error_title": "Not a number",
            "error_message": "Enter a number (dot as decimal separator).",
        },
    )


def _blocks(
    ws, F, ops: list[str], units: list[str], first_row: int, data: list[list] | None
) -> None:
    """Header: baris operasi ('... using:'), baris FF, baris satuan. Satu blok per FF."""
    h, f, u = first_row, first_row + 1, first_row + 2
    col = 0
    for b, ff in enumerate(FFS):
        cols = ["Run Measured Depth using:"] + ops
        for j, name in enumerate(cols):
            ws.write(h, col + j, name, F["head"])
            ws.write(f, col + j, f"open hole friction factor: {ff:.2f}", F["ff"])
            ws.write(u, col + j, units[j], F["unit"])
            ws.set_column(col + j, col + j, 17, F["input"] if data is None else None)
        if data is not None:
            for i, row in enumerate(data[b]):
                ws.write_row(u + 1 + i, col, row)
        _number_validation(ws, u + 1, col, u + N_ROWS, col + len(cols) - 1)
        col += len(cols) + 1
    ws.set_row(h, 30)
    ws.freeze_panes(u + 1, 0)


def _drag(wb, F, example: bool, name: str = "Drag") -> None:
    ws = wb.add_worksheet(name)
    # baris 1-2: offset Calibrate DD (opsional), posisi sama dengan file roadmap client
    ws.write_row(0, 0, ["Calibrate", None, "PICK UP", "SLACK OFF", "ROTATE"], F["label"])
    ws.write_row(1, 2, [0, 0, 0] if example else ["", "", ""], F["input"])
    ws.write(
        2,
        0,
        "WellPlan Result - Drag (hookload). Hookload in kip (1000 lbf), depth in ft. Calibrate = "
        "optional DD offsets (klbf). The OHFF value in the 'open hole friction factor' row may be changed.",
        F["muted"],
    )
    data = None
    if example:
        data = [
            [[EX_MD[i], EX_SO[ff][i], EX_PU[ff][i], EX_ROT[i]] for i in range(len(EX_MD))]
            for ff in FFS
        ]
    _blocks(
        ws,
        F,
        ["Tripping In using:", "Tripping Out using:", "Rotating Off Bottom using:"],
        ["(ft)", "(kip)", "(kip)", "(kip)"],
        3,
        data,
    )


def _torque(wb, F, example: bool, name: str = "Torque") -> None:
    ws = wb.add_worksheet(name)
    ws.write(0, 0, "WellPlan Result - Torque", F["bold"])
    # offset Calibrate DD (opsional) di kolom C, posisi sama dengan file roadmap client
    ws.write(1, 0, "Calibrate On Bot Torque", F["label"])
    ws.write(2, 0, "Calibrate Off Bot Torque", F["label"])
    ws.write(1, 2, 0 if example else "", F["input"])
    ws.write(2, 2, 0 if example else "", F["input"])
    ws.write(
        1, 4, "Torque in ft-lbf, depth in ft. Calibrate = optional DD offsets (ft-lbf).", F["muted"]
    )
    data = None
    if example:
        data = [
            [[EX_MD[i], EX_TON[ff][i], EX_TOFF[ff][i]] for i in range(len(EX_MD))] for ff in FFS
        ]
    _blocks(
        ws,
        F,
        ["Rotating On Bottom using:", "Rotating Off Bottom using:"],
        ["(ft)", "(ft-lbf)", "(ft-lbf)"],
        4,
        data,
    )


def _actual(wb, F, example: bool, name: str = "T&D Actual Reading") -> None:
    ws = wb.add_worksheet(name)
    ws.write(0, 0, "T&D Actual Reading - field readings", F["bold"])
    ws.write(1, 0, "Leave a cell empty if it was not read. Units: ft, Klbs, Lbs-ft.", F["muted"])
    head = [
        "Depth (ft)",
        "Actual Pick Up Weight (Klbs)",
        "Actual Slack Off Weight (Klbs)",
        "Actual Rotating Weight Run (Klbs)",
        "Actual torque off bottom Run (Lbs-ft)",
        "Actual torque on bottom Run (Lbs-ft)",
    ]
    for j, t in enumerate(head):
        ws.write(3, j, t, F["head"])
        ws.set_column(j, j, 20, None if example else F["input"])
    ws.set_row(3, 32)
    if example:
        for i, row in enumerate(EX_ACT):
            ws.write_row(4 + i, 0, row)
    _number_validation(ws, 4, 0, 4 + N_ROWS, len(head) - 1)
    ws.freeze_panes(4, 0)


def _survey(wb, F, example: bool = False, name: str = "Survey") -> None:
    ws = wb.add_worksheet(name)
    ws.write(0, 0, "Survey (optional)", F["bold"])
    ws.write(1, 0, "Leave empty if not available.", F["muted"])
    for j, (t, u) in enumerate(
        (
            ("Measured Depth", "ft"),
            ("Inclination", "deg"),
            ("Azimuth", "deg"),
            ("Dog-Leg Severity", "deg/100ft"),
        )
    ):
        ws.write(2, j, t, F["head"])
        ws.write(3, j, u, F["unit"])
        ws.set_column(j, j, 18, None if example else F["input"])
    if example:
        for i, (md, inc) in enumerate(
            [(0, 0), (1000, 0), (2000, 12), (3000, 28), (4000, 30), (7000, 30)]
        ):
            ws.write_row(4 + i, 0, [md, inc, 145, 0 if i < 2 else 1.5])
    _number_validation(ws, 4, 0, 4 + N_ROWS, 3)
    ws.freeze_panes(4, 0)


def _examples(wb, F, with_actual: bool) -> None:
    ws = wb.add_worksheet("Example")
    ws.set_column(0, 0, 100)
    ws.write(
        0,
        0,
        "Filled-in example (synthetic data). 'Example ...' sheets are not imported.",
        F["title"],
    )
    ws.write(
        2,
        0,
        "Well Info: Well name = EXAMPLE-01, Well section = 8.5, Well type = J, Block weight = 20, "
        "Casing shoe = 2800, Mud weight = 9.2",
        F["wrap"],
    )
    ws.write(
        3,
        0,
        "See sheets 'Example Drag', 'Example Torque'"
        + (", 'Example T&D'" if with_actual else "")
        + ", 'Example Survey'.",
        F["wrap"],
    )
    _drag(wb, F, example=True, name="Example Drag")
    _torque(wb, F, example=True, name="Example Torque")
    if with_actual:
        _actual(wb, F, example=True, name="Example T&D")
    _survey(wb, F, example=True, name="Example Survey")
