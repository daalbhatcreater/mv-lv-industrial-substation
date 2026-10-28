"""The same substation in pandapower, as an independent IEC 60909 check."""

import warnings

import pandapower as pp
import pandapower.shortcircuit as sc

from .network import LV_V, MV_KV


def build(grid, tr, n_transformers):
    net = pp.create_empty_network()
    mv = pp.create_bus(net, vn_kv=MV_KV, name="11 kV bus")
    lv = pp.create_bus(net, vn_kv=LV_V / 1e3, name="415 V PCC")
    pp.create_ext_grid(net, mv, s_sc_max_mva=grid.sk_max_mva, rx_max=grid.r_over_x,
                       s_sc_min_mva=grid.sk_min_mva, rx_min=grid.r_over_x)
    for k in range(n_transformers):
        pp.create_transformer_from_parameters(
            net, mv, lv, sn_mva=tr.kva / 1e3, vn_hv_kv=tr.ur_hv_kv, vn_lv_kv=tr.ur_lv_kv,
            vk_percent=100 * tr.uk, vkr_percent=100 * tr.pk_kw / tr.kva,
            pfe_kw=tr.p0_kw, i0_percent=0.0, shift_degree=150, name=f"TR{k + 1}")
    return net


def run(grid, tr):
    """{case: (Ik 11 kV, Ik 415 V)} in kA."""
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for n in (1, 2):
            for case in ("max", "min"):
                net = build(grid, tr, n)
                sc.calc_sc(net, case=case, lv_tol_percent=6)
                out[(n, case)] = tuple(net.res_bus_sc.ikss_ka.values)
    return out
