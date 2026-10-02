"""Selisih dihitung benar (tanda dan besar) pada 3 titik yang dicek manual."""

import pytest
from app.db.models import (
    ActualReading,
    MLModel,
    PlanResult,
    Prediction,
    PredictionPoint,
    Well,
)
from app.services import units
from app.services.profile import well_profile
from sqlalchemy import update


@pytest.fixture
def tiny_well(db):
    db.execute(update(MLModel).values(active=False))
    w = Well(name="CEK", section_in=8.5, well_type="J", meta={})
    m = MLModel(algorithm="uji", status="selesai", active=True, path=None)
    db.add_all([w, m])
    db.flush()
    # WellPlan FF 0.3 (klbf): 100 ft -> 100, 200 ft -> 110, 300 ft -> 120
    for d, v in [(100, 100.0), (200, 110.0), (300, 120.0)]:
        db.add(
            PlanResult(
                well_id=w.id,
                operation="pick_up",
                ff=0.3,
                source_sheet="Tripping Load Analysis",
                depth_m=units.to_si(d, "ft"),
                value=v,
                unit="klbf",
                value_si=units.to_si(v, "klbf"),
            )
        )
    # Aktual: 100 ft = 95 (WP lebih tinggi 5), 200 ft = 115 (WP lebih rendah 5), 300 ft = 120
    for d, v in [(100, 95.0), (200, 115.0), (300, 120.0)]:
        db.add(
            ActualReading(
                well_id=w.id,
                operation="pick_up",
                source_sheet="T&D Actual Reading",
                depth_m=units.to_si(d, "ft"),
                value=v,
                unit="klbf",
                value_si=units.to_si(v, "klbf"),
            )
        )
    p = Prediction(well_id=w.id, model_id=m.id, kind="full", warnings=[])
    db.add(p)
    db.flush()
    # ML: 100 ft = 97, 200 ft = 113, 300 ft = 126
    for d, v in [(100, 97.0), (200, 113.0), (300, 126.0)]:
        db.add(
            PredictionPoint(
                prediction_id=p.id,
                operation="pick_up",
                depth_m=units.to_si(d, "ft"),
                wellplan_si=None,
                ml_si=units.to_si(v, "klbf"),
            )
        )
    db.commit()
    yield w
    db.delete(w)
    db.delete(m)
    db.commit()


def test_three_manual_points(db, tiny_well):
    prof = well_profile(db, tiny_well, "imperial")
    d = prof["operations"]["pick_up"]["diff"]

    wa = dict(zip(d["wp_minus_actual"]["depth"], d["wp_minus_actual"]["abs"], strict=True))
    assert wa[100.0] == pytest.approx(5.0, abs=1e-3)  # kanan: WP lebih tinggi
    assert wa[200.0] == pytest.approx(-5.0, abs=1e-3)  # kiri: WP lebih rendah
    assert wa[300.0] == pytest.approx(0.0, abs=1e-3)

    ma = dict(zip(d["ml_minus_actual"]["depth"], d["ml_minus_actual"]["abs"], strict=True))
    assert ma[100.0] == pytest.approx(2.0, abs=1e-3)
    assert ma[200.0] == pytest.approx(-2.0, abs=1e-3)
    assert ma[300.0] == pytest.approx(6.0, abs=1e-3)
    pct = dict(zip(d["ml_minus_actual"]["depth"], d["ml_minus_actual"]["pct"], strict=True))
    assert pct[300.0] == pytest.approx(5.0, abs=1e-2)  # 6 / 120

    mw = dict(zip(d["ml_minus_wp"]["depth"], d["ml_minus_wp"]["abs"], strict=True))
    assert mw[100.0] == pytest.approx(-3.0, abs=1e-3)
    assert mw[200.0] == pytest.approx(3.0, abs=1e-3)
    assert mw[300.0] == pytest.approx(6.0, abs=1e-3)

    m = prof["operations"]["pick_up"]["metrics"]
    # RMSE WellPlan = sqrt((25+25+0)/3) klbf
    assert m["wellplan"]["rmse"] == pytest.approx((50 / 3) ** 0.5, rel=1e-4)
