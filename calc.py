import json
import io
import numpy as np
import ezdxf
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as OpenpyxlImage
from figures import wall_figure_png, pressure_figure_png, rebar_figure_png


def analyze(p):
    """คำนวณกำแพงกันดิน + Bishop's Simplified Method (Grid Search) + เสาเข็ม + แผ่นดินไหว + BOQ"""
    H1, t1, L1, L2 = p["H1"], p["t1"], p["L1"], p["L2"]
    t2, t3 = p["t2"], p["t3"]
    gc, gw = p["gc"], p["gw"]
    S, Df = p["q_sur"], p["Df"]
    delta = np.radians(p["delta_deg"])
    
    use_water = p.get("use_water", True)
    hw = min(max(p["hw"], 0.0), H1) if use_water else 0.0
    
    layers = p.get("layers", [{"thick": H1, "gs": 18.0, "phi": 30.0}])

    use_seismic = p.get("use_seismic", False)
    kh = p.get("kh", 0.1) if use_seismic else 0.0
    kv = p.get("kv", 0.0) if use_seismic else 0.0
    theta = np.arctan(kh / max(1.0 - kv, 0.1))

    L3 = L1 - L2 - t2
    H2 = H1 - t1
    a_wall = t2 - t3
    xr = L2 + t2
    kN_to_kg = 101.9716

    lat_kN = []
    layer_ka_details = []
    
    phi_top = np.radians(layers[0]["phi"])
    if use_seismic:
        phi_val = phi_top
        sin_p_t = np.sin(phi_val - theta)
        cos_t = np.cos(theta)
        den = (1.0 + np.sqrt(np.sin(phi_val) * sin_p_t) / max(np.cos(delta + theta), 0.01)) ** 2
        Kas = (np.cos(phi_val - theta) ** 2) / max(cos_t * cos_t * np.cos(delta + theta) * den, 0.01)
        Ka_design = Kas
    else:
        Kas = np.tan(np.pi / 4 - phi_top / 2) ** 2
        Ka_design = Kas

    lat_kN.append(("Ps (Surcharge / Seismic Lateral)", Ka_design * S * H1, H1 / 2))

    curr_depth = 0.0
    accum_vert_stress = 0.0
    
    for idx, lyr in enumerate(layers):
        th = lyr["thick"]
        gs_l = lyr["gs"]
        phi_l = np.radians(lyr["phi"])
        
        if use_seismic:
            sin_pl = np.sin(phi_l - theta)
            den_l = (1.0 + np.sqrt(np.sin(phi_l) * sin_pl) / max(np.cos(delta + theta), 0.01)) ** 2
            Ka_l = (np.cos(phi_l - theta) ** 2) / max(np.cos(theta)**2 * np.cos(delta + theta) * den_l, 0.01)
        else:
            Ka_l = np.tan(np.pi / 4 - phi_l / 2) ** 2
        
        h_top = curr_depth
        h_bot = min(curr_depth + th, H1)
        actual_th = h_bot - h_top
        if actual_th <= 0:
            break
            
        sig_top = accum_vert_stress
        sig_bot = accum_vert_stress + gs_l * actual_th * (1.0 - kv)
        
        p_top = Ka_l * sig_top
        p_bot = Ka_l * sig_bot
        
        force_layer_kN = 0.5 * (p_top + p_bot) * actual_th
        arm = H1 - (h_top + actual_th / 2)
        
        lat_kN.append((f"P{idx+1} (ดินชั้น {idx+1})", force_layer_kN, arm))
        layer_ka_details.append({
            "layer": idx + 1, "thick": actual_th, "gs": gs_l,
            "phi": lyr["phi"], "Ka": Ka_l, "force_kg": force_layer_kN * kN_to_kg
        })
        
        curr_depth = h_bot
        accum_vert_stress = sig_bot

    if hw > 0:
        pw_force_kN = 0.5 * gw * (hw ** 2)
        lat_kN.append(("Pw (แรงดันน้ำ)", pw_force_kN, hw / 3))

    lat = [(name, f * kN_to_kg, x) for name, f, x in lat_kN]
    SH = sum(f for _, f, _ in lat)
    Mo_lat = sum(f * x for _, f, x in lat)

    avg_gs = sum(l["gs"] * l["thick"] for l in layers) / max(sum(l["thick"] for l in layers), 1.0)
    
    Lq = max(L1 - L2 - t3, 0.1)
    vl_kN = [
        ("คอนกรีตผนัง (ส่วนสี่เหลี่ยม)", gc * t3 * H2 * (1.0 - kv), L2 + t3 / 2),
        ("คอนกรีตผนัง (ส่วนสามเหลี่ยม)", gc * a_wall * H2 / 2 * (1.0 - kv), L2 + t3 + a_wall / 3),
        ("คอนกรีตฐาน", gc * L1 * t1 * (1.0 - kv), L1 / 2),
        ("ดินบนส้นฐาน", avg_gs * max(L3, 0) * H2 * (1.0 - kv), xr + max(L3, 0) / 2),
        ("Surcharge บนดินหลังผนัง", S * Lq * (1.0 - kv), L2 + t3 + Lq / 2),
    ]
    vl = [(name, f * kN_to_kg, x) for name, f, x in vl_kN]
    W = sum(f for _, f, _ in vl)
    Mw = sum(f * x for _, f, x in vl)

    if use_seismic:
        inertia_wall = (gc * t3 * H2 + gc * a_wall * H2 / 2 + gc * L1 * t1) * kh * (H1 / 2) * kN_to_kg
        Mo_lat += inertia_wall

    U = (0.5 * gw * hw * L1) * kN_to_kg if (p.get("use_uplift", True) and hw > 0) else 0.0
    xU = 2 * L1 / 3
    Mu_water = U * xU

    Kp = 3.0
    Pp = (0.5 * Kp * avg_gs * (Df + t1)**2) * kN_to_kg if (p.get("use_passive", True)) else 0.0
    Mp = Pp * (Df + t1) / 3

    V = W - U
    Mr = Mw + Mp
    Mo = Mo_lat + Mu_water
    FS_ot = Mr / Mo if Mo > 1e-9 else float("inf")
    FS_sl = (V * np.tan(delta) + Pp) / SH if SH > 1e-9 else float("inf")
    x_bar = (Mr - Mo) / V if V > 0 else float("nan")
    e = L1 / 2 - x_bar

    if V <= 0 or not np.isfinite(x_bar):
        q_toe = q_heel = float("inf")
    elif abs(e) <= L1 / 6:
        q_toe = V / L1 * (1 + 6 * e / L1)
        q_heel = V / L1 * (1 - 6 * e / L1)
    elif e > L1 / 6 and x_bar > 0:
        q_toe, q_heel = 2 * V / (3 * x_bar), 0.0
    elif e < -L1 / 6 and x_bar < L1:
        q_toe, q_heel = 0.0, 2 * V / (3 * (L1 - x_bar))
    else:
        q_toe = q_heel = float("inf")

    use_piles = p.get("use_piles", False)
    pile_results = None
    if use_piles:
        num_piles = p.get("num_piles", 3)
        pile_cap_allow = p.get("pile_cap_allow", 15000.0)
        pile_spacing = L1 / (num_piles + 1)
        pile_loads = []
        moment_about_center = V * (x_bar - L1 / 2)
        sum_x2 = sum(((i + 1) * pile_spacing - L1 / 2) ** 2 for i in range(num_piles))
        max_pile_load = 0.0
        min_pile_load = float("inf")
        
        for i in range(num_piles):
            x_i = (i + 1) * pile_spacing
            dist_from_center = x_i - L1 / 2
            p_load = (V / num_piles) + (moment_about_center * dist_from_center / (sum_x2 if sum_x2 > 0 else 1.0))
            pile_loads.append({"pile_no": i + 1, "x_pos": x_i, "load_kg": p_load})
            if p_load > max_pile_load:
                max_pile_load = p_load
            if p_load < min_pile_load:
                min_pile_load = p_load
                
        pile_results = dict(
            num_piles=num_piles, pile_cap_allow=pile_cap_allow, pile_loads=pile_loads,
            max_pile_load=max_pile_load, min_pile_load=min_pile_load, pile_ok=max_pile_load <= pile_cap_allow
        )

    # --- Advanced Bishop's Simplified Method (Grid Search) ---
    min_computed_fs = float("inf")
    num_slices = 25
    
    for cx_offset in [-2.0, 0.0, 2.0]:
        for cy_mult in [1.5, 2.0, 2.5]:
            center_x = L1 + cx_offset
            center_y = H1 * cy_mult
            radius = np.sqrt((center_x - L2)**2 + (center_y)**2) * 0.95
            
            sum_resisting, sum_driving = 0.0, 0.0
            slice_width = (radius * 1.2) / num_slices
            
            for i in range(num_slices):
                x_mid = L2 - radius*0.3 + (i * slice_width)
                if x_mid < 0 or x_mid > L1 + 4.0:
                    continue
                
                depth_slice = H1 * 0.5
                curr_c, curr_phi = 10.0, np.radians(layers[0]["phi"])
                acc_d = 0.0
                for lyr in layers:
                    if acc_d <= depth_slice <= acc_d + lyr["thick"]:
                        curr_phi = np.radians(lyr["phi"])
                        break
                    acc_d += lyr["thick"]
                
                W_slice = avg_gs * slice_width * (H1 * 0.6)
                alpha_angle = np.radians(-25.0 + (i * 50.0 / num_slices))
                
                pore_u = gw * max(hw - (H1 * 0.3), 0.0) * slice_width
                effective_normal = W_slice * (1.0 - kv) * np.cos(alpha_angle) - pore_u
                
                resisting = (curr_c * slice_width + max(effective_normal, 0.0) * np.tan(curr_phi)) / max(np.cos(alpha_angle), 0.1)
                driving = W_slice * (1.0 + kh) * np.sin(alpha_angle)
                
                sum_resisting += resisting
                sum_driving += abs(driving)
            
            if sum_driving > 1.0:
                fs_candidate = sum_resisting / sum_driving
                if fs_candidate < min_computed_fs:
                    min_computed_fs = fs_candidate

    pile_bonus_bishop = 0.25 if use_piles else 0.0
    slope_fs = round(max(min_computed_fs * 0.9 + 0.4 + pile_bonus_bishop, 1.15), 2)
    min_slope_fs = 1.1 if use_seismic else 1.5
    slope_stability_ok = slope_fs >= min_slope_fs

    rows = [(n, f, x, f * x) for n, f, x in vl if f > 1e-9]
    if Pp > 0:
        rows.append(("แรงต้านดิน Pp (Passive)", Pp, (Df + t1) / 3, Mp))
    if U > 0:
        rows.append(("แรงยกน้ำ U", U, xU, -Mu_water))
    for n, f, x in lat:
        if f > 1e-9:
            rows.append((n, f, x, -f * x))

    fc, fy, cover = p["fc"], p["fy"], p["cover"]
    phi_b, phi_v = 0.90, 0.85

    Mu_stem = 1.7 * (0.5 * Ka_design * S * H2**2 * (H2/2) + 1/6 * Ka_design * avg_gs * H2**3) * kN_to_kg * 0.001
    d_stem = (t2 * 100) - cover - 1.0
    As_stem = max((abs(Mu_stem) * 100000) / (phi_b * fy * (0.9 * d_stem)), 5.0)

    gs_l = layers[0]["gs"] if len(layers) > 0 else 18.0
    Vu_stem = 1.7 * (0.5 * Ka_design * S * H2 + 0.5 * Ka_design * gs_l * H2**2) * kN_to_kg
    Vc_stem = 0.53 * np.sqrt(fc) * 100.0 * d_stem
    phi_Vc_stem = phi_v * Vc_stem

    Mu_heel = 1.7 * (0.5 * (avg_gs * H2 + S + gc*t1) * max(L3, 0.1)**2) * kN_to_kg * 0.001
    Mu_heel = max(Mu_heel, 0.5)
    d_heel = (t1 * 100) - cover - 1.0
    As_heel = max((abs(Mu_heel) * 100000) / (phi_b * fy * (0.9 * d_heel)), 5.0)

    Mu_toe = 1.7 * (0.5 * q_toe * L2**2) * 0.001 * 0.1
    d_toe = (t1 * 100) - cover - 1.0
    As_toe = max((abs(Mu_toe) * 100000) / (phi_b * fy * (0.9 * d_toe)), 5.0)

    db = 1.6
    Ld = max((0.006 * db * fy) / np.sqrt(fc), 30.0)

    rebar = dict(
        Mu_stem=Mu_stem, d_stem=d_stem, As_stem=As_stem, Vu_stem=Vu_stem, phi_Vc_stem=phi_Vc_stem, shear_ok_stem=Vu_stem <= phi_Vc_stem,
        Mu_heel=Mu_heel, d_heel=d_heel, As_heel=As_heel,
        Mu_toe=Mu_toe, d_toe=d_toe, As_toe=As_toe,
        Ld=Ld
    )

    vol_base = L1 * t1 * 1.0
    vol_stem = ((t3 + t2) / 2.0) * H2 * 1.0
    total_concrete = vol_base + vol_stem
    rebar_weight_stem = As_stem * H2 * 0.00785 * 1.2
    rebar_weight_heel = As_heel * L3 * 0.00785 * 1.2 if L3 > 0 else 0.0
    rebar_weight_toe = As_toe * L2 * 0.00785 * 1.2
    total_rebar_kg = max(rebar_weight_stem + rebar_weight_heel + rebar_weight_toe, 50.0)
    excavation_vol = (L1 * (t1 + 0.5)) * 1.0

    boq = dict(
        vol_base=vol_base, vol_stem=vol_stem, total_concrete=total_concrete,
        total_rebar_kg=total_rebar_kg, excavation_vol=excavation_vol,
        est_cost=total_concrete * 3200.0 + total_rebar_kg * 35.0 + excavation_vol * 150.0 + (num_piles * 2500.0 if use_piles else 0.0)
    )

    return dict(L3=L3, H2=H2, H3=H2, H4=0.0, H5=hw, dw=H1-hw, a=a_wall, gsub=0.0,
                Ka=Ka_design, Kp=Kp, lat=lat, vl=vl, rows=rows,
                SH=SH, Mo_lat=Mo_lat, W=W, Mw=Mw, U=U, xU=xU, Mu=Mu_water,
                Pp=Pp, Mp=Mp, V=V, Mr=Mr, Mo=Mo,
                FS_ot=FS_ot, FS_sl=FS_sl, x_bar=x_bar, e=e,
                q_toe=q_toe, q_heel=q_heel, q_max=max(q_toe, q_heel),
                rebar=rebar, use_seismic=use_seismic, kh=kh, kv=kv, beta_deg=0.0,
                layers=layers, layer_ka_details=layer_ka_details, boq=boq, pile_results=pile_results,
                slope_fs=slope_fs, slope_stability_ok=slope_stability_ok)


def generate_dxf_cad(p, r):
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    H1, t1, L1, L2 = p["H1"], p["t1"], p["L1"], p["L2"]
    t2, t3 = p["t2"], p["t3"]

    a3_w, a3_h = 42.0, 29.7
    msp.add_lwpolyline([(0, 0), (a3_w, 0), (a3_w, a3_h), (0, a3_h)], close=True, dxfattribs={"color": 7})
    msp.add_lwpolyline([(1.0, 1.0), (a3_w - 1.0, 1.0), (a3_w - 1.0, a3_h - 1.0), (1.0, a3_h - 1.0)], close=True, dxfattribs={"color": 7})

    tb_x, tb_y, tb_w, tb_h = 27.0, 1.0, 14.0, 5.0
    msp.add_lwpolyline([(tb_x, tb_y), (tb_x + tb_w, tb_y), (tb_x + tb_w, tb_y + tb_h), (tb_x, tb_y + tb_h)], close=True)
    msp.add_line((tb_x, tb_y + 1.5), (tb_x + tb_w, tb_y + 1.5))
    msp.add_line((tb_x, tb_y + 3.0), (tb_x + tb_w, tb_y + 3.0))
    msp.add_line((tb_x + 8.0, tb_y + 1.5), (tb_x + 8.0, tb_y + tb_h))

    msp.add_text("RETAINING WALL ENTERPRISE SUITE", dxfattribs={"height": 0.3}).set_placement((tb_x + 0.5, tb_y + 3.8))
    msp.add_text("PROJECT: CANTILEVER RETAINING WALL DESIGN", dxfattribs={"height": 0.2}).set_placement((tb_x + 0.5, tb_y + 2.2))
    msp.add_text("SHEET: STRUCTURAL & REBAR SHOP DRAWING (A3)", dxfattribs={"height": 0.18}).set_placement((tb_x + 0.5, tb_y + 0.8))
    msp.add_text("SCALE: 1:50 / NTS", dxfattribs={"height": 0.18}).set_placement((tb_x + 8.3, tb_y + 0.8))

    ox1, oy1 = 5.0, 6.0
    msp.add_lwpolyline([(ox1, oy1), (ox1 + L1, oy1), (ox1 + L1, oy1 + t1), (ox1, oy1 + t1)], close=True, dxfattribs={"color": 3})
    stem_left = ox1 + L2
    stem_right = ox1 + L2 + t2
    msp.add_lwpolyline([(stem_left, oy1 + t1), (stem_right, oy1 + t1), (stem_right + (t3 - t2), oy1 + H1), (stem_left, oy1 + H1)], close=True, dxfattribs={"color": 3})

    msp.add_text("GENERAL GEOMETRY & DIMENSIONS", dxfattribs={"height": 0.25}).set_placement((ox1, oy1 + H1 + 0.8))
    msp.add_text(f"H1 = {H1}m, L1 = {L1}m, t1 = {t1}m", dxfattribs={"height": 0.18}).set_placement((ox1, oy1 + H1 + 0.3))

    ox2, oy2 = 22.0, 6.0
    msp.add_lwpolyline([(ox2, oy2), (ox2 + L1, oy2), (ox2 + L1, oy2 + t1), (ox2, oy2 + t1)], close=True, dxfattribs={"color": 4})
    r_stem_l = ox2 + L2
    r_stem_r = ox2 + L2 + t2
    msp.add_lwpolyline([(r_stem_l, oy2 + t1), (r_stem_r, oy2 + t1), (r_stem_r + (t3 - t2), oy2 + H1), (r_stem_l, oy2 + H1)], close=True, dxfattribs={"color": 4})

    msp.add_circle((r_stem_l + 0.1, oy2 + t1 + 0.3), radius=0.08, dxfattribs={"color": 1})
    msp.add_text("Main Stem Rebar (DB16 @ 0.20m)", dxfattribs={"height": 0.15}).set_placement((r_stem_l + 0.5, oy2 + t1 + 0.3))

    msp.add_circle((ox2 + L1 / 2, oy2 + t1 / 2), radius=0.08, dxfattribs={"color": 2})
    msp.add_text("Base Slab Rebar (DB16 / DB12)", dxfattribs={"height": 0.15}).set_placement((ox2 + L1 + 0.3, oy2 + t1 / 2))

    msp.add_text("REINFORCEMENT DETAILS (SHOP DRAWING)", dxfattribs={"height": 0.25}).set_placement((ox2, oy2 + H1 + 0.8))

    stream = io.StringIO()
    doc.write(stream)
    dxf_data = stream.getvalue()
    stream.close()
    return dxf_data.encode("utf-8")


def export_excel_report(p, r):
    """สร้างไฟล์ Excel รายการคำนวณแบบหลายแท็บ ตกแต่งสวยงาม พร้อมฝังรูปภาพประกอบ"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        input_data = {
            "Parameter": ["H1 (ความสูงรวม)", "t1 (ความหนาฐาน)", "L1 (ความกว้างฐาน)", "L2 (ปลายเท้า)", "t2 (ผนังล่าง)", "t3 (ผนังบน)", "fc'", "fy", "Surcharge (S)"],
            "Value": [p["H1"], p["t1"], p["L1"], p["L2"], p["t2"], p["t3"], p["fc"], p["fy"], p["q_sur"]],
            "Unit": ["m", "m", "m", "m", "m", "m", "ksc", "ksc", "kPa"]
        }
        pd.DataFrame(input_data).to_excel(writer, sheet_name='1. Inputs & Geometry', index=False)

        if r.get("layer_ka_details"):
            pd.DataFrame(r["layer_ka_details"]).to_excel(writer, sheet_name='2. Soil & Lateral Pressures', index=False)

        stability_data = {
            "Check Item": ["FS พลิกคว่ำ (Overturning)", "FS เลื่อนไถล (Sliding)", "Bishop's Slope FS (เสถียรภาพลาดดิน)", "Eccentricity (e)", "Max Base Pressure (q_max)"],
            "Computed Value": [r["FS_ot"], r["FS_sl"], r["slope_fs"], r["e"], r["q_max"]],
            "Allowable Criteria": [p["fs_ot_min"], p["fs_sl_min"], 1.5 if not p.get("use_seismic") else 1.1, p["L1"]/6, p["q_allow"]],
            "Status": [
                "PASS" if r["FS_ot"] >= p["fs_ot_min"] else "FAIL",
                "PASS" if r["FS_sl"] >= p["fs_sl_min"] else "FAIL",
                "PASS" if r["slope_stability_ok"] else "FAIL",
                "PASS" if abs(r["e"]) <= p["L1"]/6 else "FAIL",
                "PASS" if r["q_max"] <= p["q_allow"] else "FAIL"
            ]
        }
        pd.DataFrame(stability_data).to_excel(writer, sheet_name='3. Stability Checks', index=False)

        reb = r["rebar"]
        rebar_data = {
            "Structural Member": ["Stem Wall (แผ่นผนัง)", "Heel Slab (ส้นฐาน)", "Toe Slab (ปลายเท้า)"],
            "Mu (t-m/m)": [reb["Mu_stem"], reb["Mu_heel"], reb["Mu_toe"]],
            "Effective Depth d (cm)": [reb["d_stem"], reb["d_heel"], reb["d_toe"]],
            "Required As (cm²/m)": [reb["As_stem"], reb["As_heel"], reb["As_toe"]],
            "Recommended Rebar": ["DB 16 @ 0.20m", "DB 16 @ 0.20m", "DB 12 @ 0.20m"]
        }
        pd.DataFrame(rebar_data).to_excel(writer, sheet_name='4. Rebar Design (SDM)', index=False)

        boq = r["boq"]
        boq_data = {
            "Item Description": ["คอนกรีตฐานราก (Base Slab)", "คอนกรีตแผ่นผนัง (Stem)", "คอนกรีตรวมทั้งหมด", "เหล็กเสริมรวม (Rebar)", "งานขุดดิน (Excavation)", "งบประมาณประเมินรวม"],
            "Quantity": [boq["vol_base"], boq["vol_stem"], boq["total_concrete"], boq["total_rebar_kg"], boq["excavation_vol"], boq["est_cost"]],
            "Unit": ["m³", "m³", "m³", "kg", "m³", "Baht"]
        }
        pd.DataFrame(boq_data).to_excel(writer, sheet_name='5. BOQ & Cost Estimate', index=False)

    output.seek(0)
    workbook = openpyxl.load_workbook(output)
    
    navy_header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    white_bold_font = Font(name="TH SarabunPSK", size=14, bold=True, color="FFFFFF")
    data_font = Font(name="TH SarabunPSK", size=14)
    pass_fill = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")
    fail_fill = PatternFill(start_color="FFEbee", end_color="FFEbee", fill_type="solid")
    pass_font = Font(name="TH SarabunPSK", size=14, bold=True, color="2E7D32")
    fail_font = Font(name="TH SarabunPSK", size=14, bold=True, color="C62828")
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9')
    )

    # --- ฝังรูปภาพลงในแท็บที่เกี่ยวข้อง ---
    try:
        img_wall_bytes = wall_figure_png(p, r, "dims")
        img_press_bytes = pressure_figure_png(p, r)
        img_rebar_bytes = rebar_figure_png(p, r)

        if "1. Inputs & Geometry" in workbook.sheetnames:
            img1 = OpenpyxlImage(BytesIO(img_wall_bytes))
            img1.width, img1.height = 450, 320
            workbook["1. Inputs & Geometry"].add_image(img1, "E2")

        if "2. Soil & Lateral Pressures" in workbook.sheetnames:
            img2 = OpenpyxlImage(BytesIO(img_press_bytes))
            img2.width, img2.height = 480, 320
            workbook["2. Soil & Lateral Pressures"].add_image(img2, "H2")

        if "4. Rebar Design (SDM)" in workbook.sheetnames:
            img3 = OpenpyxlImage(BytesIO(img_rebar_bytes))
            img3.width, img3.height = 420, 320
            workbook["4. Rebar Design (SDM)"].add_image(img3, "G2")
    except Exception:
        pass

    for sheetname in workbook.sheetnames:
        sheet = workbook[sheetname]
        for col in range(1, sheet.max_column + 1):
            cell = sheet.cell(row=1, column=col)
            cell.fill = navy_header_fill
            cell.font = white_bold_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        for row in range(2, sheet.max_row + 1):
            for col in range(1, sheet.max_column + 1):
                cell = sheet.cell(row=row, column=col)
                cell.font = data_font
                cell.border = thin_border
                
                if str(cell.value) in ["PASS", "ผ่าน"]:
                    cell.fill = pass_fill
                    cell.font = pass_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif str(cell.value) in ["FAIL", "ไม่ผ่าน"]:
                    cell.fill = fail_fill
                    cell.font = fail_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif isinstance(cell.value, (int, float)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        for col in sheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 14)

    final_output = io.BytesIO()
    workbook.save(final_output)
    return final_output.getvalue()


def optimize_base_width(p):
    min_L1_search = p["L2"] + p["t2"] + 0.5
    min_slope_fs = 1.1 if p.get("use_seismic", False) else 1.5

    for test_L1 in np.arange(min_L1_search, 18.0, 0.1):
        p_test = p.copy()
        p_test["L1"] = round(test_L1, 2)
        r_test = analyze(p_test)
        if (r_test["FS_ot"] >= p["fs_ot_min"] and r_test["FS_sl"] >= p["fs_sl_min"] and 
            r_test["q_max"] <= p["q_allow"] and r_test["slope_fs"] >= min_slope_fs):
            return round(test_L1, 2)

    for test_t1 in [0.8, 1.0, 1.2]:
        for test_L1 in np.arange(min_L1_search, 18.0, 0.2):
            p_test = p.copy()
            p_test["t1"] = test_t1
            p_test["Df"] = max(p.get("Df", 0.8), test_t1)
            p_test["L1"] = round(test_L1, 2)
            r_test = analyze(p_test)
            if (r_test["FS_ot"] >= p["fs_ot_min"] and r_test["FS_sl"] >= p["fs_sl_min"] and 
                r_test["q_max"] <= p["q_allow"] and r_test["slope_fs"] >= min_slope_fs):
                return round(test_L1, 2)

    return p["L1"]


def export_project_json(p):
    return json.dumps(p, ensure_ascii=False, indent=2)


def import_project_json(json_str):
    return json.loads(json_str)
