"""Gerbang kualitas: kasus sederhana yang ditanam langsung ke database."""

from app.db.models import ActualReading, PlanResult, Well
from app.services import units
from app.services.quality import effective_status, evaluate_well


def _well(db, name, actual_rows, plan_scale=1.0):
    w = Well(name=name, section_in=8.5, well_type="J", meta={})
    db.add(w)
    db.flush()
    for d in range(1000, 5001, 500):
        for op, base in (
            ("pick_up", 100),
            ("slack_off", 80),
            ("rotating_weight", 90),
            ("torque_off_bottom", 3000),
            ("torque_on_bottom", 5000),
        ):
            unit = "ft-lbf" if op.startswith("torque") else "klbf"
            v = base * plan_scale * (1 + d / 10000)
            db.add(
                PlanResult(
                    well_id=w.id,
                    operation=op,
                    ff=0.3,
                    source_sheet="Drag",
                    depth_m=d * 0.3048,
                    value=v,
                    unit=unit,
                    value_si=units.to_si(v, unit),
                )
            )
    for d, pu, so, rot in actual_rows:
        for op, v in (("pick_up", pu), ("slack_off", so), ("rotating_weight", rot)):
            db.add(
                ActualReading(
                    well_id=w.id,
                    operation=op,
                    source_sheet="T&D Actual Reading",
                    depth_m=d * 0.3048,
                    value=v,
                    unit="klbf",
                    value_si=units.to_si(v, "klbf"),
                )
            )
    db.commit()
    return w


def test_good_well_is_A(db):
    rows = [
        (d, 100 * (1 + d / 10000) + 3, 80 * (1 + d / 10000), 90 * (1 + d / 10000) + 1)
        for d in range(1100, 5000, 300)
    ]
    wq = evaluate_well(db, _well(db, "QA-BAIK", rows))
    assert wq.status in ("A", "B"), wq.checks
    assert not [c for c in wq.checks if c["level"] == "critical"]


def test_few_points_is_C(db):
    rows = [(d, 110, 85, 95) for d in (1500, 2000, 2500)]
    wq = evaluate_well(db, _well(db, "QA-SEDIKIT", rows))
    assert wq.status == "C"
    assert any(c["code"] == "K6" and c["level"] == "critical" for c in wq.checks)


def test_order_violation_is_C(db):
    # slack off > pick up di semua titik
    rows = [(d, 80, 120, 100) for d in range(1100, 5000, 300)]
    wq = evaluate_well(db, _well(db, "QA-URUTAN", rows))
    assert wq.status == "C"
    assert any(c["code"] == "K5" and c["level"] == "critical" for c in wq.checks)


def test_unit_error_is_C(db):
    # aktual dalam lbf padahal tertulis klbf -> rasio ~1000
    rows = [(d, 110_000, 85_000, 95_000) for d in range(1100, 5000, 300)]
    wq = evaluate_well(db, _well(db, "QA-SATUAN", rows))
    assert wq.status == "C"


def test_review_overrides(db):
    class Q:
        status = "C"

    class R:
        def __init__(self, d):
            self.decision = d

    assert effective_status(Q(), None) == "C"
    assert effective_status(Q(), R("accept")) == "B"
    assert effective_status(Q(), R("exclude")) == "X"
    assert effective_status(Q(), R("fix")) == "C"
