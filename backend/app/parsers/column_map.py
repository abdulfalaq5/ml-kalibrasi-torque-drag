"""Pola nama sheet dan kolom (regex, huruf kecil) untuk dua format file client.

Diturunkan dari audit 94 file di folder Training (Okt 2026), lihat docs/keputusan.md K-17.

Format A, "roadmap" (.xlsx): Drag, Torque, T&D Actual Reading, Casing Shoe
Format B, "laporan WellPlan" (.xlsm): Summary, Tripping Load Analysis,
    Off Bottom Torque analysis, Rotary Drill Buckling Outputs, Survey Outputs,
    Drilling Data, Tripping  Data (+ sheet plot yang diabaikan)
"""

# ---------------------------------------------------------------- deteksi format
ROADMAP_SHEETS = {"drag", "torque"}
WELLPLAN_SHEETS = {"summary", "tripping load analysis"}

# ---------------------------------------------------------------- Format A
# Sheet Drag: header operasi di baris yang memuat "Run Measured Depth", baris di bawahnya
# "open hole friction factor: 0.30". Blok "Graph reference" (kurva + offset kalibrasi)
# diabaikan.
ROADMAP_DEPTH_HEADER = r"^run measured depth"
ROADMAP_GRAPH_REF = r"graph reference"
ROADMAP_DRAG_OPS = {
    "pick_up": [r"^tripping out"],
    "slack_off": [r"^tripping in"],
    "rotating_weight": [r"^rotating off bottom"],
}
ROADMAP_TORQUE_OPS = {
    "torque_on_bottom": [r"^rotating on bottom"],
    "torque_off_bottom": [r"^rotating off bottom"],
}
FF_OPEN_HOLE = r"open hole friction factor\s*:?\s*(\d*[.,]\d+|\d+)"
FF_CASED_HOLE = r"cased hole friction factor\s*:?\s*(\d*[.,]\d+|\d+)"

ACTUAL_SHEET = r"t\s*&\s*d actual reading"
ACTUAL_COLS = {
    "pick_up": [r"pick ?up"],
    "slack_off": [r"slack ?off"],
    "rotating_weight": [r"rotating weight"],
    "torque_off_bottom": [r"torque off bottom", r"off[ -]?b(o)?tt?o?m torque"],
    "torque_on_bottom": [r"torque on bottom", r"on[ -]?b(o)?tt?o?m torque"],
}
ACTUAL_IGNORE = [r"differential", r"\bho\b", r"delta"]
ACTUAL_META = {
    "well_name": r"^well\s*:?\s*(.*)$",
    "block_weight": r"block weight",
    "section_meta": r"^section\s*:?$",
    "run": r"^run\s*:?$",
}

# ---------------------------------------------------------------- Format B
WP_TRIPPING = r"^tripping load analysis"
WP_OFFBTM = r"^off bottom torque"
WP_ROTARY = r"^rotary drill buckling"
WP_SURVEY = r"^survey outputs?"
WP_DRILLING = r"^drilling data"
WP_TRIPDATA = r"^tripping\s+data"
WP_FF_SET = r"csg\s*(\d*[.,]?\d+)\s*oph\s*(\d*[.,]?\d+)"

DRILLING_COLS = {
    "slack_off": [r"^slack ?off"],
    "rotating_weight": [r"^rotating weight"],
    "pick_up": [r"^pick ?/?\s*up"],
    "torque_off_bottom": [r"^off[ -]?btm torque", r"^off[ -]?bottom torque"],
    "torque_on_bottom": [r"^on[ -]?btm torque", r"^on[ -]?bottom torque"],
}

SUMMARY_KEYS = {
    "well_name": r"^well\s*:$",
    "field": r"^field\s*:$",
    "client": r"^client\s*:$",
    "rig": r"^rig\s*:$",
    "block_weight": r"^block weight\s*:$",
    "mud_weight": r"mud weight\s*:$",
    "bit_depth_range": r"^drilling bit depth range\s*:$",
}

# Folder tipe sumur pada impor massal (Training/<tipe>/<sumur>/file)
TYPE_FOLDERS = {
    "j": "J",
    "s": "S",
    "horizontal": "Horizontal",
    "hz": "Horizontal",
    "hw": "Horizontal",
}
