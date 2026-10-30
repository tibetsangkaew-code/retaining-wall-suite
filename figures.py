from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go

DIM = "#222222"
EXT = "#888888"
WATER = "#0277bd"


def _rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    rr, gg, bb = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({rr},{gg},{bb},{alpha})"


def _layout(p, r, mode="full"):
    dims_on = mode in ("full", "dims")
    force_on = mode in ("full", "forces")

    H1, t1, L1, L2 = p["H1"], p["t1"], p["L1"], p["L2"]
    t2, t3 = p["t2"], p["t3"]
    S, Df, gw = p["q_sur"], p.get("Df", 0.0), p["gw"]
    
    layers = p.get("layers", [
        {"thick": 2.0, "gs": 18.0, "phi": 30.0},
    ])
    
    H2, hw = r["H2"], r["H5"]
    xr = L2 + t2
    use_pass = bool(p.get("use_passive", False)) and Df > 0
    uh = 0.8 if (force_on and r["U"] > 1e-9) else 0.0

    xmin = -2.7 if dims_on else -1.0
    xe = L1 + (3.5 if dims_on else 1.3)
    xl = xmin + 0.1

    polys, labels, lines, dims = [], [], [], []

    def poly(name, pts, fc, ec="none", alpha=1.0, lw=1.0):
        polys.append(dict(name=name, pts=pts, fc=fc, ec=ec, alpha=alpha, lw=lw))

    if use_pass:
        if Df <= t1:
            poly("Passive soil", [(xl, 0), (0, 0), (0, Df), (xl, Df)], "#ead9b8")
        else:
            poly("Passive soil", [(xl, 0), (0, 0), (0, t1), (L2, t1), (L2, Df), (xl, Df)], "#ead9b8")

    soil_colors = ["#f5ebe0", "#e3d5ca", "#d5bdaf"]
    curr_y = t1
    for idx, lyr in enumerate(layers):
        th = lyr["thick"]
        next_y = min(curr_y + th, H1)
        if next_y <= curr_y:
            break
        poly(f"Soil Layer {idx+1}", [(xr, curr_y), (xe, curr_y), (xe, next_y), (xr, next_y)],
             soil_colors[idx % len(soil_colors)], ec="#b0a695", alpha=0.9, lw=1.0)
        
        labels.append(dict(
            x=xr + 0.3, y=(curr_y + next_y) / 2,
            text=f"<b>Layer {idx+1}</b><br>γ={lyr['gs']} kN/m³<br>φ={lyr['phi']}°",
            color="#444444", ha="left", va="center", size=9, bold=False
        ))
        curr_y = next_y

    xw0 = L1
    if hw > t1 + 1e-9:
        a_val = 0.0 if H2 <= 0 else (xr - (t2 - t3) * (hw - t1) / H2)
        xw0 = a_val
        poly("Groundwater", [(xr, t1), (xe, t1), (xe, hw), (xw0, hw)], "#9fd0f0", alpha=0.6)

    if S > 0:
        poly("Surcharge", [(L2 + t3, H1), (xe, H1), (xe, H1 + 0.35), (L2 + t3, H1 + 0.35)],
             "#bbdefb", ec="#1976d2")
        labels.append(dict(x=(L2 + t3 + xe) / 2, y=H1 + 0.175, text=f"S = {S:.1f} kPa",
                           color="#0d47a1", ha="center", va="center", size=10, bold=True))

    poly("Concrete", [(0, 0), (L1, 0), (L1, t1), (xr, t1), (L2 + t3, H1), (L2, H1), (L2, t1), (0, t1)],
         "#bdbdbd", ec="#222222", lw=2)

    # วาดเสาเข็มใต้ฐาน (หากเปิดใช้งาน Piles)
    use_piles = p.get("use_piles", False)
    if use_piles and r.get("pile_results"):
        pile_loads = r["pile_results"]["pile_loads"]
        for pl in pile_loads:
            xp = pl["x_pos"]
            # วาดรูปเสาเข็มเป็นแท่งสี่เหลี่ยมผืนผ้าปักลงไปใต้ฐาน (จาก y=0 ถึง y=-1.2)
            poly(f"Pile {pl['pile_no']}", [(xp - 0.1, 0), (xp + 0.1, 0), (xp + 0.1, -1.2), (xp - 0.1, -1.2)],
                 "#78909c", ec="#37474f", alpha=1.0, lw=1.5)
            labels.append(dict(
                x=xp, y=-1.35, text=f"<b>P{pl['pile_no']}</b><br>{pl['load_kg']:.0f}kg",
                color="#37474f", ha="center", va="top", size=8, bold=True
            ))

    if uh > 0:
        poly("Uplift", [(0, 0), (L1, 0), (L1, -uh)], "#b3e5fc", ec="#0277bd", alpha=0.9, lw=1.2)
        labels.append(dict(x=L1 + 0.12, y=-uh * 0.35, text=f"U = {r['U']:.1f} kg",
                           color="#01579b", ha="left", va="center", size=10, bold=True))

    xw_ = xe
    if force_on:
        lat = {n.split()[0]: (f, y) for n, f, y in r["lat"]}
        x0 = xe + 0.4
        
        if "Ps" in lat:
            f_ps, _ = lat["Ps"]
            xps = x0 + 0.4
            poly("Ps", [(x0, 0), (xps, 0), (xps, H1), (x0, H1)], "#90caf9", ec="#1565c0", alpha=0.85)
            labels.append(dict(x=xps + 0.1, y=H1 / 2, text=f"Ps={f_ps:.1f}kg", color="#0d47a1", ha="left", va="center", size=9, bold=True))

        x1 = x0 + 0.9
        colors_p = ["#ffcc80", "#ffab91", "#ff8a65"]
        curr_d = 0.0
        for idx, lyr in enumerate(layers):
            th = lyr["thick"]
            h_top = curr_d
            h_bot = min(curr_d + th, H1)
            actual_th = h_bot - h_top
            if actual_th <= 0:
                break
            
            y_top_plot = H1 - h_top
            y_bot_plot = H1 - h_bot
            
            p_name = f"P{idx+1}"
            if p_name in lat:
                f_val, _ = lat[p_name]
                width_scale = min(f_val / 1000.0, 1.2)
                poly(p_name, [(x1, y_top_plot), (x1 + width_scale, y_bot_plot), (x1, y_bot_plot)],
                     colors_p[idx % len(colors_p)], ec="#e65100", alpha=0.85)
                labels.append(dict(x=x1 + width_scale + 0.05, y=(y_top_plot + y_bot_plot) / 2,
                                   text=f"{p_name}={f_val:.1f}kg", color="#e65100", ha="left", va="center", size=9, bold=True))
            curr_d = h_bot

        if hw > 1e-9 and "Pw" in lat:
            f_pw, _ = lat["Pw"]
            x2 = x1 + 1.2
            y_hw_plot = hw
            poly("Pw", [(x2, y_hw_plot), (x2 + 0.8, 0), (x2, 0)], "#81d4fa", ec="#0277bd", alpha=0.85)
            labels.append(dict(x=x2 + 0.9, y=hw / 2, text=f"Pw={f_pw:.1f}kg", color="#01579b", ha="left", va="center", size=9, bold=True))
            xw_ = x2 + 1.8

    if hw > 1e-9:
        x_end = (xw_ + 0.5) if force_on else xe
        lines.append(dict(x=[xw0, x_end], y=[hw, hw], color=WATER, name="GWL"))
        labels.append(dict(x=x_end, y=hw + 0.08, text="GWL", color=WATER,
                           ha="right", va="bottom", size=10, bold=True))

    def dh(xa, xb_, y, text, yref, side=-1, stag=0):
        if abs(xb_ - xa) < 1e-6:
            return
        dims.append(dict(p0=(xa, y), p1=(xb_, y),
                         ext=[((xa, yref), (xa, y)), ((xb_, yref), (xb_, y))],
                         text=text, vertical=False, side=side, stag=stag))

    def dv(ya, yb, x, text, xr0=None, xr1=None, side=-1):
        if abs(yb - ya) < 1e-6:
            return
        ext = []
        if xr0 is not None:
            ext.append(((xr0, ya), (x, ya)))
        if xr1 is not None:
            ext.append(((xr1, yb), (x, yb)))
        dims.append(dict(p0=(x, ya), p1=(x, yb), ext=ext, text=text,
                         vertical=True, side=side, stag=0))

    if dims_on:
        yd1 = -1.6 if use_piles else -1.4
        yd2 = -2.5 if use_piles else -2.3
        dh(0, L2, yd1, f"L2 = {L2:.2f}", 0)
        dh(L2, xr, yd1, f"t2 = {t2:.2f}", 0, stag=1)
        dh(xr, L1, yd1, f"L3 = {r['L3']:.2f}", 0)
        dh(0, L1, yd2, f"L1 = {L1:.2f}", 0)
        dh(L2, L2 + t3, H1 + 0.8, f"t3 = {t3:.2f}", H1, side=+1)
        dv(0, t1, -0.6, f"t1 = {t1:.2f}", xr0=0, xr1=0, side=-1)
        dv(0, H1, -1.3, f"H1 = {H1:.2f}", xr0=0, xr1=L2, side=-1)
        dv(t1, H1, L1 + 1.3, f"H2 = {r['H2']:.2f}", xr0=L1, xr1=L2 + t3, side=+1)
        if hw > 1e-9:
            dv(0, hw, L1 + 2.0, f"H5 = {hw:.2f}", xr0=L1, side=+1)

    sv = None
    if force_on and np.isfinite(r["x_bar"]) and 0 <= r["x_bar"] <= L1:
        sv = dict(x=r["x_bar"], tail=-0.9, text=f"ΣV = {r['V']:.1f} kg")

    xmax = (xw_ + 1.2) if force_on else (xe + 0.3)
    ymin = (-3.2 if use_piles else -3.0)
    ymax = H1 + 1.5

    return dict(polys=polys, labels=labels, lines=lines, dims=dims, sv=sv,
                xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)


def wall_figure(p, r):
    L = _layout(p, r, "full")
    fig = go.Figure()
    for q in L["polys"]:
        pts = q["pts"] + [q["pts"][0]]
        edge = _rgba("#000000", 0) if q["ec"] == "none" else q["ec"]
        fig.add_trace(go.Scatter(
            x=[u for u, _ in pts], y=[v for _, v in pts], mode="lines",
            fill="toself", fillcolor=_rgba(q["fc"], q["alpha"]),
            line=dict(color=edge, width=q["lw"]), name=q["name"], hoverinfo="name"))
    for ln in L["lines"]:
        fig.add_trace(go.Scatter(x=ln["x"], y=ln["y"], mode="lines",
                                 line=dict(color=ln["color"], width=2, dash="dash"),
                                 name=ln["name"], hoverinfo="skip"))
    ex, ey = [], []
    for d in L["dims"]:
        for pa, pb in d["ext"]:
            ex += [pa[0], pb[0], None]
            ey += [pa[1], pb[1], None]
    if ex:
        fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color=EXT, width=0.8),
                                 showlegend=False, hoverinfo="skip"))
    yanc = {"center": "middle", "bottom": "bottom", "top": "top"}
    for lb in L["labels"]:
        txt = f"<b>{lb['text']}</b>" if lb.get("bold") else lb["text"]
        fig.add_annotation(x=lb["x"], y=lb["y"], text=txt, showarrow=False,
                           xanchor=lb["ha"], yanchor=yanc[lb["va"]],
                           font=dict(size=10, color=lb["color"]))
    for d in L["dims"]:
        (x0, y0), (x1, y1) = d["p0"], d["p1"]
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y",
                           text="", showarrow=True, arrowhead=2, startarrowhead=2,
                           arrowside="end+start", arrowsize=1, startarrowsize=1,
                           arrowwidth=1.2, arrowcolor=DIM)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        if d["vertical"]:
            fig.add_annotation(x=mx, y=my, text=d["text"], showarrow=False, textangle=-90,
                               xshift=d["side"] * 12, font=dict(size=11, color=DIM))
        else:
            fig.add_annotation(x=mx, y=my, text=d["text"], showarrow=False,
                               yshift=d["side"] * (12 + 14 * d["stag"]),
                               font=dict(size=11, color=DIM))
    if L["sv"]:
        sv = L["sv"]
        fig.add_annotation(x=sv["x"], y=0, ax=sv["x"], ay=sv["tail"], xref="x", yref="y",
                           axref="x", ayref="y", text="", showarrow=True, arrowhead=2,
                           arrowwidth=2.5, arrowcolor="#1565c0")
        fig.add_annotation(x=sv["x"], y=sv["tail"] - 0.02, text=f"<b>{sv['text']}</b>",
                           showarrow=False, yanchor="top", bgcolor="rgba(255,255,255,0.85)",
                           font=dict(size=11, color="#1565c0"))
    fig.add_annotation(x=0, y=0, text="<b>A</b>", showarrow=False, xshift=-10, yshift=10,
                       font=dict(size=12))
    fig.update_layout(
        title="<b>Retaining Wall Section: Piles & Multi-Layer Soils</b>",
        xaxis=dict(range=[L["xmin"], L["xmax"]], scaleanchor="y", scaleratio=1,
                   showgrid=False, zeroline=False, title="Distance (m)"),
        yaxis=dict(range=[L["ymin"], L["ymax"]], showgrid=False, zeroline=False,
                   title="Height (m)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=20),
        height=700,
        template="plotly_white",
    )
    return fig


def pressure_figure(p, r):
    use_piles = p.get("use_piles", False)
    if use_piles and r.get("pile_results"):
        # แสดงกราฟแท่งแรงกดเสาเข็มแต่ละต้น
        pr = r["pile_results"]
        loads = [item["load_kg"] for item in pr["pile_loads"]]
        x_pos = [item["x_pos"] for item in pr["pile_loads"]]
        allow = pr["pile_cap_allow"]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=[f"Pile {item['pile_no']} (X={item['x_pos']:.2f}m)" for item in pr["pile_loads"]],
                             y=loads, marker_color="#1565c0", name="Actual Pile Load"))
        fig.add_trace(go.Scatter(x=[-0.5, len(loads)-0.5], y=[allow, allow], mode="lines",
                                 line=dict(color="red", dash="dash", width=2),
                                 name=f"Allowable Capacity ({allow:,.0f} kg)"))
        fig.update_layout(
            title="<b>Pile Load Distribution (kg/pile) vs Allowable</b>",
            xaxis=dict(title="Pile Number & Position", showgrid=True),
            yaxis=dict(title="Load (kg)", showgrid=True),
            margin=dict(l=20, r=20, t=50, b=20),
            height=350,
            template="plotly_white",
        )
        return fig
    else:
        # กราฟแรงแบกทานใต้ฐานแผ่ปกติ
        B, qa = p["L1"], p["q_allow"]
        qt, qh = r["q_toe"], r["q_heel"]
        fig = go.Figure()
        if np.isfinite(qt) and np.isfinite(qh):
            fig.add_trace(go.Scatter(x=[0, 0, B, B], y=[0, qt, qh, 0], fill="toself",
                                     fillcolor="rgba(144,202,249,0.5)",
                                     line=dict(color="#1565c0", width=2), name="Bearing Pressure"))
            fig.add_annotation(x=0, y=qt, text=f"{qt:.1f} kg/m²", showarrow=False,
                               xanchor="left", yanchor="bottom")
            fig.add_annotation(x=B, y=qh, text=f"{qh:.1f} kg/m²", showarrow=False,
                               xanchor="right", yanchor="bottom")
        fig.add_trace(go.Scatter(x=[0, B], y=[qa, qa], mode="lines",
                                 line=dict(color="red", dash="dash", width=2),
                                 name=f"q_allow ({qa:.0f} kg/m²)"))
        fig.update_layout(
            title="<b>Bearing Pressure Diagram (kg/m²)</b>",
            xaxis=dict(title="Base Width (m) [Toe → Heel]", showgrid=True),
            yaxis=dict(title="Pressure (kg/m²)", showgrid=True),
            margin=dict(l=20, r=20, t=50, b=20),
            height=350,
            template="plotly_white",
        )
        return fig


def rebar_figure_png(p, r):
    H1, t1, L1, L2 = p["H1"], p["t1"], p["L1"], p["L2"]
    t2, t3 = p["t2"], p["t3"]
    xr = L2 + t2

    fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=200)
    ax.set_aspect("equal")
    ax.axis("off")

    from matplotlib.patches import Polygon
    wall_pts = [(0, 0), (L1, 0), (L1, t1), (xr, t1), (L2 + t3, H1), (L2, H1), (L2, t1), (0, t1)]
    ax.add_patch(Polygon(wall_pts, closed=True, fc="#e0e0e0", ec="#222222", lw=1.5))

    ax.plot([L2 + t2 - 0.08, L2 + t3 - 0.04], [t1 + 0.1, H1 - 0.1], color="#c62828", lw=2.5)
    ax.text(L2 + t2 + 0.15, H1 / 2, "DB16 @ 0.20 m\n(Stem Rebar)", color="#c62828", fontsize=8, fontweight="bold", va="center")

    ax.plot([xr + 0.1, L1 - 0.1], [t1 - 0.08, t1 - 0.08], color="#1565c0", lw=2.5)
    ax.text((xr + L1) / 2, t1 - 0.35, "DB16 @ 0.20 m (Heel Rebar)", color="#1565c0", fontsize=8, fontweight="bold", ha="center")

    ax.plot([0.1, L2 - 0.1], [0.08, 0.08], color="#2e7d32", lw=2.5)
    ax.text(L2 / 2, -0.25, "DB12 @ 0.20 m (Toe Rebar)", color="#2e7d32", fontsize=8, fontweight="bold", ha="center")

    ax.set_xlim(-0.8, L1 + 1.2)
    ax.set_ylim(-0.8, H1 + 0.8)
    ax.set_title("Reinforcement Layout Details", fontsize=10, fontweight="bold", pad=6)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return buf.getvalue()


def _png(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return buf.getvalue()


def wall_figure_png(p, r, mode="dims"):
    L = _layout(p, r, mode)
    scale = {"dims": 0.7, "forces": 0.62, "full": 0.55}[mode]
    w = (L["xmax"] - L["xmin"]) * scale
    h = (L["ymax"] - L["ymin"]) * scale
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(L["xmin"], L["xmax"])
    ax.set_ylim(L["ymin"], L["ymax"])
    ax.set_aspect("equal")
    ax.axis("off")
    from matplotlib.patches import Polygon
    for q in L["polys"]:
        ax.add_patch(Polygon(q["pts"], closed=True, fc=q["fc"], ec=q["ec"], lw=q["lw"], alpha=q["alpha"]))
    for ln in L["lines"]:
        ax.plot(ln["x"], ln["y"], ls="--", color=ln["color"], lw=1.4)
    for lb in L["labels"]:
        ax.text(lb["x"], lb["y"], lb["text"], color=lb["color"], fontsize=lb["size"], ha=lb["ha"], va=lb["va"], fontweight="bold" if lb.get("bold") else "normal")
    for d in L["dims"]:
        for pa, pb in d["ext"]:
            ax.plot([pa[0], pb[0]], [pa[1], pb[1]], color=EXT, lw=0.6)
        (x0, y0), (x1, y1) = d["p0"], d["p1"]
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="<|-|>", color=DIM, lw=1, mutation_scale=9, shrinkA=0, shrinkB=0))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        if d["vertical"]:
            ax.text(mx + d["side"] * 0.1, my, d["text"], rotation=90, fontsize=9, color=DIM, ha="right" if d["side"] < 0 else "left", va="center")
        else:
            off = d["side"] * (0.1 + 0.32 * d["stag"])
            ax.text(mx, my + off, d["text"], fontsize=9, color=DIM, ha="center", va="top" if d["side"] < 0 else "bottom")
    if L["sv"]:
        sv = L["sv"]
        ax.annotate("", xy=(sv["x"], 0), xytext=(sv["x"], sv["tail"]), arrowprops=dict(arrowstyle="-|>", color="#1565c0", lw=2.5))
        ax.text(sv["x"], sv["tail"] - 0.03, sv["text"], color="#1565c0", fontsize=10, fontweight="bold", ha="center", va="top")
    ax.plot(0, 0, "ko", ms=4)
    ax.text(-0.1, 0.1, "A", ha="right", fontsize=11, fontweight="bold")
    return _png(fig)


def pressure_figure_png(p, r):
    use_piles = p.get("use_piles", False)
    if use_piles and r.get("pile_results"):
        pr = r["pile_results"]
        loads = [item["load_kg"] for item in pr["pile_loads"]]
        names = [f"P{item['pile_no']}" for item in pr["pile_loads"]]
        allow = pr["pile_cap_allow"]
        fig, ax = plt.subplots(figsize=(7.5, 3.0))
        bars = ax.bar(names, loads, color="#1565c0", width=0.4)
        ax.axhline(allow, color="#c62828", ls="--", lw=1.5)
        ax.text(len(names)/2 - 0.5, allow * 1.02, f"Allowable = {allow:,.0f} kg", ha="center", color="#c62828", fontsize=10)
        ax.set_ylabel("Pile Load (kg)")
        ax.set_ylim(0, max(max(loads) * 1.2, allow * 1.2))
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        return _png(fig)
    else:
        B, qa = p["L1"], p["q_allow"]
        qt, qh = r["q_toe"], r["q_heel"]
        fig, ax = plt.subplots(figsize=(7.5, 3.0))
        top = qa * 1.3
        if np.isfinite(qt) and np.isfinite(qh):
            ax.fill([0, 0, B, B], [0, qt, qh, 0], fc="#90caf9", ec="#1565c0", lw=2)
            top = max(top, max(qt, qh) * 1.25)
            ax.text(0, qt + top * 0.03, f"{qt:.1f} kg/m²", ha="left", color="#0d47a1", fontsize=10)
            ax.text(B, qh + top * 0.03, f"{qh:.1f} kg/m²", ha="right", color="#0d47a1", fontsize=10)
        ax.axhline(qa, color="#c62828", ls="--", lw=1.5)
        ax.text(B / 2, qa + top * 0.02, f"q_allow = {qa:.0f} kg/m²", ha="center", color="#c62828", fontsize=10)
        ax.set_xlim(-0.1, B + 0.1)
        ax.set_ylim(0, top)
        ax.set_xticks([0, B])
        ax.set_xticklabels(["Toe (A)", "Heel"])
        ax.set_ylabel("Bearing Pressure (kg/m²)")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        return _png(fig)
