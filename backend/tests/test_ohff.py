"""OHFF 0.1–0.5 untuk tampilan (K-50): interpolasi di dalam rentang file, tanpa ekstrapolasi."""

import numpy as np
from app.services.dataset import fill_ohff
from app.services.operations import series_name


def _c(*vals):
    d = np.array([100.0, 200.0, 300.0])
    return d, np.array(vals, dtype=float)


def test_fill_between_file_ohffs():
    curves = {0.1: _c(10, 20, 30), 0.3: _c(20, 40, 60), 0.5: _c(30, 60, 90)}
    out, added = fill_ohff(curves)
    assert list(out) == [0.1, 0.2, 0.3, 0.4, 0.5]
    assert added == {0.2, 0.4}
    np.testing.assert_allclose(out[0.2][1], [15, 30, 45])
    np.testing.assert_allclose(out[0.4][1], [25, 50, 75])
    np.testing.assert_allclose(out[0.3][1], curves[0.3][1])  # kurva file tidak berubah


def test_no_extrapolation_outside_file_range():
    out, added = fill_ohff({0.3: _c(1, 2, 3), 0.4: _c(2, 3, 4), 0.5: _c(3, 4, 5)})
    assert added == set() and sorted(out) == [0.3, 0.4, 0.5]  # 0.1 dan 0.2 tidak digambar


def test_single_curve_and_overlap_only():
    one = {None: _c(1, 2, 3)}
    assert fill_ohff(one) == (one, set())
    lo = (np.array([0.0, 100.0, 200.0, 300.0]), np.array([0.0, 10, 20, 30]))
    hi = (np.array([100.0, 200.0]), np.array([30.0, 40]))
    out, added = fill_ohff({0.1: lo, 0.3: hi})
    assert added == {0.2}
    np.testing.assert_allclose(out[0.2][0], [100, 200])  # hanya kedalaman yang ada di keduanya
    np.testing.assert_allclose(out[0.2][1], [20, 30])
    assert series_name("pick_up", 0.2, True) == "PU - OHFF : 0.2 (interp.)"
