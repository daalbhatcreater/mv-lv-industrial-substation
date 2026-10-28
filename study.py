"""Run the substation design and write every result.

    python study.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from substation import loads as L
from substation import pp_check, sld
from substation.design import GRID, design
from substation.protection import inrush_point, transformer_damage

OUT = Path(__file__).parent / "results"


def tables(d):
    tr = d["transformer"]["tr"]
    load_rows = [{
        "Load": l.name, "Working": l.qty_working, "Standby": l.qty_standby,
        "kW each": l.kw, "pf": l.pf, "Efficiency": l.efficiency,
        "Load factor": l.load_factor, "Starting": l.starting,
        "Demand kW": round(l.demand_kw, 1), "Demand kvar": round(l.demand_kvar, 1),
    } for l in L.PLANT]
    dem = d["demand"]
    load_rows.append({"Load": f"Total x diversity {L.DIVERSITY}", "Demand kW": round(dem["kw"], 1),
                      "Demand kvar": round(dem["kvar"], 1)})

    t = d["transformer"]
    sizing = pd.DataFrame([
        ("Installed load", f"{dem['installed_kw']:.0f} kW"),
        ("Maximum demand", f"{dem['kw']:.0f} kW, {dem['kvar']:.0f} kvar, "
                           f"{dem['kva']:.0f} kVA at pf {dem['pf']:.3f}"),
        ("With 20 % growth", f"{t['kva_design']:.0f} kVA"),
        ("Transformer (each)", f"{tr.kva} kVA, 11/0.433 kV, Dyn11, uk {100 * tr.uk:g} %, "
                               f"In {tr.in_hv_a:.1f} A HV / {tr.in_lv_a:.0f} A LV"),
        ("Loading today / with growth", f"{100 * t['loading_today']:.0f} % / "
                                        f"{100 * t['loading_future']:.0f} %"),
        ("Efficiency at today's load", f"{100 * t['efficiency']:.2f} %"),
        ("Regulation at today's load", f"{t['regulation_pct']:.2f} %"),
        ("APFC to reach pf 0.95", f"{t['apfc_kvar']:.0f} kvar (detailed design: APFC project)"),
        ("Largest DOL motor start (160 kW)", f"{d['start']['i_start_a']:.0f} A, "
                                             f"{d['start']['dip_pct']:.1f} % dip at the PCC"),
    ], columns=["Item", "Value"])

    f = d["faults"]
    pp = pp_check.run(GRID, tr)
    faults = pd.DataFrame([
        ("11 kV bus, max", f["mv_max"]["ik_ka"], f["mv_max"]["ip_ka"], pp[(1, "max")][0]),
        ("11 kV bus, min", f["mv_min"]["ik_ka"], f["mv_min"]["ip_ka"], pp[(1, "min")][0]),
        ("415 V PCC, one transformer, max", f["lv_single"]["ik_ka"], f["lv_single"]["ip_ka"],
         pp[(1, "max")][1]),
        ("415 V PCC, one transformer, min", f["lv_min"]["ik_ka"], f["lv_min"]["ip_ka"],
         pp[(1, "min")][1]),
        ("415 V PCC, both paralleled (not allowed)", f["lv_parallel"]["ik_ka"],
         f["lv_parallel"]["ip_ka"], pp[(2, "max")][1]),
    ], columns=["Location", "Ik (kA)", "ip (kA)", "pandapower Ik (kA)"]).round(2)

    mv, lv = d["mv"], d["lv"]
    switchgear = pd.DataFrame([
        ("11 kV VCB", f"12 kV, {mv['ir_a']} A, {mv['isc_ka']:g} kA {mv['tk_s']} s, "
                      f"making {mv['making_ka']:g} kA peak",
         f"Ik {mv['ik_ka']:.2f} kA, ip {mv['ip_ka']:.1f} kA, DC time constant "
         f"{mv['tau_dc_ms']:.1f} ms (standard 45 ms)"),
        ("11 kV busbar", f"{mv['busbar_a']} A", "both transformers via one incomer: "
                                               f"{2 * tr.in_hv_a:.0f} A"),
        ("11 kV cable to each transformer", f"3C x {d['cable'].size_mm2} mm2 Al XLPE (UE)",
         "fault withstand for backup clearing time governs, not current"),
        ("LV incomer / bus coupler ACB", f"{lv['frame_a']} A, Ir {lv['ir_a']:.0f} A",
         f"transformer LV In {tr.in_lv_a:.0f} A"),
        ("LV PCC busbar", f"{lv['busbar_a']} A, {lv['icw_ka']} kA 1 s, Icm {lv['icm_ka']:.0f} kA",
         f"Ik {f['lv_single']['ik_ka']:.1f} kA, ip {f['lv_single']['ip_ka']:.1f} kA; "
         f"paralleled {f['lv_parallel']['ik_ka']:.1f} kA exceeds rating, hence the interlock"),
    ], columns=["Item", "Selected", "Check"])

    cable = pd.DataFrame([{"Size (mm2)": s, "Rating (A)": a,
                           "S min, main protection (mm2)": round(m, 1),
                           "S min, backup protection (mm2)": round(b, 1), "OK": ok}
                          for s, a, m, b, ok in d["cable_rows"]])

    p = d["protection"]
    relays = pd.DataFrame([
        (r.name, f"{r.ct_primary:g}/1", round(r.is_a), f"IEC {r.curve}", r.tms,
         round(r.highset_a) if r.highset_a else "off", r.highset_t if r.highset_a else "")
        for r in (p["tf"], p["inc"])],
        columns=["Relay", "CT", "51 pickup (A)", "Curve", "TMS", "50 pickup (A)", "50 delay (s)"])
    grading = pd.DataFrame([(n, round(i), round(t_down, 3), round(t_up, 3), round(t_up - t_down, 3))
                            for n, i, t_down, t_up in p["margins"]],
                           columns=["Pair", "Current at 11 kV (A)", "Downstream clears (s)",
                                    "Upstream clears (s)", "Margin (s)"])
    c = p["checks"]
    checks = pd.DataFrame([
        ("Faults on 11 kV cable / transformer HV cleared by",
         f"{c['hv_fault_clearing_s']:.2f} s (TF1 + VCB)"),
        ("11 kV bus faults cleared by", f"{c['mv_bus_fault_clearing_s']:.2f} s (IN1 delayed 50)"),
        ("Curves that grade: TF1 / IN1", f"{', '.join(c['tf_curves_that_grade'])} / "
                                         f"{', '.join(c['inc_curves_that_grade'])}"),
        ("LV PCC fault cleared by LV incomer", f"{c['through_fault_cleared_s']:.2f} s"),
        ("Backup by TF1 for the same fault", f"{c['backup_for_through_fault_s']:.2f} s"),
        ("Transformer through-fault withstand (IEC 60076-5)", f"{c['transformer_withstand_s']:.2f} s"),
        ("TF1 highset above inrush (12 x In, 0.1 s)", str(c["highset_above_inrush"])),
        ("TF1 highset above 1.3 x reflected LV fault", str(c["highset_above_through_fault"])),
        ("TF1 highset below minimum 11 kV fault", str(c["highset_below_min_mv_fault"])),
        ("CT effective ALF / linear up to", f"{p['ct']['alf_effective']:.0f} / "
                                            f"{p['ct']['linear_up_to_a'] / 1e3:.1f} kA "
                                            f"(highset {p['ct']['highset_a'] / 1e3:.2f} kA)"),
    ], columns=["Check", "Result"])
    return {"Load list": pd.DataFrame(load_rows), "Sizing": sizing, "Fault levels": faults,
            "Switchgear": switchgear, "MV cable": cable, "Relay settings": relays,
            "Grading": grading, "Checks": checks}


def plot_tcc(d, path):
    p, tr, f = d["protection"], d["transformer"]["tr"], d["faults"]
    i = np.geomspace(50, 25e3, 2000)
    fig, ax = plt.subplots(figsize=(9, 7))

    def curve(fn, imax, **kw):
        x = i[i <= imax]
        y = np.array([fn(v) for v in x])
        y[np.isinf(y)] = np.nan
        ax.plot(x, y, **kw)

    curve(p["lv_acb"].t_clear, f["lv_single"]["ik_hv_a"], color="tab:green",
          label="LV incomer ACB (referred to 11 kV)")
    curve(p["tf"].t_clear, f["mv_max"]["ik_ka"] * 1e3, color="tab:blue",
          label=f"TF1 relay: {p['tf'].curve} TMS {p['tf'].tms:.2f}, 50 at {p['tf'].highset_a:.0f} A")
    curve(p["inc"].t_clear, f["mv_max"]["ik_ka"] * 1e3, color="tab:red",
          label=f"IN1 relay: {p['inc'].curve} TMS {p['inc'].tms:.2f}, "
                f"50 at {p['inc'].highset_a:.0f} A / {p['inc'].highset_t:g} s")
    # a through-fault can never exceed the transformer's own short-circuit current
    curve(lambda x: transformer_damage(tr, x), tr.in_hv_a / tr.uk, color="black", ls="--",
          label="Transformer through-fault limit (IEC 60076-5)")
    ii, ti = inrush_point(tr)
    ax.plot([ii], [ti], "k^", label=f"Inrush {ii:.0f} A, 0.1 s")
    for k, (x, name) in enumerate([(f["lv_single"]["ik_hv_a"], "LV fault (reflected)"),
                                   (f["mv_min"]["ik_ka"] * 1e3, "11 kV min"),
                                   (f["mv_max"]["ik_ka"] * 1e3, "11 kV max")]):
        ax.axvline(x, color="grey", ls=":", lw=0.8)
        ax.text(x * 0.97, 60 / 2.5 ** (k % 2), f"{name}\n{x / 1e3:.2f} kA", fontsize=7,
                ha="right", color="dimgrey")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(50, 25e3)
    ax.set_ylim(0.03, 100)
    ax.set_xlabel("Current at 11 kV (A)")
    ax.set_ylabel("Clearing time (s)")
    ax.set_title("11 kV protection coordination")
    ax.grid(True, which="both", lw=0.3)
    ax.legend(fontsize=7.5, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    d = design()
    t = tables(d)
    with pd.ExcelWriter(OUT / "substation_design.xlsx") as xl:
        for name, df in t.items():
            df.to_excel(xl, sheet_name=name, index=False)
    plot_tcc(d, OUT / "protection_tcc.png")
    nodes, edges = sld.build(d)
    title = "11/0.415 kV industrial substation - single-line diagram"
    sld.render_png(nodes, edges, OUT / "sld.png", title)
    sld.write_drawio(nodes, edges, OUT / "sld.drawio", "SLD")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 90)
    for name, df in t.items():
        print(name)
        print(df.to_string(index=False))
        print()


if __name__ == "__main__":
    main()
