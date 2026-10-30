import json
import numpy as np
import pandas as pd
import streamlit as st

from calc import analyze, export_project_json, generate_dxf_cad, import_project_json, optimize_base_width, export_excel_report
from figures import pressure_figure, rebar_figure_png, wall_figure
from report import build_report

st.set_page_config(page_title="Retaining Wall Enterprise Suite", layout="wide")


def card(title, value, criterion, ok):
    color = "#2e7d32" if ok else "#c62828"
    bg = "#e8f5e9" if ok else "#ffebee"
    badge = "ผ่าน" if ok else "ไม่ผ่าน"
    return f"""
    <div style="border-left:6px solid {color};background:{bg};padding:14px 16px;
                border-radius:10px;height:130px">
      <div style="font-size:13px;color:#555">{title}</div>
      <div style="font-size:30px;font-weight:700;color:{color};line-height:1.3">{value}</div>
      <div style="font-size:12px;color:#555">{criterion} &nbsp;|&nbsp;
        <b style="color:{color}">{badge}</b></div>
    </div>"""


st.title("Retaining Wall & Geotechnical Enterprise Suite")
st.caption("ระบบออกแบบกำแพงกันดินครบวงจร + Bishop's Slip Circle + Excel & CAD (.dxf) Export + บันทึกโปรเจกต์ JSON")

with st.sidebar:
    st.header("📂 จัดการโปรเจกต์ (JSON)")
    uploaded_file = st.file_uploader("เปิดไฟล์โปรเจกต์ (.json)", type=["json"])
    loaded_params = None
    if uploaded_file is not None:
        try:
            loaded_params = json.load(uploaded_file)
            st.success("โหลดข้อมูลโปรเจกต์สำเร็จ!")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")

    st.markdown("---")
    st.header("ข้อมูลนำเข้าหลัก")
    def_val = lambda key, fallback: loaded_params.get(key, fallback) if loaded_params else fallback

    if "opt_L1" not in st.session_state:
        st.session_state.opt_L1 = def_val("L1", 4.5)

    st.subheader("รูปทรงกำแพง (m)")
    H1 = st.number_input("ความสูงรวม H1", 2.0, 15.0, float(def_val("H1", 5.0)), 0.1)
    t1 = st.number_input("ความหนาฐาน t1", 0.2, 3.0, float(def_val("t1", 0.6)), 0.05)
    L2 = st.number_input("ปลายเท้า L2", 0.0, 5.0, float(def_val("L2", 0.75)), 0.05)
    t2 = st.number_input("ความหนาผนังส่วนล่าง t2", 0.2, 3.0, float(def_val("t2", 0.6)), 0.05)
    t3 = st.number_input("ความหนาผนังส่วนบน t3", 0.1, 2.0, float(def_val("t3", 0.3)), 0.05)

    st.subheader("คุณสมบัติชั้นดินหลังกำแพง")
    saved_layers = def_val("layers", [{"thick": 5.0, "gs": 18.0, "phi": 30.0}])
    num_layers = st.selectbox("เลือกจำนวนชั้นดิน", [1, 2, 3], index=min(len(saved_layers)-1, 2) if len(saved_layers)>0 else 0)
    st.markdown("---")

    layers = []
    th1 = st.number_input("ความหนาชั้น 1 (m)", 0.1, float(H1), float(saved_layers[0]["thick"]), 0.1)
    gs1 = st.number_input("หน่วยน้ำหนักดิน 1 (kN/m³)", 12.0, 24.0, float(saved_layers[0]["gs"]), 0.5)
    phi1 = st.slider("มุมเสียดทานดิน 1 (φ°)", 15, 40, int(saved_layers[0]["phi"]))
    layers.append({"thick": th1, "gs": gs1, "phi": phi1})

    if num_layers >= 2:
        rem2 = max(float(H1) - th1, 0.5)
        d2 = saved_layers[1] if len(saved_layers) > 1 else {"thick": rem2, "gs": 19.0, "phi": 32.0}
        th2 = st.number_input("ความหนาชั้น 2 (m)", 0.1, float(H1), float(d2["thick"]), 0.1)
        gs2 = st.number_input("หน่วยน้ำหนักดิน 2 (kN/m³)", 12.0, 24.0, float(d2["gs"]), 0.5)
        phi2 = st.slider("มุมเสียดทานดิน 2 (φ°)", 15, 40, int(d2["phi"]))
        layers.append({"thick": th2, "gs": gs2, "phi": phi2})

    if num_layers == 3:
        sum_prev = th1 + th2
        def_th3 = max(float(H1) - sum_prev, 0.5)
        d3 = saved_layers[2] if len(saved_layers) > 2 else {"thick": def_th3, "gs": 20.0, "phi": 35.0}
        th3 = st.number_input("ความหนาชั้น 3 (m)", 0.1, float(H1), float(d3["thick"]), 0.1)
        gs3 = st.number_input("หน่วยน้ำหนักดิน 3 (kN/m³)", 12.0, 24.0, float(d3["gs"]), 0.5)
        phi3 = st.slider("มุมเสียดทานดิน 3 (φ°)", 15, 40, int(d3["phi"]))
        layers.append({"thick": th3, "gs": gs3, "phi": phi3})

    st.subheader("วิเคราะห์แรงแผ่นดินไหว (Seismic)")
    use_seismic = st.checkbox("คิดแรงแผ่นดินไหว", value=bool(def_val("use_seismic", False)))
    kh = st.number_input("สัมประสิทธิ์ความเร่งราบ kh", 0.0, 0.5, float(def_val("kh", 0.1)), 0.02, disabled=not use_seismic)
    kv = st.number_input("สัมประสิทธิ์ความเร่งดิ่ง kv", 0.0, 0.3, float(def_val("kv", 0.0)), 0.02, disabled=not use_seismic)

    st.subheader("ระบบฐานรากและแรงต้านทาน")
    use_passive = st.checkbox("คิดแรงต้านดินด้านหน้า (Passive Pp)", value=bool(def_val("use_passive", True)))
    Df = st.number_input("ความลึกฝังดินด้านหน้า Df (m)", 0.0, 3.0, float(def_val("Df", 0.8)), 0.1, disabled=not use_passive)
    
    use_piles = st.checkbox("ใช้เสาเข็มรองรับฐานราก", value=bool(def_val("use_piles", False)))
    num_piles = st.number_input("จำนวนแถวเสาเข็มใต้ฐาน", 2, 10, int(def_val("num_piles", 3)), 1, disabled=not use_piles)
    pile_cap_allow = st.number_input("กำลังรับน้ำหนักปลอดภัยต่อต้น (kg/ต้น)", 1000.0, 100000.0, float(def_val("pile_cap_allow", 15000.0)), 500.0, disabled=not use_piles)

    st.subheader("น้ำใต้ดินและฐานราก")
    use_water = st.checkbox("มีน้ำใต้ดินหลังกำแพง", value=bool(def_val("use_water", True)))
    hw = st.number_input("ระดับน้ำสูงจากใต้ฐาน H5 (m)", 0.0, float(H1), float(def_val("hw", 2.0)), 0.1, disabled=not use_water)
    use_uplift = st.checkbox("คิดแรงยกน้ำใต้ดิน (Uplift)", value=bool(def_val("use_uplift", True)), disabled=not use_water)
    gw = st.number_input("γ น้ำ (kN/m³)", 9.0, 10.5, float(def_val("gw", 9.81)), 0.01)
    delta_deg = st.slider("มุมเสียดทานใต้ฐาน δ (°)", 10, 35, int(def_val("delta_deg", 22)))
    q_sur = st.number_input("Surcharge S (kPa)", 0.0, 50.0, float(def_val("q_sur", 10.0)), 1.0)

    st.subheader("วัสดุคอนกรีตและเหล็กเสริม")
    gc = st.number_input("γ คอนกรีต (kN/m³)", 20.0, 26.0, float(def_val("gc", 24.0)), 0.5)
    fc = st.number_input("กำลังอัดคอนกรีต f'c (ksc)", 180.0, 400.0, float(def_val("fc", 240.0)), 10.0)
    bar_type = st.selectbox("ชนิดเหล็กเสริม", ["SD40 (fy=4000 ksc)", "SD30 (fy=3000 ksc)", "SR24 (fy=2400 ksc)"])
    fy_map = {"SD40 (fy=4000 ksc)": 4000.0, "SD30 (fy=3000 ksc)": 3000.0, "SR24 (fy=2400 ksc)": 2400.0}
    fy = fy_map[bar_type]
    cover = st.number_input("ระยะหุ้มคอนกรีต cover (cm)", 3.0, 10.0, float(def_val("cover", 7.5)), 0.5)

    st.subheader("เกณฑ์ตรวจสอบ")
    q_allow = st.number_input("กำลังแบกทานที่ยอมให้ (kg/m²)", 500.0, 50000.0, float(def_val("q_allow", 15000.0)), 500.0, key="qa_main")
    fs_ot_min = st.number_input("FS พลิกคว่ำ ขั้นต่ำ", 1.0, 3.0, float(def_val("fs_ot_min", 2.0)), 0.1, key="fso_main")
    fs_sl_min = st.number_input("FS เลื่อนไถล ขั้นต่ำ", 1.0, 3.0, float(def_val("fs_sl_min", 1.5)), 0.1, key="fss_main")

    if st.button("🔍 Auto-Optimize ความกว้างฐาน L1 (ทุกเคส)"):
        p_current = dict(
            H1=H1, t1=t1, L1=4.5, L2=L2, t2=t2, t3=t3, gc=gc, gw=gw,
            delta_deg=delta_deg, q_sur=q_sur, use_water=use_water, hw=hw,
            use_uplift=use_uplift, use_passive=use_passive, Df=Df, q_allow=q_allow,
            fs_ot_min=fs_ot_min, fs_sl_min=fs_sl_min, fc=fc, fy=fy, cover=cover,
            layers=layers, use_piles=use_piles, num_piles=num_piles, pile_cap_allow=pile_cap_allow,
            use_seismic=use_seismic, kh=kh, kv=kv
        )
        best = optimize_base_width(p_current)
        st.session_state.opt_L1 = float(best)
        st.success(f"พบ L1 ที่เหมาะสมคือ: {best:.2f} m")

    L1 = st.number_input("ความกว้างฐาน L1", 1.0, 15.0, float(st.session_state.opt_L1), 0.1)

current_params = dict(
    H1=H1, t1=t1, L1=L1, L2=L2, t2=t2, t3=t3, gc=gc, gw=gw,
    delta_deg=delta_deg, q_sur=q_sur, use_water=use_water, hw=hw,
    use_uplift=use_uplift, use_passive=use_passive, Df=Df, q_allow=q_allow,
    fs_ot_min=fs_ot_min, fs_sl_min=fs_sl_min, fc=fc, fy=fy, cover=cover,
    layers=layers, use_piles=use_piles, num_piles=num_piles, pile_cap_allow=pile_cap_allow,
    use_seismic=use_seismic, kh=kh, kv=kv
)

st.sidebar.markdown("---")
st.sidebar.download_button("💾 บันทึกโปรเจกต์ (.json)", data=export_project_json(current_params), file_name="retaining_wall_project.json", mime="application/json")

if L1 - L2 - t2 <= 0:
    st.error("ต้องให้ L1 มากกว่า L2 + t2")
    st.stop()
if t3 > t2:
    st.error("t3 ต้องไม่มากกว่า t2")
    st.stop()
if t1 >= H1:
    st.error("t1 ต้องน้อยกว่า H1")
    st.stop()

r = analyze(current_params)

ok_ot = r["FS_ot"] >= fs_ot_min
ok_sl = r["FS_sl"] >= fs_sl_min
ok_e = bool(np.isfinite(r["e"])) and abs(r["e"]) <= L1 / 6
ok_q = bool(np.isfinite(r["q_max"])) and r["q_max"] <= q_allow
ok_shear = r["rebar"]["shear_ok_stem"]
ok_pile = r["pile_results"]["pile_ok"] if use_piles else True
ok_slope = r["slope_stability_ok"]
all_ok = ok_ot and ok_sl and ok_e and (ok_q or use_piles) and ok_shear and ok_pile and ok_slope

if all_ok:
    st.success("ผ่านทุกเกณฑ์ตรวจสอบเสถียรภาพ (รวมวิธี Bishop's Slip Circle)")
else:
    st.error("มีบางเกณฑ์ไม่ผ่าน ลองตรวจสอบพารามิเตอร์หรือกด Auto-Optimize ใน Sidebar")

# --- Metric Cards ---
c1, c2, c3, c4 = st.columns(4)
c1.markdown(card("FS การพลิกคว่ำ", f"{r['FS_ot']:.2f}", f"เกณฑ์ ≥ {fs_ot_min}", ok_ot), unsafe_allow_html=True)
c2.markdown(card("FS การเลื่อนไถล", f"{r['FS_sl']:.2f}", f"เกณฑ์ ≥ {fs_sl_min}", ok_sl), unsafe_allow_html=True)
c3.markdown(card("Bishop's Slope FS", f"{r['slope_fs']:.2f}", f"เกณฑ์ ≥ {1.1 if use_seismic else 1.5}", ok_slope), unsafe_allow_html=True)
if use_piles:
    c4.markdown(card("Max Pile Load", f"{r['pile_results']['max_pile_load']:.1f} kg", f"เกณฑ์ ≤ {pile_cap_allow:,.0f} kg", ok_pile), unsafe_allow_html=True)
else:
    qtxt = f"{r['q_max']:.1f} kg/m²" if np.isfinite(r["q_max"]) else "-"
    c4.markdown(card("q max ใต้ฐาน", qtxt, f"เกณฑ์ ≤ {q_allow:.0f} kg/m²", ok_q), unsafe_allow_html=True)

st.write("")

# --- Tabs Navigation ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 1. ภาพรวมและรูปทรงกำแพง", 
    "📊 2. เสถียรภาพและแรงดัน", 
    "🏗️ 3. ออกแบบโครงสร้างและเหล็กเสริม", 
    "⚖️ 4. เปรียบเทียบทางเลือก (Scenario)", 
    "📄 5. รายงานและ BOQ"
])

with tab1:
    st.subheader("ภาพตัดกำแพงและมิติเรขาคณิต")
    st.plotly_chart(wall_figure(current_params, r), use_container_width=True, config={"scrollZoom": True})

with tab2:
    st.subheader("แผนภาพแรงดันดินและแรงกระทำ")
    st.plotly_chart(pressure_figure(current_params, r), use_container_width=True)

with tab3:
    st.subheader("การออกแบบหน้าตัดคอนกรีตและเหล็กเสริม (Strength Design Method - SDM)")
    rebar = r["rebar"]
    
    col_img, col_txt = st.columns([1, 1])
    with col_img:
        st.subheader("ภาพตัดรายละเอียดการเสริมเหล็ก")
        st.image(rebar_figure_png(current_params, r), caption="รูปแสดงตำแหน่งการเสริมเหล็กหลัก", use_container_width=True)
    with col_txt:
        st.subheader("สรุปผลการออกแบบ:")
        st.markdown(
            f"- **เหล็กแผ่นผนัง (Stem):** DB 16 @ 0.20 m (As = {rebar['As_stem']:.2f} cm²/m)  \n"
            f"- **ตรวจสอบแรงเฉือนโคนผนัง:** Vu = {rebar['Vu_stem']:.1f} kg/m ≤ φVc = {rebar['phi_Vc_stem']:.1f} kg/m ⇒ **{'ผ่าน' if rebar['shear_ok_stem'] else 'ไม่ผ่าน'}**  \n"
            f"- **เหล็กส้นฐาน (Heel):** DB 16 @ 0.20 m (As = {rebar['As_heel']:.2f} cm²/m)  \n"
            f"- **เหล็กปลายเท้า (Toe):** DB 12 @ 0.20 m (As = {rebar['As_toe']:.2f} cm²/m)  \n"
            f"- **ระยะทาบเหล็กพัฒนา (Ld):** {rebar['Ld']:.1f} cm"
        )

    st.markdown("---")
    st.subheader("📝 รายละเอียดสูตรและขั้นตอนการคำนวณอย่างละเอียด")
    
    with st.expander("1. การออกแบบแผ่นผนัง (Stem Wall Flexure & Shear)", expanded=True):
        st.markdown(
            f"* **โมเมนต์ดัดประลัย (Mu):** คำนวณจากแรงดันดินด้านข้างและ Surcharge คูณตัวคูณน้ำหนักบรรทัด 1.7  \n"
            f"  ⇒ Mu-stem = {rebar['Mu_stem']:.2f} t-m/m  \n"
            f"* **ความลึกประสิทธิผล (d):** จากความหนาผนัง t2 = {t2*100:.0f} cm หักระยะหุ้มคอนกรีตและกึ่งกลางเหล็ก  \n"
            f"  ⇒ d = {t2*100} − {cover} − 1.0 = {rebar['d_stem']:.1f} cm  \n"
            f"* **พื้นที่เหล็กเสริมดัด (As):** คำนวณตามวิธีกำลัง (SDM) ด้วยสมการ As = [Mu × 10⁵] / [φ × fy × 0.9 × d]  \n"
            f"  ⇒ As = [({rebar['Mu_stem']:.2f}) × 10⁵] / [0.90 × {fy} × (0.9 × {rebar['d_stem']:.1f})] = {rebar['As_stem']:.2f} cm²/m  \n"
            f"* **การตรวจสอบแรงเฉือน (Vu ≤ φVc):**  \n"
            f"  * แรงเฉือนประลัย Vu = {rebar['Vu_stem']:.1f} kg/m  \n"
            f"  * แรงเฉือนที่คอนกรีตรับได้ φVc = {rebar['phi_Vc_stem']:.1f} kg/m (โดย φ = 0.85)  \n"
            f"  * ผลการตรวจสอบ: **{'ผ่านเกณฑ์แรงเฉือน ไม่ต้องใช้เหล็กปลอก' if rebar['shear_ok_stem'] else 'ไม่ผ่านเกณฑ์แรงเฉือน'}**"
        )

    with st.expander("2. การออกแบบส้นฐาน (Heel Slab Design)"):
        st.markdown(
            f"* **โมเมนต์ดัดประลัย (Mu):** เกิดจากน้ำหนักดินบนส้นฐาน น้ำหนักคอนกรีต และ Surcharge หักด้วยแรงดันแบกทานใต้ฐาน  \n"
            f"  ⇒ Mu-heel = {rebar['Mu_heel']:.2f} t-m/m  \n"
            f"* **ความลึกประสิทธิผล (d):** จากความหนาฐาน t1 = {t1*100:.0f} cm  \n"
            f"  ⇒ d = {t1*100} − {cover} − 1.0 = {rebar['d_heel']:.1f} cm  \n"
            f"* **พื้นที่เหล็กเสริมส้นฐาน (As):**  \n"
            f"  ⇒ As = {rebar['As_heel']:.2f} cm²/m (แนะนำเสริมเหล็ก DB 16 @ 0.20 m)"
        )

    with st.expander("3. การออกแบบปลายเท้า (Toe Slab Design)"):
        st.markdown(
            f"* **โมเมนต์ดัดประลัย (Mu):** เกิดจากแรงดันแบกทานใต้ฐานบริเวณปลายเท้า (q_toe)  \n"
            f"  ⇒ Mu-toe = {rebar['Mu_toe']:.2f} t-m/m  \n"
            f"* **ความลึกประสิทธิผล (d):**  \n"
            f"  ⇒ d = {t1*100} − {cover} − 1.0 = {rebar['d_toe']:.1f} cm  \n"
            f"* **พื้นที่เหล็กเสริมปลายเท้า (As):**  \n"
            f"  ⇒ As = {rebar['As_toe']:.2f} cm²/m (แนะนำเสริมเหล็ก DB 12 @ 0.20 m)"
        )

    with st.expander("4. ระยะฝังตัวและทาบเหล็ก (Development Length - Ld)"):
        st.markdown(
            f"* คำนวณตามมาตรฐาน ACI / วสท. สำหรับเหล็กข้ออ้อย: Ld = [0.006 × db × fy] / [√(f'c)]  \n"
            f"  ⇒ Ld = [0.006 × 1.6 × {fy}] / [√({fc})] = {rebar['Ld']:.1f} cm"
        )

with tab4:
    st.subheader("⚖️ ระบบเปรียบเทียบทางเลือก (Scenario Comparison)")
    if "scenarios" not in st.session_state:
        st.session_state.scenarios = []
    sc_name = st.text_input("ชื่อทางเลือก", f"เคสที่ {len(st.session_state.scenarios)+1}")
    if st.button("➕ บันทึกเคสนี้ลงตารางเปรียบเทียบ"):
        st.session_state.scenarios.append({"name": sc_name, "L1": L1, "piles": "ใช้" if use_piles else "ไม่ใช้", "FS_ot": r["FS_ot"], "FS_sl": r["FS_sl"], "Slope_FS": r["slope_fs"], "Cost": r["boq"]["est_cost"]})
        st.success(f"บันทึก '{sc_name}' สำเร็จ!")
    if len(st.session_state.scenarios) > 0:
        st.dataframe(pd.DataFrame(st.session_state.scenarios), hide_index=True, use_container_width=True)

with tab5:
    st.subheader("ถอดปริมาณวัสดุ BOQ รายงาน Word, Excel และส่งออก CAD (.dxf)")
    boq = r["boq"]
    bc1, bc2, bc3, bc4 = st.columns(4)
    bc1.metric("คอนกรีตรวม", f"{boq['total_concrete']:.2f} m³")
    bc2.metric("เหล็กเสริมรวม", f"{boq['total_rebar_kg']:.1f} kg")
    bc3.metric("งานขุดดิน", f"{boq['excavation_vol']:.2f} m³")
    bc4.metric("งบประมาณประเมิน", f"{boq['est_cost']:,.0f} บาท")

    st.markdown("---")
    
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button("📐 ดาวน์โหลดแบบแปลน CAD (.dxf)", data=generate_dxf_cad(current_params, r), file_name="retaining_wall_shop_drawing.dxf", mime="application/dxf", type="secondary")
    with col_dl2:
        st.download_button("📊 ดาวน์โหลดรายการคำนวณ Excel (.xlsx)", data=export_excel_report(current_params, r), file_name="retaining_wall_calculation_sheet.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="secondary")

    st.markdown("---")
    rc1, rc2, rc3 = st.columns(3)
    project = rc1.text_input("ชื่อโครงการ", "โครงการออกแบบกำแพงกันดิน Enterprise Suite")
    designer = rc2.text_input("ผู้ออกแบบ", "")
    checker = rc3.text_input("ผู้ตรวจสอบ", "")

    checks = dict(ot=ok_ot, sl=ok_sl, e=ok_e, q=ok_q, shear=ok_shear, pile=ok_pile, slope=ok_slope)
    st.download_button(
        "📥 ดาวน์โหลดรายงาน (.docx)",
        data=build_report(current_params, r, checks, project, designer, checker),
        file_name="retaining_wall_enterprise_report.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
    )
