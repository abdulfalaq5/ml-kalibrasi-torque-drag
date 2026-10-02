"""Alur penuh: impor -> latih (validasi per kelompok sumur) -> prediksi -> dashboard -> ekspor."""

import io

import openpyxl
import pytest
from app.db.models import MLModel, Prediction, Well
from app.services.training import train
from make_sample_data import build_well, well_specs, write_wellplan
from sqlalchemy import select

from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def sample_files(tmp_dir):
    out = tmp_dir / "sample"
    out.mkdir(exist_ok=True)
    files = []
    for i, spec in enumerate(well_specs(6, seed=11)):
        spec.name = f"T{i + 1:02d}"
        p = out / f"{spec.name}.xlsx"
        write_wellplan(build_well(spec), p, include_actual=i < 5)
        files.append(p)
    return files


def _upload(client, path, **form):
    with path.open("rb") as fh:
        return client.post("/api/files", files={"file": (path.name, fh)}, data=form)


def test_upload_rejects_non_excel(auth_client, tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b")
    assert _upload(auth_client, p).status_code == 400
    p = tmp_path / "x.xlsx"
    p.write_text("bukan zip")
    assert _upload(auth_client, p).status_code == 400


def test_failed_file_has_reason(auth_client, tmp_path):
    wb = openpyxl.Workbook()
    wb.active.title = "Sembarang"
    p = tmp_path / "gagal.xlsx"
    wb.save(p)
    j = _upload(auth_client, p).json()
    assert j["status"] == "gagal"
    assert j["issues"] and j["issues"][0]["level"] == "error"


def test_full_pipeline(auth_client, db, sample_files):
    for p in [FIXTURES / "contoh1_wellplan_aktual.xlsx", *sample_files]:
        j = _upload(auth_client, p).json()
        assert j["status"] in ("ok", "peringatan"), j
    # roadmap tidak memuat nama sumur -> diisi di form unggah
    j = _upload(
        auth_client, FIXTURES / "contoh1_roadmap.xlsx", well_name="W01", section_in="12.25"
    ).json()
    assert j["well_name"] == "W01", j
    # unggah ulang file yang sama tidak menggandakan data
    again = _upload(auth_client, sample_files[0]).json()
    assert again["status"] in ("ok", "peringatan")

    wells = auth_client.get("/api/wells").json()
    names = {w["name"] for w in wells}
    assert {"W01", "T01", "T06"} <= names
    for w in wells:
        assert w["section_in"] is not None and w["well_type"] in ("J", "S", "Horizontal")

    # koreksi manual tipe sumur
    t06 = next(w for w in wells if w["name"] == "T06")
    r = auth_client.patch(f"/api/wells/{t06['id']}", json={"well_type": "S"})
    assert r.json()["type_source"] == "manual"

    # latih langsung (sinkron) agar deterministik di tes
    row = MLModel(algorithm="terbaik", status="antri")
    db.add(row)
    db.commit()
    train(db, row)
    assert row.status == "selesai" and row.active
    m = row.metrics["operations"]["pick_up"]
    assert m["overall"]["n_wells"] == 6  # W01 + T01..T05
    assert m["overall"]["ml"]["rmse"] > 0
    assert m["by_section_type"] and any(g["warning"] for g in m["by_section_type"])
    assert set(m["candidates"]) >= {"ridge_langsung", "ridge_selisih", "xgboost1_langsung"}

    # sumur latih punya prediksi out-of-fold, sumur baru belum
    oof_wells = set(
        db.scalars(
            select(Prediction.well_id).where(
                Prediction.kind == "oof", Prediction.model_id == row.id
            )
        )
    )
    t06_id = db.scalar(select(Well.id).where(Well.name == "T06"))
    assert len(oof_wells) == 6 and t06_id not in oof_wells

    r = auth_client.post(f"/api/wells/{t06_id}/predict")
    assert r.status_code == 200, r.text

    prof = auth_client.get(f"/api/wells/{t06_id}/profile").json()
    assert prof["has_actual"] is False
    assert prof["prediction"]["kind"] == "full"
    assert any("Belum ada data aktual" in w for w in prof["warnings"])
    for op, o in prof["operations"].items():
        assert len(o["ml"]["depth"]) > 5, op
        assert o["diff"]["ml_minus_actual"]["depth"] == []
        assert len(o["diff"]["ml_minus_wp"]["depth"]) == len(o["ml"]["depth"])

    w01 = db.scalar(select(Well.id).where(Well.name == "W01"))
    prof = auth_client.get(f"/api/wells/{w01}/profile?units=si").json()
    assert prof["prediction"]["kind"] == "oof"
    assert prof["operations"]["torque_on_bottom"]["unit"] == "kN·m"
    assert prof["operations"]["pick_up"]["metrics"]["ml"]["n"] > 10

    # ekspor Excel terbuka dan memuat grafik
    r = auth_client.get(f"/api/wells/{w01}/export.xlsx")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert {"Perbandingan", "Prediksi ML", "Grafik", "Metrik"} <= set(wb.sheetnames)

    r = auth_client.get(f"/api/models/{row.id}/report.xlsx")
    assert r.status_code == 200
    openpyxl.load_workbook(io.BytesIO(r.content))

    r = auth_client.get("/api/models/dataset.csv")
    assert r.status_code == 200 and "wp_ff03" in r.text
