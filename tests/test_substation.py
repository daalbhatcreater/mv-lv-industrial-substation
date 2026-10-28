import math

import pytest

from substation import loads as L
from substation import pp_check
from substation.design import GRID, design
from substation.protection import CTI_S, Relay


@pytest.fixture(scope="module")
def d():
    return design()


def test_iec_idmt_curves():
    # textbook values at 10 x pickup, TMS 1 (IEC 60255-151)
    assert Relay("x", 1, 1, 1, "SI").t_relay(10) == pytest.approx(2.971, abs=1e-3)
    assert Relay("x", 1, 1, 1, "VI").t_relay(10) == pytest.approx(1.5, abs=1e-3)
    assert Relay("x", 1, 1, 1, "EI").t_relay(10) == pytest.approx(0.808, abs=1e-3)


def test_transformer_carries_plant_with_growth(d):
    t = d["transformer"]
    assert t["tr"].kva >= L.max_demand()["kva"] * (1 + L.FUTURE_GROWTH)
    assert 0.98 < t["efficiency"] < 1.0
    assert 0 < t["regulation_pct"] < 5


def test_mv_fault_by_hand(d):
    z = 1.1 * 11.0 ** 2 / 350          # ohm
    ik = 1.1 * 11.0 / (math.sqrt(3) * z)
    assert d["faults"]["mv_max"]["ik_ka"] == pytest.approx(ik, rel=1e-3)


def test_agrees_with_pandapower(d):
    pp = pp_check.run(GRID, d["transformer"]["tr"])
    f = d["faults"]
    assert pp[(1, "max")][0] == pytest.approx(f["mv_max"]["ik_ka"], rel=0.01)
    assert pp[(1, "max")][1] == pytest.approx(f["lv_single"]["ik_ka"], rel=0.01)
    assert pp[(1, "min")][1] == pytest.approx(f["lv_min"]["ik_ka"], rel=0.01)
    assert pp[(2, "max")][1] == pytest.approx(f["lv_parallel"]["ik_ka"], rel=0.01)


def test_switchgear_ratings(d):
    mv, lv, f = d["mv"], d["lv"], d["faults"]
    assert mv["isc_ka"] >= mv["ik_ka"] and mv["making_ka"] >= mv["ip_ka"]
    assert mv["tau_dc_ms"] < 45
    assert lv["icw_ka"] >= f["lv_single"]["ik_ka"]
    assert lv["icm_ka"] >= f["lv_single"]["ip_ka"]
    # paralleling the transformers would exceed the board: the interlock is needed
    assert not lv["parallel_ok"]


def test_grading_margins(d):
    for name, _, t_down, t_up in d["protection"]["margins"]:
        assert t_up - t_down >= CTI_S - 1e-3, name


def test_protection_checks(d):
    c = d["protection"]["checks"]
    assert c["highset_above_inrush"]
    assert c["highset_above_through_fault"]
    assert c["highset_below_min_mv_fault"]
    assert c["backup_for_through_fault_s"] < c["transformer_withstand_s"]
    assert c["hv_fault_clearing_s"] <= 0.1
    assert d["protection"]["ct"]["ok"]


def test_mv_cable_survives_backup_clearing(d):
    cab = d["cable"]
    t = d["protection"]["checks"]["mv_bus_fault_clearing_s"]
    ik = d["faults"]["mv_max"]["ik_ka"] * 1e3
    assert cab.size_mm2 >= ik * math.sqrt(t) / cab.k


def test_motor_start_dip(d):
    assert d["start"]["dip_pct"] < 10
