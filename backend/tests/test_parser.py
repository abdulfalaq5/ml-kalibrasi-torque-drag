"""Parser vs angka di Excel asli (5 titik dicek manual dari file contoh)."""

import pytest
from app.parsers.workbook import parse_workbook
from openpyxl import Workbook

from tests.conftest import FIXTURES


def _find(rows, op, depth, ff=None, sheet=None):
    hits = [
        r
        for r in rows
        if r.operation == op
        and r.depth == depth
        and r.ff == ff
        and (sheet is None or r.sheet == sheet)
    ]
    assert len(hits) == 1, (op, depth, ff, hits)
    return hits[0]


def test_wellplan_with_actual_five_checkpoints():
    pw = parse_workbook(FIXTURES / "contoh1_wellplan_aktual.xlsx")
    assert pw.kinds == {"wellplan", "actual"}
    assert not pw.has_errors, pw.issues
    assert pw.meta["well_name"] == "W01"
    assert pw.meta["hole_size"] == 12.25

    # Titik cek manual (dibaca langsung dari sel Excel)
    r = _find(pw.plan, "pick_up", 2600, 0.3)
    assert (r.value, r.unit) == (114.15, "klbf")
    r = _find(pw.plan, "slack_off", 2600, 0.5)
    assert r.value == 102.03
    r = _find(pw.plan, "torque_off_bottom", 2600, 0.3)
    assert (r.value, r.unit) == (1268, "ft-lbf")
    r = _find(pw.actual, "pick_up", 3293, sheet="T&D Actual Reading")
    assert r.value == 130.11
    r = _find(pw.actual, "torque_on_bottom", 3293, sheet="T&D Actual Reading")
    assert r.value == 6886
    s = next(s for s in pw.survey if s.md == 2500)
    assert s.inc == 17.5

    ops_ff = {(r.operation, r.ff) for r in pw.plan}
    assert ("rotating_weight", None) in ops_ff
    assert {ff for op, ff in ops_ff if op == "pick_up"} == {0.1, 0.3, 0.5}
    # Tripping Data dengan kolom arah POOH/RIH
    assert any(r.sheet == "Tripping Data" and r.operation == "slack_off" for r in pw.actual)


def test_roadmap():
    pw = parse_workbook(FIXTURES / "contoh1_roadmap.xlsx")
    assert pw.kinds == {"roadmap"}
    assert not pw.has_errors
    assert {r.operation for r in pw.plan} == {
        "pick_up",
        "slack_off",
        "rotating_weight",
        "torque_off_bottom",
        "torque_on_bottom",
    }


def _save(tmp_path, sheets: dict[str, list[list]]):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    p = tmp_path / "uji.xlsx"
    wb.save(p)
    return p


def test_unknown_unit_is_error(tmp_path):
    p = _save(
        tmp_path, {"Tripping Load Analysis": [["MD (ft)", "Pick Up FF 0.3 (pisang)"], [100, 1]]}
    )
    pw = parse_workbook(p)
    assert pw.has_errors
    assert any("Satuan tidak dikenal" in i.message for i in pw.issues)


def test_missing_depth_header(tmp_path):
    p = _save(tmp_path, {"Tripping Load Analysis": [["Apa", "Pick Up FF 0.3 (kip)"], [1, 2]]})
    pw = parse_workbook(p)
    assert any("kedalaman" in i.message and i.level == "error" for i in pw.issues)


def test_no_recognized_sheets(tmp_path):
    p = _save(tmp_path, {"Lainnya": [["a", "b"]]})
    pw = parse_workbook(p)
    assert any("Tidak ada sheet yang dikenali" in i.message for i in pw.issues)


def test_not_excel(tmp_path):
    p = tmp_path / "palsu.xlsx"
    p.write_bytes(b"bukan excel")
    pw = parse_workbook(p)
    assert pw.has_errors


def test_warnings_unsorted_missing_unit_out_of_range(tmp_path):
    p = _save(
        tmp_path,
        {
            "Tripping Load Analysis": [
                ["Measured Depth (ft)", "Pick Up FF 0.3", "Slack Off FF 0,3 (kip)"],
                [200, 50, 40],
                [100, 45, 38],
                [300, 99999, 42],
            ]
        },
    )
    pw = parse_workbook(p)
    msgs = " | ".join(i.message for i in pw.issues)
    assert not pw.has_errors
    assert "tanpa satuan" in msgs
    assert "tidak naik" in msgs
    assert "di luar rentang wajar" in msgs
    # FF dengan desimal koma terbaca
    assert {r.ff for r in pw.plan if r.operation == "slack_off"} == {0.3}
    # titik 99999 kip dibuang
    assert not any(r.value == 99999 for r in pw.plan)


@pytest.mark.parametrize(
    "md,inc,expected",
    [
        ([0, 1000, 2000, 3000], [0, 30, 45, 45], "J"),
        ([0, 1000, 2000, 3000, 4000], [0, 30, 40, 20, 10], "S"),
        ([0, 1000, 2000, 3000], [0, 40, 85, 90], "Horizontal"),
        ([0, 1000, 2000, 3000], [0, 1, 2, 2], "J"),
    ],
)
def test_classify_well_type(md, inc, expected):
    from app.services.classify import classify_well_type

    assert classify_well_type(md, inc)[0] == expected


def test_classify_section():
    from app.services.classify import classify_section

    assert classify_section(12.25) == 12.25
    assert classify_section(8.375) == 8.5
    assert classify_section(None) is None
