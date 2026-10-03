"""Alur penuh paket 6 minggu dengan data sintetis berstruktur folder seperti data client:
pindai folder -> gerbang kualitas -> tinjauan -> bekukan dataset -> latih -> blind test ->
prediksi -> batas aman -> ekspor Excel/PDF -> evaluasi prediksi setelah data aktual masuk."""

import io
import os
import subprocess
import sys
import time

import openpyxl
import pytest
from app.db.models import MLModel, Prediction, Well
from app.services.training import _compare_and_activate, train
from make_sample_data import build_well, section_spec, well_specs, write_wellplan_file
from sqlalchemy import select

from tests.conftest import ROOT

SEED = 11


@pytest.fixture(scope="module")
def inbox(tmp_dir):
    path = tmp_dir / "inbox"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "make_sample_data.py"),
            "--out",
            str(path),
            "--wells",
            "9",
            "--new-wells",
            "1",
            "--seed",
            str(SEED),
        ],
        check=True,
        capture_output=True,
    )
    old = time.time() - 300
    for f in path.rglob("*.xls*"):
        os.utime(f, (old, old))
    return path


def test_upload_rejects_non_excel(auth_client, tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b")
    with p.open("rb") as fh:
        assert auth_client.post("/api/files", files={"file": (p.name, fh)}).status_code == 400


def test_full_pipeline(auth_client, db, inbox, tmp_dir):
    st = auth_client.get("/api/inbox/status").json()
    assert st["pending"] > 15 and st["wells"] == 10

    # --- impor massal (background task dijalankan sinkron oleh TestClient)
    r = auth_client.post("/api/inbox/scan")
    assert r.status_code == 200, r.text
    run = auth_client.get(f"/api/inbox/runs/{r.json()['id']}").json()
    assert run["status"] == "selesai", run
    assert run["counts"].get("ditolak", 0) == 0, run["files"]
    assert not list(inbox.rglob("*.xls*")), "file harus dipindah dari inbox"
    assert list((tmp_dir / "processed").rglob("*.xls*"))
    # idempoten: memindai lagi tidak menemukan file
    assert auth_client.post("/api/inbox/scan").status_code == 400

    # --- gerbang kualitas
    q = auth_client.get("/api/quality").json()
    by = {(x["well"], x["section_in"]): x for x in q}
    new = [x for x in q if "BARU" in x["well"]]
    assert new and all(x["status"] == "C" for x in new)  # tanpa data aktual -> ditahan
    assert sum(x["status"] in ("A", "B") for x in q) >= 15
    for x in q:
        assert x["well_type"] in ("J", "S", "Horizontal")  # dari folder tipe
    # tinjauan tercatat
    target = new[0]
    rv = auth_client.post(
        f"/api/quality/{target['well_id']}/review",
        json={"decision": "perbaiki", "reason": "minta data aktual ke client"},
    )
    assert rv.json()["status"] == "C"
    assert (
        auth_client.post(
            f"/api/quality/{target['well_id']}/review",
            json={"decision": "x", "reason": "tidak valid"},
        ).status_code
        == 400
    )
    xl = auth_client.get("/api/quality/report.xlsx")
    assert "Kualitas data" in openpyxl.load_workbook(io.BytesIO(xl.content)).sheetnames
    assert by  # noqa

    # --- bekukan dataset + blind test terkunci
    d = auth_client.post("/api/datasets/freeze").json()
    assert d["version"] == 1 and d["n_blind"] >= 1 and len(d["hash"]) == 64
    blind = auth_client.get("/api/datasets/blind").json()
    assert len(blind["wells"]) >= 1
    d2 = auth_client.post("/api/datasets/freeze").json()
    assert d2["version"] == 2 and d2["hash"] == d["hash"]  # data sama -> hash sama
    assert (
        auth_client.get("/api/datasets/blind").json()["wells"] == blind["wells"]
    )  # tetap terkunci

    # --- latih (sinkron agar deterministik)
    row = MLModel(algorithm="xgboost", status="antri")
    db.add(row)
    db.commit()
    train(db, row, "xgboost")
    assert row.status == "selesai" and row.active and row.dataset_id
    m = row.metrics
    assert m["dataset"]["wells_blind"] >= 1
    assert set(m["operations"]) >= {"pick_up", "slack_off"}
    op = m["operations"]["pick_up"]
    assert op["learning_curve"] and op["explain"]["features"] and op["strategy"]
    assert m["feature_selection"][0]["grup"] == "dasar"
    trained = set(m["dataset"]["train_combos"])
    assert trained
    # sumur blind tidak pernah punya prediksi out-of-fold
    oof_wells = {
        db.get(Well, wid).name
        for wid in db.scalars(
            select(Prediction.well_id).where(
                Prediction.kind == "oof", Prediction.model_id == row.id
            )
        )
    }
    assert oof_wells and not (oof_wells & set(blind["wells"]))

    # --- blind test sekali
    b = auth_client.post(f"/api/models/{row.id}/blind-test")
    assert b.status_code == 200, b.text
    assert set(b.json()["wells"]) == set(blind["wells"])
    assert auth_client.post(f"/api/models/{row.id}/blind-test").status_code == 400

    # --- laporan model
    assert auth_client.get(f"/api/models/{row.id}/report.pdf").content[:4] == b"%PDF"
    sheets = openpyxl.load_workbook(
        io.BytesIO(auth_client.get(f"/api/models/{row.id}/report.xlsx").content)
    ).sheetnames
    assert {"Ringkasan", "Kurva belajar", "Pentingnya fitur", "Blind test", "Dataset"} <= set(
        sheets
    )

    # --- prediksi sumur baru + batas aman
    w_new = db.get(Well, target["well_id"])
    p = auth_client.post(f"/api/wells/{w_new.id}/predict")
    assert p.status_code == 200, p.text
    lim = auth_client.post(
        "/api/limits",
        json={
            "operation": "pick_up",
            "value": 50,
            "unit_system": "imperial",
            "section_in": w_new.section_in,
            "note": "uji",
        },
    )
    assert lim.status_code == 200, lim.text
    prof = auth_client.get(f"/api/wells/{w_new.id}/profile").json()
    assert prof["prediction"]["kind"] == "full"
    pu = prof["operations"]["pick_up"]
    assert pu["ml"]["lo"] and pu["ml"]["hi"]
    assert pu["limits"] and pu["limits"][0]["cross_ml"] is not None  # 50 klbf pasti terlampaui
    assert prof["quality"]["status"] == "C"

    x = auth_client.get(f"/api/wells/{w_new.id}/export.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert {"Drag", "Torque", "T&D Actual Reading", "Grafik", "Batas aman"} <= set(wb.sheetnames)
    assert auth_client.get(f"/api/wells/{w_new.id}/report.pdf").content[:4] == b"%PDF"

    # --- evaluasi prediksi: data aktual sumur baru datang belakangan
    spec = well_specs(10, SEED)[9]
    data = build_well(section_spec(spec, w_new.section_in))
    from make_sample_data import _compute_plan

    _compute_plan(data, [0.2, 0.3, 0.4, 0.5])
    f = tmp_dir / f"P_{spec.name}_BHA_{w_new.section_in:g}in_TnD_aktual.xlsm"
    write_wellplan_file(data, f, include_actual=True)
    with f.open("rb") as fh:
        up = auth_client.post(
            "/api/files", files={"file": (f.name, fh)}, data={"well_name": w_new.name}
        )
    assert up.json()["status"] in ("ok", "peringatan"), up.json()
    evs = auth_client.get("/api/evaluations").json()
    assert evs and evs[0]["well_id"] == w_new.id
    assert "pick_up" in evs[0]["metrics"]["operations"]


def test_model_held_when_worse(db):
    from sqlalchemy import update

    db.execute(update(MLModel).values(active=False))
    db.commit()
    a = MLModel(algorithm="a", status="selesai", active=True, metrics={"skill": 0.7})
    b = MLModel(algorithm="b", status="berjalan", metrics={"skill": 0.9})
    db.add_all([a, b])
    db.commit()
    _compare_and_activate(db, b)
    assert b.status == "ditahan" and not b.active and "Ditahan" in b.comparison["decision"]
    c = MLModel(algorithm="c", status="berjalan", metrics={"skill": 0.6})
    db.add(c)
    db.commit()
    _compare_and_activate(db, c)
    db.commit()
    assert c.status == "selesai" and c.active
    db.refresh(a)
    assert not a.active
    for x in (a, b, c):
        db.delete(x)
    db.commit()
