"""Template Excel untuk diisi pengguna lalu diunggah.

Struktur sheet sama dengan format A (roadmap) yang dibaca parser, ditambah sheet
'Info Sumur' (nama, section, tipe, block weight, casing shoe) dan 'Survey' opsional.
Sheet 'Petunjuk' dan 'Contoh' diabaikan saat impor.

kind = "data-latih" : rencana WellPlan + data aktual (untuk melatih model)
kind = "sumur-baru" : rencana WellPlan saja (untuk prediksi)
"""

import io

import xlsxwriter

N_ROWS = 300  # baris isian per tabel
FFS = [0.1, 0.3, 0.5]
SECTIONS = ["26", "22", "17.5", "12.25", "8.5", "6.125"]

# Contoh kecil (sintetis, satuan imperial) untuk sheet Contoh
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
    with_actual = kind == "data-latih"
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
    _petunjuk(wb, F, with_actual)
    _info(wb, F)
    _drag(wb, F, example=False)
    _torque(wb, F, example=False)
    if with_actual:
        _actual(wb, F, example=False)
    _survey(wb, F)
    _contoh(wb, F, with_actual)
    wb.close()
    return buf.getvalue()


def _petunjuk(wb, F, with_actual: bool) -> None:
    ws = wb.add_worksheet("Petunjuk")
    ws.set_column(0, 0, 4)
    ws.set_column(1, 1, 110)
    title = (
        "Template data latih (rencana WellPlan + data aktual)"
        if with_actual
        else "Template sumur baru (rencana WellPlan, untuk prediksi)"
    )
    ws.write(0, 1, title, F["title"])
    steps = [
        'Satu file = satu section sumur (mis. section 8,5"). Buat file terpisah untuk section lain.',
        "Isi sheet 'Info Sumur': nama sumur, section, tipe sumur (J / S / Horizontal), block weight. "
        "Casing shoe dan mud weight opsional.",
        "Isi sheet 'Drag': kedalaman (ft) di kolom 'Run Measured Depth', lalu hookload (kip = 1000 lbf) "
        "Tripping In (slack off), Tripping Out (pick up), Rotating Off Bottom (rotating weight) untuk "
        "setiap skenario friction factor. Nilai FF di baris kedua boleh diubah (mis. 0.30/0.40/0.50); "
        "sertakan FF 0.30 dan 0.50.",
        "Isi sheet 'Torque': kedalaman (ft), torque Rotating On Bottom dan Rotating Off Bottom (ft-lbf) per FF.",
    ]
    if with_actual:
        steps.append(
            "Isi sheet 'T&D Actual Reading': pembacaan lapangan per kedalaman (ft): pick up, slack off, "
            "rotating weight (Klbs), torque off/on bottom (Lbs-ft). Sel boleh kosong bila tidak dibaca. "
            "Minimal 8 kedalaman di dalam rentang kedalaman WellPlan agar dipakai melatih model."
        )
    steps += [
        "Sheet 'Survey' opsional (MD ft, inklinasi, azimuth, DLS deg/100ft). Bila diisi, prediksi lebih baik.",
        "Angka saja (titik sebagai desimal), jangan ubah judul kolom, jangan sisipkan kolom. Baris kosong diabaikan.",
        "Lihat sheet 'Contoh' untuk contoh isian. Sheet 'Petunjuk' dan 'Contoh' tidak ikut diimpor.",
        "Simpan sebagai .xlsx lalu unggah di aplikasi: "
        + (
            "Data sumur -> Impor file Excel."
            if with_actual
            else "Data sumur -> Prediksi sumur baru. Sistem mengimpor, memprediksi dengan model aktif, "
            "lalu menampilkan hasil (dashboard, Excel, PDF)."
        ),
    ]
    for i, t in enumerate(steps, start=2):
        ws.write(i, 0, f"{i - 1}.", F["bold"])
        ws.write(i, 1, t, F["wrap"])
        ws.set_row(i, 32)
    ws.activate()


def _info(wb, F) -> None:
    ws = wb.add_worksheet("Info Sumur")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 28)
    ws.set_column(2, 2, 60)
    ws.write(0, 0, "Info Sumur", F["title"])
    rows = [
        ("Nama sumur", "", "Wajib. Kode sumur, mis. P_MINA25_0025"),
        ("Section (inci)", "", "Wajib. Pilih: 26, 22, 17.5, 12.25, 8.5, 6.125"),
        ("Tipe sumur", "", "Wajib. Pilih: J, S, Horizontal"),
        ("Block weight (klbf)", "", "Disarankan. Berat blok (Klbs)"),
        (
            "Casing shoe section sebelumnya (ft)",
            "",
            "Opsional. Kedalaman shoe; bila kosong dipakai puncak rencana",
        ),
        ("Mud weight (ppg)", "", "Opsional"),
        ("Lapangan", "", "Opsional"),
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
                "error_message": "Isi angka >= 0",
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
            "error_title": "Bukan angka",
            "error_message": "Isi angka (titik sebagai desimal).",
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
    ws.write(0, 0, "WellPlan Result - Drag (hookload)", F["bold"])
    ws.write(
        1,
        0,
        "Hookload dalam kip (1000 lbf), kedalaman dalam ft. Nilai FF di baris 'open hole friction "
        "factor' boleh diubah.",
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
    ws.write(1, 0, "Torsi dalam ft-lbf, kedalaman dalam ft.", F["muted"])
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
    ws.write(0, 0, "T&D Actual Reading - pembacaan lapangan", F["bold"])
    ws.write(1, 0, "Sel boleh kosong bila tidak dibaca. Satuan: ft, Klbs, Lbs-ft.", F["muted"])
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
    ws.write(0, 0, "Survey (opsional)", F["bold"])
    ws.write(1, 0, "Kosongkan bila tidak ada.", F["muted"])
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


def _contoh(wb, F, with_actual: bool) -> None:
    ws = wb.add_worksheet("Contoh")
    ws.set_column(0, 0, 100)
    ws.write(
        0, 0, "Contoh isian (data sintetis). Sheet 'Contoh ...' tidak ikut diimpor.", F["title"]
    )
    ws.write(
        2,
        0,
        "Info Sumur: Nama sumur = CONTOH-01, Section = 8.5, Tipe = J, Block weight = 20, "
        "Casing shoe = 2800, Mud weight = 9.2",
        F["wrap"],
    )
    ws.write(
        3,
        0,
        "Lihat sheet 'Contoh Drag', 'Contoh Torque'"
        + (", 'Contoh T&D'" if with_actual else "")
        + ", 'Contoh Survey'.",
        F["wrap"],
    )
    _drag(wb, F, example=True, name="Contoh Drag")
    _torque(wb, F, example=True, name="Contoh Torque")
    if with_actual:
        _actual(wb, F, example=True, name="Contoh T&D")
    _survey(wb, F, example=True, name="Contoh Survey")
