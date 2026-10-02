import pytest
from app.services import units


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Pick Up FF 0.30 (kip)", "klbf"),
        ("Torque (ft-lbf)", "ft-lbf"),
        ("Torque [kft.lbf]", "kft-lbf"),
        ("Depth (m)", "m"),
        ("DLS (°/100ft)", "deg/100ft"),
        ("Hookload (kN)", "kn"),
        ("Tanpa satuan", None),
        ("Aneh (pisang)", None),
    ],
)
def test_unit_from_header(header, expected):
    assert units.unit_from_header(header) == expected


def test_conversions():
    assert units.to_si(1000, "ft") == pytest.approx(304.8)
    assert units.to_si(100, "klbf") == pytest.approx(444.822, rel=1e-5)
    assert units.to_si(10_000, "ft-lbf") == pytest.approx(13.558, rel=1e-4)
    assert units.to_si(3, "deg/100ft") == pytest.approx(2.9528, rel=1e-4)
    assert units.from_si(units.to_si(123.4, "kft-lbf"), "kft-lbf") == pytest.approx(123.4)
