"""Design sequence for the substation: demand, transformer, LV switchgear,
MV switchgear, MV cables, protection settings and checks."""

import math

from . import loads as L
from .network import (LV_V, MV_CABLES, MV_KV, TRANSFORMERS, Grid, MVCable,
                      Transformer, kappa, lv_fault, mv_fault)
from .protection import (CT, CTI_S, LVBreaker, Relay, grade, inrush_point,
                         lead_burden, transformer_damage)

GRID = Grid()
VCB_BREAKING_KA = [16, 20, 25, 31.5]
VCB_CURRENTS = [630, 800, 1250, 1600, 2000]
ACB_FRAMES = [800, 1000, 1250, 1600, 2000, 2500, 3200, 4000]
LV_BOARD_ICW_KA = [36, 50, 65, 80, 100]
CT_PRIMARIES = [50, 75, 100, 150, 200, 300, 400, 600, 800]


def first_at_least(values, x):
    return next(v for v in values if v >= x)


def size_transformer(demand):
    """Each transformer carries the whole plant plus growth, on the demand
    before power factor correction (the APFC panel may be out of service)."""
    kva_design = demand["kva"] * (1 + L.FUTURE_GROWTH)
    rating = first_at_least(sorted(TRANSFORMERS), kva_design)
    tr = Transformer(rating)
    load = demand["kva"]
    return {
        "tr": tr, "kva_design": kva_design,
        "loading_today": load / rating,
        "loading_future": kva_design / rating,
        "efficiency": tr.efficiency(load, demand["pf"]),
        "regulation_pct": 100 * tr.regulation(load / rating, demand["pf"]),
        "apfc_kvar": L.apfc_kvar(demand["kw"], demand["pf"], L.PF_TARGET_WITH_APFC),
    }


def motor_start_dip(tr, motor_kw=160, pf=0.88, eff=0.95, start_mult=6.5, start_pf=0.3,
                    running_kva=0.0):
    """Voltage dip at the PCC when the largest DOL motor starts, from the
    source impedance (grid + one transformer)."""
    flc = motor_kw * 1e3 / (math.sqrt(3) * LV_V * pf * eff)
    i_start = start_mult * flc
    z = lv_fault(GRID, tr, case="min")["z"]
    sin = math.sqrt(1 - start_pf ** 2)
    dv = math.sqrt(3) * i_start * (z.real * start_pf + z.imag * sin)
    return {"flc_a": flc, "i_start_a": i_start, "dip_pct": 100 * dv / LV_V}


def lv_switchgear(tr, faults):
    ir_needed = tr.in_lv_a
    frame = first_at_least(ACB_FRAMES, ir_needed / 0.9)
    ir = math.ceil(ir_needed / (0.05 * frame)) * 0.05 * frame
    icw = first_at_least(LV_BOARD_ICW_KA, 1.1 * faults["lv_single"]["ik_ka"])
    return {"frame_a": frame, "ir_a": ir, "busbar_a": frame, "icw_ka": icw,
            "icm_ka": icw * (2.2 if icw > 50 else 2.1),
            "parallel_ok": faults["lv_parallel"]["ik_ka"] <= icw}


def mv_switchgear(tr, faults):
    mv = faults["mv_max"]
    breaking = first_at_least(VCB_BREAKING_KA, 1.1 * mv["ik_ka"])
    # incomer carries both transformers when the other incomer is out
    i_incomer = 2 * tr.in_hv_a
    return {
        "ur_kv": 12, "ir_a": first_at_least(VCB_CURRENTS, i_incomer), "isc_ka": breaking,
        "making_ka": 2.5 * breaking, "tk_s": 3,
        "busbar_a": first_at_least(VCB_CURRENTS, i_incomer),
        # IEC 62271-100 standard DC time constant is 45 ms
        "tau_dc_ms": 1000 * mv["x_over_r"] / (2 * math.pi * 50),
        "ip_ka": mv["ip_ka"], "ik_ka": mv["ik_ka"],
    }


def size_mv_cable(tr, faults, t_main, t_backup, length_m=60):
    """Smallest 3-core Al XLPE cable meeting load current and the adiabatic
    limit for the backup clearing time (main protection assumed to fail)."""
    ik = faults["mv_max"]["ik_ka"] * 1e3
    rows = []
    chosen = None
    for size, (r, x, amps) in sorted(MV_CABLES.items()):
        s_main = ik * math.sqrt(t_main) / 94
        s_backup = ik * math.sqrt(t_backup) / 94
        ok = amps >= tr.in_hv_a and size >= s_backup
        rows.append((size, amps, s_main, s_backup, ok))
        if ok and chosen is None:
            chosen = MVCable(size, length_m, r, x)
    return chosen, rows


def protection(tr, faults, lv):
    """Grade the transformer feeder relay over the LV incomer across the whole
    current range it can see, then the 11 kV incomer over the feeder relay."""
    through = faults["lv_single"]["ik_hv_a"]
    mv_ik = faults["mv_max"]["ik_ka"] * 1e3
    lv_acb = LVBreaker("LV incomer ACB", ir_a=lv["ir_a"], tr_s=4, isd_a=3 * lv["ir_a"],
                       tsd_s=0.3, ratio=tr.ratio)
    # LV long-time pickup can be up to 1.2 Ir; the HV pickup must sit above it
    lv_pickup_hv = 1.2 * lv_acb.ir_a / tr.ratio
    inrush_a, _ = inrush_point(tr)

    ct_tf = first_at_least(CT_PRIMARIES, 1.5 * tr.in_hv_a)
    candidates = []
    for curve in ("SI", "VI", "EI"):
        r = Relay("Transformer feeder relay (TF1)", ct_primary=ct_tf,
                  is_a=1.3 * lv_pickup_hv, tms=0.0, curve=curve)
        r.highset_a = max(1.3 * through, 1.1 * inrush_a)
        if grade(r, lv_acb.t_clear, lv_pickup_hv, through) is None:
            continue
        if r.t_clear(through) < transformer_damage(tr, through):
            candidates.append(r)
    # fastest backup for the LV fault among the curves that grade
    tf = min(candidates, key=lambda r: r.t_clear(through))

    ct_in = first_at_least(CT_PRIMARIES, 1.5 * 2 * tr.in_hv_a)
    inc_candidates = []
    for curve in ("SI", "VI", "EI"):
        r = Relay("11 kV incomer relay (IN1)", ct_primary=ct_in,
                  is_a=max(1.2 * 2 * tr.in_hv_a, 1.3 * tf.is_a), tms=0.0, curve=curve)
        # time-delayed 50 stage: above the feeder highset, one CTI behind it,
        # so 11 kV bus faults are not left to the slow end of the IDMT curve
        r.highset_a = 1.3 * tf.highset_a
        r.highset_t = tf.t_relay(r.highset_a) + CTI_S
        if grade(r, tf.t_clear, tf.is_a * 1.06, mv_ik) is not None:
            inc_candidates.append(r)
    if not inc_candidates:
        raise ValueError("incomer relay cannot be graded over the feeder relay")
    # fastest clearance of an 11 kV bus fault
    inc = min(inc_candidates, key=lambda r: r.t_clear(mv_ik))

    checks = {
        "tf_curves_that_grade": [r.curve for r in candidates],
        "inc_curves_that_grade": [r.curve for r in inc_candidates],
        "highset_above_inrush": tf.highset_a > inrush_a,
        "highset_above_through_fault": tf.highset_a >= 1.3 * through,
        "highset_below_min_mv_fault": tf.highset_a < faults["mv_min"]["ik_ka"] * 1e3,
        "through_fault_cleared_s": lv_acb.t_clear(through),
        "backup_for_through_fault_s": tf.t_clear(through),
        "transformer_withstand_s": transformer_damage(tr, through),
        "hv_fault_clearing_s": tf.t_clear(mv_ik),
        "mv_bus_fault_clearing_s": inc.t_clear(mv_ik),
    }

    def worst_margin(up, down, lo, hi):
        worst = (math.inf, 0.0)
        for k in range(400):
            i = lo * (hi / lo) ** (k / 399)
            td = down(i)
            if not math.isinf(td):
                worst = min(worst, (up(i) - td, i))
        return worst

    m1, i1 = worst_margin(tf.t_clear, lv_acb.t_clear, lv_pickup_hv, through)
    m2, i2 = worst_margin(inc.t_clear, tf.t_clear, tf.is_a * 1.06, mv_ik)
    margins = [
        ("LV incomer ACB -> TF1 (worst point)", i1, lv_acb.t_clear(i1), tf.t_clear(i1)),
        ("LV incomer ACB -> TF1 at LV fault", through, lv_acb.t_clear(through),
         tf.t_clear(through)),
        ("TF1 -> IN1 (worst point)", i2, tf.t_clear(i2), inc.t_clear(i2)),
        ("TF1 highset -> IN1 at max 11 kV fault", mv_ik, tf.t_clear(mv_ik), inc.t_clear(mv_ik)),
    ]

    ct = CT(ct_tf)
    burden = lead_burden(20)
    alf_eff = ct.effective_alf(burden)
    ct_check = {"ct": f"{ct_tf:g}/1 A 5P20 5 VA", "burden_ohm": burden,
                "alf_effective": alf_eff, "linear_up_to_a": alf_eff * ct_tf,
                "highset_a": tf.highset_a, "ok": alf_eff * ct_tf > 2 * tf.highset_a}
    return {"lv_acb": lv_acb, "tf": tf, "inc": inc, "checks": checks,
            "margins": margins, "ct": ct_check}


def design():
    demand = L.max_demand()
    t = size_transformer(demand)
    tr = t["tr"]
    faults = {
        "mv_max": mv_fault(GRID),
        "mv_min": mv_fault(GRID, c=1.0, sk=GRID.sk_min_mva),
        "lv_single": lv_fault(GRID, tr, 1),
        "lv_parallel": lv_fault(GRID, tr, 2),
        "lv_min": lv_fault(GRID, tr, 1, case="min"),
    }
    lv = lv_switchgear(tr, faults)
    mv = mv_switchgear(tr, faults)
    prot = protection(tr, faults, lv)
    cable, cable_rows = size_mv_cable(tr, faults,
                                      t_main=prot["checks"]["hv_fault_clearing_s"],
                                      t_backup=prot["checks"]["mv_bus_fault_clearing_s"])
    start = motor_start_dip(tr)
    return {"demand": demand, "transformer": t, "faults": faults, "lv": lv, "mv": mv,
            "protection": prot, "cable": cable, "cable_rows": cable_rows, "start": start}
