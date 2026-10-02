"""Pola nama sheet dan kolom (regex, huruf kecil).

ASUMSI awal berdasarkan nama sheet di dokumen proyek. Sesuaikan setelah audit
data (scripts/audit_files.py) dan catat perubahan di docs/keputusan.md.
"""

SHEET_ROLES: dict[str, list[str]] = {
    # Laporan WellPlan
    "summary": [r"^summary$", r"^ringkasan"],
    "tripping": [r"tripping load", r"^tripping analysis"],
    "off_bottom_torque": [r"off[ -]?bottom torque", r"^torque analysis"],
    "survey": [r"survey output", r"^survey$", r"^surveys?$"],
    "bha": [r"^bha", r"bottom hole assembly"],
    # Roadmap
    "roadmap_drag": [r"^drag$", r"^drag roadmap", r"^hookload roadmap"],
    "roadmap_torque": [r"^torque$", r"^torque roadmap"],
    # Data aktual
    "actual_td": [r"t\s*&\s*d actual", r"t&d actual", r"actual reading", r"td actual"],
    "actual_drilling": [r"^drilling data"],
    "actual_tripping": [r"^tripping data"],
}

PLAN_ROLES = {"tripping", "off_bottom_torque", "roadmap_drag", "roadmap_torque"}
ACTUAL_ROLES = {"actual_td", "actual_drilling", "actual_tripping"}
WELLPLAN_ROLES = {"summary", "tripping", "off_bottom_torque", "survey", "bha"}
ROADMAP_ROLES = {"roadmap_drag", "roadmap_torque"}

# Satuan bawaan bila header kolom tidak mencantumkan satuan (memunculkan peringatan)
SHEET_DEFAULT_UNIT = {
    "tripping": "klbf",
    "roadmap_drag": "klbf",
    "off_bottom_torque": "ft-lbf",
    "roadmap_torque": "ft-lbf",
}
# Operasi torsi bawaan bila header tidak menyebut on/off bottom
SHEET_DEFAULT_TORQUE_OP = {
    "off_bottom_torque": "torque_off_bottom",
    "roadmap_torque": "torque_off_bottom",
    "actual_drilling": "torque_on_bottom",
}

DEPTH_PATTERNS = [
    r"^measured depth",
    r"^md\b",
    r"^depth\b",
    r"^bit depth",
    r"^kedalaman",
    r"^hole depth",
]

FF_PATTERNS = [
    r"\bff\s*[=:]?\s*(\d*[.,]\d+)",
    r"\bcof\s*[=:]?\s*(\d*[.,]\d+)",
    r"friction factor\s*[=:]?\s*(\d*[.,]\d+)",
    r"\bfriction\s*[=:]?\s*(\d*[.,]\d+)",
]

HOOKLOAD_OP_PATTERNS = {
    "pick_up": [r"pick[ -]?up", r"tripping out", r"trip out", r"\bpooh\b", r"\bp/u\b", r"\bpuw?\b"],
    "slack_off": [
        r"slack[ -]?off",
        r"tripping in",
        r"trip in",
        r"\brih\b",
        r"\bs/o\b",
        r"\bsow?\b",
    ],
    "rotating_weight": [r"rotating", r"\brot\.?\s*w", r"\brob\b", r"\brotw\b", r"free rotating"],
}

TORQUE_OP_PATTERNS = {
    "torque_on_bottom": [r"on[ -]?bottom", r"\bdrilling torque\b", r"\btob\b"],
    "torque_off_bottom": [r"off[ -]?bottom", r"\btorque off\b", r"\btoffb\b"],
}

# Kolom survey
SURVEY_COLUMNS = {
    "md": [r"^measured depth", r"^md\b", r"^depth\b"],
    "inc": [r"^inc", r"inclination", r"^inklinasi"],
    "azi": [r"^azi", r"azimuth"],
    "tvd": [r"^tvd\b", r"true vertical"],
    "dls": [r"^dls\b", r"dog ?leg", r"^dogleg"],
}

# Kunci di sheet Summary (kolom label -> nilai di sel sebelah kanan)
SUMMARY_KEYS = {
    "well_name": [r"^well( name)?\s*:?$", r"^nama sumur", r"^wellbore( name)?\s*:?$"],
    "field": [r"^field\s*:?$", r"^lapangan"],
    "hole_size": [r"^hole (size|diameter)", r"^open hole (size|diameter)", r"^ukuran lubang"],
    "bit_size": [r"^bit size", r"^bit diameter"],
    "section": [r"^section\s*:?$", r"^hole section"],
    "well_type": [r"^well (type|profile)", r"^tipe sumur"],
    "casing_shoe": [r"^casing shoe", r"^shoe depth", r"^previous casing"],
}

# Kolom arah pada sheet Tripping Data aktual (bila satu kolom hookload + kolom arah)
DIRECTION_PATTERNS = [r"^direction", r"^arah", r"^trip direction", r"^operation"]
DIRECTION_VALUES = {
    "pick_up": [r"pooh", r"out", r"pick", r"cabut", r"\bpu\b"],
    "slack_off": [r"rih", r"\bin\b", r"slack", r"masuk", r"\bso\b"],
}
HOOKLOAD_GENERIC = [r"hook ?load", r"\bhkld\b", r"\bweight\b"]
