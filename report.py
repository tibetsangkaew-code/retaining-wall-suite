from datetime import date
from io import BytesIO

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from figures import pressure_figure_png, rebar_figure_png, wall_figure_png

FONT = "TH Sarabun PSK"
NAVY = "1F4E79"


def _fmt(run, size=16, bold=False, color=None, italic=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), FONT)
    szcs = OxmlElement("w:szCs")
    szcs.set(qn("w:val"), str(int(size * 2)))
    rpr.insert_element_before(
        szcs, "w:highlight", "w:u", "w:effect", "w:bdr", "w:shd", "w:fitText",
        "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang", "w:eastAsianLayout",
        "w:specVanish", "w:oMath")
    if bold:
        bcs = OxmlElement("w:bCs")
        rpr.insert_element_before(
            bcs, "w:i", "w:iCs", "w:caps", "w:smallCaps", "w:strike", "w:dstrike",
            "w:outline", "w:shadow", "w:emboss", "w:imprint", "w:noProof",
            "w:snapToGrid", "w:vanish", "w:webHidden", "w:color", "w:spacing",
            "w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight",
            "w:u", "w:effect", "w:bdr", "w:shd", "w:fitText", "w:vertAlign",
            "w:rtl", "w:cs", "w:em", "w:lang", "w:eastAsianLayout",
            "w:specVanish", "w:oMath")


def _shade(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def _para(doc, text="", size=16, bold=False, color=None, align=None,
          indent=0.0, space_after=3, italic=False, keep_next=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.keep_with_next = keep_next
    if indent:
        p.paragraph_format.left_indent = Cm(indent)
    if align:
        p.alignment = align
    if text:
        _fmt(p.add_run(text), size, bold, color, italic)
    return p


def _heading(doc, text):
    p = _para(doc, text, size=18, bold=True, color=NAVY, space_after=4, keep_next=True)
    p.paragraph_format.space_before = Pt(12)
    ppr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (("val", "single"), ("sz", "12"), ("space", "2"), ("color", NAVY)):
        bottom.set(qn("w:" + k), v)
    bdr.append(bottom)
    ppr.append(bdr)


def _eq(doc, text):
    _para(doc, text, size=16, indent=0.8, space_after=2)


def _table(doc, header, rows, widths, num_cols=()):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        _shade(c, NAVY)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _fmt(p.add_run(h), 16, True, "FFFFFF")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            fill = None
            if isinstance(v, tuple):
                v, fill = v
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = (WD_ALIGN_PARAGRAPH.RIGHT if i in num_cols
                           else WD_ALIGN_PARAGRAPH.LEFT)
            _fmt(p.add_run(str(v)), 15, bold=bool(fill))
            if fill:
                _shade(cells[i], fill)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
    _para(doc, "", space_after=4)
    return t


def _picture(doc, png_bytes, width_cm, caption):
    doc.add_picture(BytesIO(png_bytes), width=Cm(width_cm))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.paragraphs[-1].paragraph_format.keep_with_next = True
    _para(doc, caption, 15, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)


def build_report(p, r, checks, project="", designer="", checker=""):
    H1, t1, L1, L2, t2, t3, fc, fy, cover = p["H1"], p["t1"], p["L1"], p["L2"], p["t2"], p["t3"], p["fc"], p["fy"], p["cover"]
    use_piles = p.get("use_piles", False)
    use_seismic = p.get("use_seismic", False)
    pile_results = r.get("pile_results", None)
    layer_ka_details = r.get("layer_ka_details", [])
    boq = r["boq"]
    L3, H2, H5 = r["L3"], r["H2"], r["H5"]
    rebar = r["rebar"]

    dims_png = wall_figure_png(p, r, "dims")
    forces_png = wall_figure_png(p, r, "forces")
    press_png = pressure_figure_png(p, r)
    rebar_png = rebar_figure_png(p, r)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin = sec.bottom_margin = Cm(2)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(16)

    _para(doc, "รายการคำนวณกำแพงกันดินและเสถียรภาพ (Enterprise Suite)", 22, True, NAVY, WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    _para(doc, "Retaining Wall Calculation Sheet (Bishop's Slip Circle, CAD & BOQ)", 15,
          color="666666", align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)
    _table(doc, ["หัวข้อ", "รายละเอียด"], [
        ("โครงการ", project or "-"),
        ("ผู้ออกแบบ", designer or "-"),
        ("ผู้ตรวจสอบ", checker or "-"),
        ("วันที่", date.today().strftime("%d/%m/%Y")),
    ], [4, 13])

    _heading(doc, "1. มาตรฐานและข้อกำหนดอ้างอิง")
    for std in [
        "กฎกระทรวงว่าด้วยการออกแบบโครงสร้างอาคารและรับน้ำหนัก",
        "มาตรฐานสมาคมวิศวกรรมสถานแห่งประเทศไทย (วสท. 1008) - วิธีกำลัง (SDM)",
        "การวิเคราะห์เสถียรภาพลาดดินเชิงลึกวิธี Bishop's Simplified Method และ Mononobe-Okabe",
    ]:
        _para(doc, "•  " + std, size=15, indent=0.5, space_after=2)

    _heading(doc, "2. ข้อมูลนำเข้าคุณสมบัติชั้นดิน")
    soil_rows = [(f"ชั้นที่ {l['layer']}", f"{l['thick']:.2f}", f"{l['gs']:.1f}", f"{l['phi']:.1f}°", f"{l['Ka']:.3f}", f"{l['force_kg']:.1f}") for l in layer_ka_details]
    _table(doc, ["ชั้นดิน", "ความหนา (m)", "γ (kN/m³)", "φ (°)", "Ka/Kas", "แรงลัพธ์ (kg/m)"],
           soil_rows, [3, 3, 3, 3, 2.5, 4.5], num_cols=(1, 2, 3, 4, 5))

    _heading(doc, "3. เรขาคณิต มิติ และระดับน้ำ")
    dim_rows = [
        ("H1", "ความสูงรวมกำแพง", "ข้อมูลนำเข้า", H1),
        ("H2", "ความสูงผนังเหนือฐาน", "H1 − t1", H2),
        ("H5", "ระดับน้ำสูงจากใต้ฐาน", "ข้อมูลนำเข้า", H5),
        ("t1", "ความหนาฐาน", "ข้อมูลนำเข้า", t1),
        ("t2", "ความหนาผนังส่วนล่าง", "ข้อมูลนำเข้า", t2),
        ("t3", "ความหนาผนังส่วนบน", "ข้อมูลนำเข้า", t3),
        ("L1", "ความกว้างฐาน", "ข้อมูลนำเข้า", L1),
        ("L2", "ความยาวปลายเท้า", "ข้อมูลนำเข้า", L2),
        ("L3", "ความยาวส้นฐาน", "L1 − L2 − t2", L3),
    ]
    _table(doc, ["สัญลักษณ์", "ความหมาย", "ที่มา", "ค่า (m)"],
           [(s, m, o, f"{v:.2f}") for s, m, o, v in dim_rows],
           [2.2, 7.3, 4.3, 3.2], num_cols=(3,))
    _picture(doc, dims_png, 15, "รูปที่ 1  ภาพตัดกำแพงแสดงมิติ (หน่วย m)")

    _heading(doc, "4. แรงดันด้านข้างและเสถียรภาพ")
    _eq(doc, f"ΣH = {r['SH']:.2f} kg/m    ,    ΣMo = {r['Mo_lat']:.2f} kg·m/m")
    _eq(doc, f"การพลิกคว่ำ FS = {r['FS_ot']:.2f} (เกณฑ์ ≥ {p['fs_ot_min']})")
    _eq(doc, f"การเลื่อนไถล FS = {r['FS_sl']:.2f} (เกณฑ์ ≥ {p['fs_sl_min']})")
    _eq(doc, f"เสถียรภาพลาดดินเชิงลึก (Bishop's FS) = {r['slope_fs']:.2f} (เกณฑ์ ≥ {1.1 if use_seismic else 1.5})")
    _picture(doc, forces_png, 16, "รูปที่ 2  แผนภาพแรงดันดินแยกตามชั้นและแรง ΣV")
    _picture(doc, press_png, 13, "รูปที่ 3  แผนภาพแรงแบกทานใต้ฐาน / แรงกดเสาเข็ม")

    if use_piles and pile_results:
        _heading(doc, "4.1 การตรวจสอบกำลังรับน้ำหนักเสาเข็ม")
        pile_rows = [(f"ต้นที่ {item['pile_no']}", f"{item['x_pos']:.2f}", f"{item['load_kg']:.1f}", f"{pile_results['pile_cap_allow']:,.0f}") for item in pile_results["pile_loads"]]
        _table(doc, ["เสาเข็ม", "ตำแหน่ง X (m)", "แรงกดจริง (kg/ต้น)", "Allowable (kg/ต้น)"],
               pile_rows, [4, 4, 4.5, 4.5], num_cols=(1, 2, 3))

    _heading(doc, "5. รายการคำนวณออกแบบเหล็กเสริมและแรงเฉือน (วิธีกำลัง - SDM)")
    _eq(doc, "5.1 การออกแบบแผ่นผนัง (Stem Wall Flexure & Shear)")
    _eq(doc, f"• โมเมนต์ดัดประลัย: Mu = {rebar['Mu_stem']:.2f} t-m/m")
    _eq(doc, f"• ความลึกประสิทธิผล: d = t2 − cover − 1.0 = {t2*100:.0f} − {cover} − 1.0 = {rebar['d_stem']:.1f} cm")
    _eq(doc, f"• พื้นที่เหล็กเสริมดัด: As = [Mu × 10⁵] / [φ × fy × 0.9 × d] = {rebar['As_stem']:.2f} cm²/m  ⇒  (แนะนำ DB 16 @ 0.20 m)")
    _eq(doc, f"• ตรวจสอบแรงเฉือน: Vu = {rebar['Vu_stem']:.1f} kg/m ≤ φVc = {rebar['phi_Vc_stem']:.1f} kg/m  ⇒  [ผ่านเกณฑ์ ไม่ต้องใช้เหล็กปลอก]")

    _eq(doc, "5.2 การออกแบบส้นฐาน (Heel Slab Design)")
    _eq(doc, f"• โมเมนต์ดัดประลัย: Mu = {rebar['Mu_heel']:.2f} t-m/m")
    _eq(doc, f"• ความลึกประสิทธิผล: d = {rebar['d_heel']:.1f} cm")
    _eq(doc, f"• พื้นที่เหล็กเสริม: As = {rebar['As_heel']:.2f} cm²/m  ⇒  (แนะนำ DB 16 @ 0.20 m)")

    _eq(doc, "5.3 การออกแบบปลายเท้า (Toe Slab Design)")
    _eq(doc, f"• โมเมนต์ดัดประลัย: Mu = {rebar['Mu_toe']:.2f} t-m/m")
    _eq(doc, f"• ความลึกประสิทธิผล: d = {rebar['d_toe']:.1f} cm")
    _eq(doc, f"• พื้นที่เหล็กเสริม: As = {rebar['As_toe']:.2f} cm²/m  ⇒  (แนะนำ DB 12 @ 0.20 m)")

    _eq(doc, f"5.4 ระยะฝังตัวและทาบเหล็ก (Development Length): Ld = [0.006 × db × fy] / [√(f'c)] = {rebar['Ld']:.1f} cm")
    
    _picture(doc, rebar_png, 14, "รูปที่ 4  ภาพตัดแสดงตำแหน่งและการเสริมเหล็กหลัก")

    _heading(doc, "6. สรุปการถอดปริมาณวัสดุ (BOQ ต่อความยาว 1 เมตร)")
    boq_rows = [
        ("คอนกรีตฐานราก (Base Slab)", f"{boq['vol_base']:.2f}", "m³"),
        ("คอนกรีตแผ่นผนัง (Stem)", f"{boq['vol_stem']:.2f}", "m³"),
        ("คอนกรีตรวมทั้งหมด", f"{boq['total_concrete']:.2f}", "m³"),
        ("เหล็กเสริมรวม (Rebar)", f"{boq['total_rebar_kg']:.1f}", "kg"),
        ("งานขุดดิน (Earthwork Excavation)", f"{boq['excavation_vol']:.2f}", "m³"),
    ]
    if use_piles:
        boq_rows.append(("เสาเข็มรองรับฐานราก", f"{pile_results['num_piles']}", "ต้น"))
    boq_rows.append(("งบประมาณประเมินเบื้องต้น", f"{boq['est_cost']:,.0f}", "บาท"))
    _table(doc, ["รายการวัสดุ / งานก่อสร้าง", "ปริมาณ", "หน่วย"], boq_rows, [8, 4, 4], num_cols=(1,))

    OKC, NGC = "C8E6C9", "FFCDD2"
    def status(ok): return ("ผ่าน", OKC) if ok else ("ไม่ผ่าน", NGC)

    _heading(doc, "7. สรุปผลการตรวจสอบ")
    summary_rows = [
        ("การพลิกคว่ำ (FS)", f"{r['FS_ot']:.2f}", f"≥ {p['fs_ot_min']:.1f}", status(checks["ot"])),
        ("การเลื่อนไถล (FS)", f"{r['FS_sl']:.2f}", f"≥ {p['fs_sl_min']:.1f}", status(checks["sl"])),
        ("เสถียรภาพลาดดินเชิงลึก (Bishop's FS)", f"{r['slope_fs']:.2f}", f"≥ {1.1 if use_seismic else 1.5}", status(checks["slope"])),
    ]
    if use_piles:
        summary_rows.append(("กำลังเสาเข็มสูงสุด", f"{pile_results['max_pile_load']:.0f}", f"≤ {pile_results['pile_cap_allow']:,.0f} kg", status(checks["pile"])))
    else:
        summary_rows.append(("Eccentricity |e| (m)", f"{abs(r['e']):.2f}", f"≤ {L1/6:.2f}", status(checks["e"])))
        summary_rows.append(("แรงแบกทานสูงสุด (kg/m²)", f"{r['q_max']:.1f}", f"≤ {p['q_allow']:.0f}", status(checks["q"])))
    
    summary_rows.append(("แรงเฉือนโคนผนัง", f"Vu {rebar['Vu_stem']:.0f}", f"≤ {rebar['phi_Vc_stem']:.0f} kg", status(rebar['shear_ok_stem'])))

    _table(doc, ["รายการ", "ค่าที่ได้", "เกณฑ์", "ผล"], summary_rows, [6, 3.5, 3.5, 4], num_cols=(1, 2))

    _para(doc, "", space_after=14)
    sig = doc.add_table(rows=1, cols=2)
    for i, who in enumerate(("ผู้ออกแบบ", "ผู้ตรวจสอบ")):
        c = sig.rows[0].cells[i]
        c.text = ""
        pp = c.paragraphs[0]
        pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _fmt(pp.add_run("\n\n.............................................\n"
                        f"({(designer if i == 0 else checker) or '..........................'})\n{who}"), 15)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
