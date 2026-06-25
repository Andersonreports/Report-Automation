
import os, io, re, base64, sys
from datetime import datetime


def _resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

from reportlab.pdfgen          import canvas
from reportlab.lib.colors      import Color, black, white, HexColor
from reportlab.lib.utils       import ImageReader
from reportlab.lib.styles      import ParagraphStyle
from reportlab.lib.enums       import TA_JUSTIFY, TA_LEFT
from reportlab.platypus        import Paragraph, Table, TableStyle
from reportlab.pdfbase         import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

import tera_assets

BLUE     = Color(0.122, 0.286, 0.49)
BLUE_HEX = "#1F497D"
MED_BLUE = Color(0.310, 0.506, 0.741)
FIELD    = HexColor('#F1F1F7')
GRAY_SIG = Color(0.2, 0.2, 0.2)
BLACK    = black
WHITE    = white

_FONT_DIR = _resource_path("fonts")

def _reg(name, filename):
    path = os.path.join(_FONT_DIR, filename)
    if os.path.exists(path):
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            return True
        except Exception:
            pass
    return False

_reg("GillSansMT-Bold", "GILB____.TTF")
_reg("SegoeUI-Bold",    "SEGOEUIB.TTF")
_reg("SegoeUI",         "SEGOEUI.TTF")
_reg("DengXian",        "DengXian.ttf")
_reg("DengXian-Bold",   "DengXian_Bold.ttf")
_reg("Arial-Bold",      "Arial-BoldMT.ttf")
_reg("Arial",           "ArialMT.ttf")
_reg("Calibri",         "CALIBRI.TTF")
_reg("Calibri-Bold",    "CALIBRIB.TTF")
_reg("SymbolMT",        "SymbolMT.ttf")

def _font_ok(name):
    try:
        pdfmetrics.getFont(name)
        return True
    except Exception:
        return False

if _font_ok("Calibri") and _font_ok("Calibri-Bold"):
    registerFontFamily("Calibri",
        normal="Calibri", bold="Calibri-Bold",
        italic="Calibri", boldItalic="Calibri-Bold")

if _font_ok("SegoeUI") and _font_ok("SegoeUI-Bold"):
    registerFontFamily("SegoeUI",
        normal="SegoeUI", bold="SegoeUI-Bold",
        italic="SegoeUI", boldItalic="SegoeUI-Bold")

if _font_ok("DengXian") and _font_ok("DengXian-Bold"):
    registerFontFamily("DengXian",
        normal="DengXian", bold="DengXian-Bold",
        italic="DengXian", boldItalic="DengXian-Bold")

F_TITLE  = "GillSansMT-Bold" if _font_ok("GillSansMT-Bold") else "Helvetica-Bold"
F_HDG    = "GillSansMT-Bold" if _font_ok("GillSansMT-Bold") else "Helvetica-Bold"
F_LBL    = "SegoeUI-Bold"    if _font_ok("SegoeUI-Bold")    else "Helvetica-Bold"

F_BODY   = "DengXian"        if _font_ok("DengXian")        else "Helvetica"
F_BBOLD  = "DengXian-Bold"   if _font_ok("DengXian-Bold")   else "Helvetica-Bold"

F_SIG    = "SegoeUI"         if _font_ok("SegoeUI")         else "Helvetica"
F_SIGB   = "SegoeUI-Bold"    if _font_ok("SegoeUI-Bold")    else "Helvetica-Bold"

F_BULLET = "DengXian"        if _font_ok("DengXian")        else ("Calibri" if _font_ok("Calibri") else "Helvetica")

print(f"[tera_template] Fonts: TITLE={F_TITLE}  LBL={F_LBL}  BODY={F_BODY}  BULLET={F_BULLET}")

W, H = 612.0, 792.0

HDR_X, HDR_Y, HDR_W, HDR_H = 72.0, H - 72.0, 468.0, 72.0
FTR_X, FTR_Y, FTR_W, FTR_H = 72.75, 8.0,      481.9, 34.0

DOSE_FOOTER_RESERVE = 120.0

TBL_X          = 45.84
TBL_TOP_RL     = H - 143.78
TBL_COL_WIDTHS = [111.26, 7.08, 200.61, 91.22, 9.01, 114.10]
TBL_W          = sum(TBL_COL_WIDTHS)
TBL_PAD_TOP    = 9

DIV_X0, DIV_X1 = 72.75, 554.65

RESULT_CFG = {
    "receptive": {
        "chart_x": 411.85, "chart_y": H - 506.95, "chart_w": 141,    "chart_h": 130.5,
        "box_x": 72, "box_y": H - 507.65, "box_w": 264.75, "box_h": 111.1,
        "status_x": 79.2,  "status_max_w": 257.55,
        "hdg_recom_y":   H - 553.3,
        "recom_line_y":  H - 562.5,
        "has_biopsy2":   False,
        "blast_x": 171.7, "blast_y": H - 613.0,
        "cleave_x":170.4, "cleave_y": H - 670.6,
        "reco_suffix": "post first progesterone intake",
        "recom_max_w": 280,
        "icon_y": H - 694.5,
        "bold_phrase": "receptive endometrium",
        "displaced":   False,
        "asset": "RECEPTIVE",
    },
    "pre": {
        "chart_x": 334.70, "chart_y": H - 493.80, "chart_w": 218,    "chart_h": 127.3,
        "box_x": 72, "box_y": H - 510.90, "box_w": 250.25, "box_h": 125.6,
        "status_x": 79.2,  "status_max_w": 243.05,
        "hdg_recom_y":   H - 550.1,
        "recom_line_y":  H - 559.3,
        "has_biopsy2":   False,
        "blast_x": 171.7, "blast_y": H - 609.7,
        "cleave_x":170.4, "cleave_y": H - 667.3,
        "reco_suffix": "post first progesterone intake",
        "recom_max_w": 280,
        "icon_y": H - 691.3,
        "bold_phrase": "pre-receptive endometrium",
        "displaced":   True,
        "asset": "PRE_RECEPTIVE",
    },
    "post": {
        "chart_x": 336.00, "chart_y": H - 494.05, "chart_w": 216.85, "chart_h": 127.55,
        "box_x": 72, "box_y": H - 503.90, "box_w": 257.25, "box_h": 123.85,
        "status_x": 79.2,  "status_max_w": 250.05,
        "hdg_recom_y":   H - 520.0,
        "recom_line_y":  H - 530.0,
        "has_biopsy2":   True,
        "blast_x": 171.7, "blast_y": H - 642.0,
        "cleave_x":170.4, "cleave_y": H - 702.0,
        "reco_suffix": "post first progesterone intake",
        "recom_max_w": 380,
        "icon_y": H - 725.0,
        "bold_phrase": "post-receptive endometrium",
        "displaced":   True,
        "asset": "POST_RECPTIVE",
    },
}

_IMG_CACHE: dict = {}

def _img(b64: str) -> ImageReader:
    if b64 not in _IMG_CACHE:
        _IMG_CACHE[b64] = base64.b64decode(b64)
    return ImageReader(io.BytesIO(_IMG_CACHE[b64]))

def _divider(c, y):
    c.setStrokeColor(Color(0.6, 0.6, 0.6))
    c.setLineWidth(0.48)
    c.line(DIV_X0, y, DIV_X1, y)

def _wrap(c, text, x, y, max_w, font, size, leading):
    words = text.split()
    line  = ""
    for w in words:
        trial = line + w + " "
        if c.stringWidth(trial, font, size) <= max_w:
            line = trial
        else:
            if line:
                c.drawString(x, y, line.rstrip())
                y -= leading
            line = w + " "
    if line.strip():
        c.drawString(x, y, line.rstrip())
        y -= leading
    return y


def _wrap_justify(c, text, x, y, max_w, font, size, leading, first_line_indent=0):
    words = text.split()
    lines = []
    line = []
    for w in words:
        trial = " ".join(line + [w])
        indent = first_line_indent if not lines else 0
        if c.stringWidth(trial, font, size) <= (max_w - indent):
            line.append(w)
        else:
            if line:
                lines.append(line)
            line = [w]
    if line:
        lines.append(line)

    for idx, l in enumerate(lines):
        line_str = " ".join(l)
        indent = first_line_indent if idx == 0 else 0
        if idx == len(lines) - 1:
            c.drawString(x + indent, y, line_str)
        else:
            if len(l) > 1:
                total_w = c.stringWidth(line_str, font, size)
                space_to_add = (max_w - indent) - total_w
                extra_space = space_to_add / (len(l) - 1)
                
                curr_x = x + indent
                for w_idx, w in enumerate(l):
                    c.drawString(curr_x, y, w)
                    curr_x += c.stringWidth(w, font, size) + c.stringWidth(" ", font, size) + extra_space
            else:
                c.drawString(x + indent, y, line_str)
        y -= leading
    return y


def _wrap_pm(c, text, x, y, max_w, font, size, leading):
    PM = '\u00b1'
    PM_FONT = 'Helvetica-Bold'
    space_w = c.stringWidth(' ', font, size)

    def word_w(w):
        return c.stringWidth(PM, PM_FONT, size) if w == PM else c.stringWidth(w, font, size)

    def draw_line(words_list, lx, ly):
        cx = lx
        for i, w in enumerate(words_list):
            if i > 0:
                c.setFont(font, size)
                c.drawString(cx, ly, ' ')
                cx += space_w
            if w == PM:
                c.setFont(PM_FONT, size)
            else:
                c.setFont(font, size)
            c.drawString(cx, ly, w)
            cx += word_w(w)

    words = text.split()
    line_words, line_w = [], 0.0
    for w in words:
        ww = word_w(w)
        gap = space_w if line_words else 0.0
        if line_w + gap + ww <= max_w:
            line_words.append(w)
            line_w += gap + ww
        else:
            if line_words:
                draw_line(line_words, x, y)
                y -= leading
            line_words, line_w = [w], ww
    if line_words:
        draw_line(line_words, x, y)
        y -= leading
    return y


def _justified_block(c, text, x, y, max_w, font, size, leading):
    style = ParagraphStyle(
        "JBlock",
        fontName=font, fontSize=size, leading=leading,
        alignment=TA_JUSTIFY,
        spaceAfter=0, spaceBefore=0,
    )
    para = Paragraph(text, style)
    _, h = para.wrap(max_w, 2000)
    offset = leading - size
    para.drawOn(c, x, y - h + offset)
    return y - h + offset


class TERAReportGenerator:

    def __init__(self, data_row: dict, output_dir: str, with_logo: bool = False):
        self.d         = data_row
        self.out       = output_dir
        self.with_logo = with_logo

        raw = str(self.d.get("TERA result",
              self.d.get("TERA result ",
              self.d.get("TERA Result", "")))).strip().lower()
        self.result_type = (
            "pre"  if "pre"  in raw else
            "post" if "post" in raw else
            "receptive"
        )
        self.cfg = RESULT_CFG[self.result_type]

        name = self._s(self.d.get("Patient Name", "Unknown"))
        name = re.sub(r'^(Mrs?\.|MRS?\.|Miss\.?|Ms\.?|Dr\.|DR\.)\s*', '', name).strip()
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        bno_raw = self._s(self.d.get("Biopsy No.", self.d.get("Biopsy", "1")))
        bno = self._biopsy_ordinal(bno_raw)
        logo_tag = "with logo" if self.with_logo else "without logo"
        self.filename = f"{name}_{bno}_TERA_report_{logo_tag}.pdf"
        self.filepath = os.path.join(self.out, self.filename)

    def generate(self, pages: int = 3) -> str:
        c = canvas.Canvas(self.filepath, pagesize=(W, H))
        c.setTitle(self.filename)
        self._page1(c)
        if pages >= 2:
            c.showPage()
            self._page2(c)
        if pages >= 3:
            c.showPage()
            self._page3(c)
        c.save()
        return self.filepath

    def _header(self, c):
        if not self.with_logo:
            return
        c.saveState()
        try:
            c.drawImage(_img(tera_assets.HEADER_LOGO),
                        HDR_X, HDR_Y, width=HDR_W, height=HDR_H,
                        mask="auto", preserveAspectRatio=False)
        except Exception as e:
            print(f"[TERA] Header err: {e}")
        c.restoreState()

    def _footer(self, c):
        if not self.with_logo:
            return
        c.saveState()
        try:
            c.drawImage(_img(tera_assets.FOOTER),
                        FTR_X, FTR_Y, width=FTR_W, height=FTR_H,
                        mask="auto", preserveAspectRatio=False)
        except Exception:
            pass
        c.restoreState()

    def _page_number(self, c, n: int, total: int = 3):
        text = f"Page {n} of {total}"
        y = (FTR_Y + FTR_H + 28) if self.with_logo else (DOSE_FOOTER_RESERVE + 8)
        c.saveState()
        c.setFont(F_SIG, 9)
        c.setFillColor(GRAY_SIG)
        c.drawCentredString(W / 2, y, text)
        c.restoreState()

    def _page1(self, c):
        self._header(c)
        self._footer(c)
        self._title_block(c)
        self._field_table(c)
        self._status_section(c)
        self._recom_section(c)
        self._page_number(c, 1)

    def _title_block(self, c):
        c.setFont(F_TITLE, 18)
        c.setFillColor(BLUE)
        c.drawCentredString(W / 2, H - 104.8,
                            "Transcriptome based Endometrial Receptivity Assessment")
        c.drawCentredString(W / 2, H - 136.1, "(TERA)")

    def _field_table(self, c):
        rows = self._patient_rows()

        cell_style = ParagraphStyle(
            "TeraCell",
            fontName=F_LBL, fontSize=10, leading=12,
            textColor=BLACK, spaceAfter=0, spaceBefore=0,
        )

        def P(text):
            return Paragraph(str(text) if text else "", cell_style)

        data = [[P(l1), P(":"), P(v1), P(l2), P(":"), P(v2)]
                for l1, v1, l2, v2 in rows]

        tbl = Table(data, colWidths=TBL_COL_WIDTHS, rowHeights=None, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), F_LBL),
            ("FONTSIZE",      (0, 0), (-1, -1), 10),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 2),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
            ("RIGHTPADDING",  (3, 0), (3, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), TBL_PAD_TOP),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        tbl_w, tbl_h = tbl.wrap(TBL_W, 600)
        tbl_bot = TBL_TOP_RL - tbl_h

        c.setFillColor(FIELD)
        c.rect(TBL_X, tbl_bot, tbl_w, tbl_h, fill=True, stroke=False)

        c.saveState()
        c.setStrokeColor(FIELD)
        tbl.drawOn(c, TBL_X, tbl_bot)
        c.restoreState()

    def _status_section(self, c):
        cfg = self.cfg

        try:
            asset = getattr(tera_assets, cfg["asset"])
            c.saveState()
            c.setStrokeColor(WHITE)
            c.setLineWidth(0)
            c.drawImage(_img(asset),
                        cfg["chart_x"], cfg["chart_y"],
                        width=cfg["chart_w"], height=cfg["chart_h"],
                        preserveAspectRatio=False)
            c.restoreState()
        except Exception:
            pass

        c.setFont(F_HDG, 14)
        c.setFillColor(BLUE)
        c.drawString(72, H - 361.6, "Endometrial receptivity status")
        _divider(c, H - 366.65)

        c.setFillColor(WHITE)
        c.rect(cfg["box_x"], cfg["box_y"],
               cfg["box_w"], cfg["box_h"],
               fill=True, stroke=False)

        bh_int = self._int(self.d.get("Biopsy time in hrs.1", ""))
        bh_lbl = f"P+{bh_int} hrs" if bh_int is not None else "the biopsy time"

        suffix = (" and therefore represents a displaced window of implantation."
                  if cfg["displaced"] else
                  " and therefore represents a window of implantation.")
        html = (f"The gene expression profile of the endometrial biopsy sample "
                f"performed on {bh_lbl} is indicative of a "
                f"<b>{cfg['bold_phrase']}</b>{suffix}")

        para_style = ParagraphStyle(
            "TeraStatus",
            fontName=F_BODY, fontSize=12, leading=24,
            alignment=TA_JUSTIFY,
            textColor=BLACK, spaceAfter=0, spaceBefore=0,
        )
        para = Paragraph(html, para_style)
        para_w, para_h = para.wrap(cfg["status_max_w"], 300)

        box_top_rl = cfg["box_y"] + cfg["box_h"]
        para.drawOn(c, cfg["status_x"], box_top_rl - 6.5 - para_h)

    def _recom_section(self, c):
        cfg = self.cfg

        try:
            c.saveState()
            c.setStrokeColor(WHITE)
            c.setLineWidth(0)
            c.drawImage(_img(tera_assets.RECOMENDATION),
                        72, cfg["icon_y"], width=70, height=124,
                        preserveAspectRatio=False)
            c.restoreState()
        except Exception:
            pass

        c.setFont(F_HDG, 14)
        c.setFillColor(BLUE)
        c.drawString(72, cfg["hdg_recom_y"],
                     "Recommendations for personalized Embryo Transfer (pET)")
        _divider(c, cfg["recom_line_y"])

        tr_raw = str(self.d.get("Time for report",
                     self.d.get("Time for report ",
                     self.d.get("Corrected time for report ",
                     self.d.get("embryo transfer time in hrs", ""))))).strip()
        blast_lbl, cleave_lbl = self._parse_tr(tr_raw)

        _bm = re.match(r'(\d+)', blast_lbl)
        biopsy2_hrs = int(_bm.group(1)) if _bm else 98

        suffix = cfg["reco_suffix"]

        c.setFont(F_BBOLD, 11)
        c.setFillColor(BLACK)

        if cfg["has_biopsy2"]:
            c.setFont(F_LBL, 11)
            draw_x = 72.0
            wrap_total_w = DIV_X1 - draw_x - 5

            n1 = f"A Second biopsy at P+{biopsy2_hrs} hrs and P+120 hrs is strongly recommended to confirm the Window of implantation."
            curr_y = cfg["recom_line_y"] - 14
            curr_y = _wrap_justify(c, n1, draw_x, curr_y, wrap_total_w, F_LBL, 11, 14)
            
            curr_y -= 8
            prefix = "Note: "
            rem = "Patients with post-receptive endometria are prone to cycle-to-cycle variation. Hence repeat biopsy is suggested."
            
            c.setFillColor(BLUE)
            c.drawString(draw_x, curr_y, prefix)
            pw = c.stringWidth(prefix, F_LBL, 11)
            c.setFillColor(BLACK)
            
            curr_y = _wrap_justify(c, rem, draw_x, curr_y, wrap_total_w, F_LBL, 11, 14, first_line_indent=pw)

        reco_w = cfg.get("recom_max_w", 380.0)
        reco_font = "Calibri-Bold" if _font_ok("Calibri-Bold") else F_BBOLD

        _wrap_pm(c,
                 f"Blastocyst transfer (Day 5/6 embryo): {blast_lbl} {suffix}",
                 cfg["blast_x"], cfg["blast_y"], reco_w, reco_font, 11, 17)

        _wrap_pm(c,
                 f"Cleavage stage transfer (Day 3 embryo): {cleave_lbl} {suffix}",
                 cfg["cleave_x"], cfg["cleave_y"], reco_w, reco_font, 11, 17)

    ABOUT_PARAS = [
        ("Embryo implantation is a highly organized process during which the embryo attaches "
         "to the surface of the endometrium. Synchronous structural and functional remodelling "
         "of the uterine endometrium and the blastocyst is essential for successful implantation. "
         "The window of implantation (WOI) is a limited time span during which crosstalk between "
         "a receptive uterine endometrium and a competent blastocyst occurs effectively."),
        ("A displacement in the window of implantation is among the leading causes of recurrent "
         "implantation failure and is observed in 30% of women undergoing ART conception. It is "
         "frequently observed that an endometrium that appears morphologically ready for "
         "implantation may not express appropriate transcriptomic response characteristic of WOI. "
         "Therefore, an accurate molecular description of the endometrial transcriptomic signature "
         "is essential in ensuring implantation of embryos with good development potentials."),
        ("TERA is designed to provide personalized embryo implantation time on the basis cutting-edge "
         "technical expertise based on Next generation Sequencing (NGS) that allows us to study "
         "unique endometrial signature representation of WOI. Highest reproducibility in TERA "
         "results is observed in HRT cycles."),
    ]
    METHOD_BULLETS = [
        ("TERA detects mRNA expression in endometrial tissues using NGS based RNA-seq method "
         "combined with Artificial Intelligence (AI) empowered data analysis platform to discern "
         "endometrial status. The results are used as references for embryo transfer to improve "
         "chances of successful implantation."),
        ("The duration of WOI may vary from patient to patient. The results of this test suggest "
         "the optimal time to transfer embryos and enable accurate clinical recommendations for "
         "embryo transfer."),
    ]

    def _page2(self, c):
        self._header(c)
        self._footer(c)

        CONTENT_W = DIV_X1 - 72

        c.setFont(F_HDG, 14)
        c.setFillColor(BLUE)
        c.drawString(72, H - 109.2, "About TERA")
        _divider(c, H - 118.85)

        y = H - 145.4
        c.setFillColor(BLACK)
        for para in self.ABOUT_PARAS:
            y = _justified_block(c, para, 72, y, CONTENT_W, F_BODY, 11, 22)
            y -= 23

        meth_y = y - 8
        c.setFont(F_HDG, 14)
        c.setFillColor(BLUE)
        c.drawString(78.9, meth_y, "Methodology")
        _divider(c, meth_y - 9)

        y = meth_y - 37
        for bullet in self.METHOD_BULLETS:
            c.setFillColor(BLACK)
            c.circle(92.5, y + 4, 2.5, fill=1, stroke=0)
            y = _justified_block(c, bullet, 108, y, CONTENT_W - 36, F_BODY, 11, 22)
            y -= 10
        self._page_number(c, 2)

    REFS = [
        "Achache H, Revel A. Hum Reprod Update, 2006, 12(6):731-46.",
        "Teh W T, Mcbain J, Rogers P. Journal of Assisted Reproduction & Genetics, 2016, 33(11):1-12.",
        "Mahajan N. Journal of Human Reproductive Sciences, 2015, 8(3):121-129.",
        "Ruiz-Alonso M, Blesa D, DÃ­az-Gimeno, Patricia, et al. Fertility and Sterility, 2013, 100(3):818-824.",
    ]

    def _page3(self, c):
        self._header(c)
        self._footer(c)

        c.setFont(F_HDG, 14)
        c.setFillColor(BLUE)
        c.drawString(78.9, H - 109.2, "References")
        _divider(c, H - 118.1)

        REF_W = DIV_X1 - 93.9
        y = H - 132.15
        c.setFont(F_BODY, 11)
        c.setFillColor(BLACK)
        for i, ref in enumerate(self.REFS, 1):
            c.drawString(75.9, y, f"{i}.")
            _wrap(c, ref, 93.9, y, REF_W, F_BODY, 11, 14)
            y -= 27

        c.setFont(F_SIGB, 12)
        c.setFillColor(MED_BLUE)
        c.drawString(75.9, H - 251.9,
                     "This report has been reviewed and approved by:")

        sigs = [
            (80.75,  H - 310.95, 71.15,  33.1,  tera_assets.SIVASHANKAR_SIGN),
            (237.75, H - 310.95, 74.25,  33.05, tera_assets.FIONA_SIGN),
            (406.25, H - 317.75, 100.15, 42.3,  getattr(tera_assets, "SACHIN_SIGN", None)),
        ]
        for sx, sy, sw, sh, asset in sigs:
            if asset:
                try:
                    c.drawImage(_img(asset), sx, sy, width=sw, height=sh,
                                preserveAspectRatio=True, mask="auto")
                except Exception:
                    pass
            else:
                c.setStrokeColor(BLACK)
                c.setLineWidth(0.7)
                c.line(sx, sy + 10, sx + sw, sy + 10)

        c.setFont(F_SIG, 11)
        c.setFillColor(GRAY_SIG)
        name_y = H - 329.9
        c.drawString(72.0,  name_y, "S. Sivasankar, Ph. D")
        c.drawString(208.0, name_y, "Fiona D'Souza, Ph. D")
        c.drawString(395.0, name_y, "Sachin D Honguntikar, Ph. D")

        role_y = H - 348.0
        c.drawString(72.0,  role_y, "Molecular Biologist")
        c.drawString(208.0, role_y, "Head -Scientific Operations")
        c.drawString(395.0, role_y, "Head- Clinical Genetics")
        self._page_number(c, 3)

    def _patient_rows(self):
        d     = self.d
        name  = self._s(d.get("Patient Name", "")).title()
        pin   = self._s(d.get("Sample ID", "")) or "Not Provided"
        sid   = self._s(d.get("Lab No.", ""))
        age_r = self._s(d.get("Age", ""))
        age   = f"{age_r} Years" if age_r else "Not Provided"
        doc   = self._s(d.get("Doctor Name", "")) or "Not Provided"
        hosp  = self._s(d.get("Center name", d.get("Hospital", d.get("Hospital ", ""))))
        cyc_raw     = self._s(d.get("Cycle Type", d.get("Cycle type", "HRT")))
        biopsy_days = self._int(d.get("Biopsy", ""))
        cyc_upper   = cyc_raw.upper()
        if "HRT" in cyc_upper:
            cyc = (f"HRT; P+{biopsy_days}" if biopsy_days is not None else "HRT")
        elif cyc_raw:
            cyc = cyc_raw
        else:
            cyc = "Not Provided"
        bno   = self._s(d.get("Biopsy No.",  d.get("Biopsy", "")))
        p4d   = self._dt(d.get("P4 /hCG injection  date time", ""))
        biod  = self._dt(d.get("Biopsy time in hrs", ""))
        rcpt  = self._dt(d.get("Date of Received", ""), date_only=True)
        rep_date_raw = self._s(d.get("Report Date", ""))
        today = rep_date_raw if rep_date_raw else datetime.today().strftime("%d-%m-%Y")

        return [
            ("Patient Name",          name,  "PIN",                  pin),
            ("Date of Birth/ Age",    age,   "Sample Number",        sid),
            ("Referring Clinician",   doc,   "Cycle type",           cyc),
            ("Hospital/Clinic",       hosp,  "First progesterone intake date", p4d),
            ("Specimen",              bno,   "Biopsy date",          biod),
            ("Specimen receipt date", rcpt,  "Report date",          today),
        ]

    @staticmethod
    def _biopsy_ordinal(bno_raw: str) -> str:
        m = re.search(r'(\d+)', bno_raw)
        if m:
            n = int(m.group(1))
            if 11 <= (n % 100) <= 13:
                suffix = 'th'
            else:
                suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
            return f"{n}{suffix} biopsy"
        return bno_raw

    @staticmethod
    def _s(val) -> str:
        s = str(val).strip()
        return "" if s in ("nan", "NaT", "None", "NaN") else s

    @staticmethod
    def _int(val):
        if val is None:
            return None
        s = str(val).strip()
        if s in ("", "nan", "NaT", "None", "NaN"):
            return None
        try:
            import math
            f = float(s)
            return math.floor(f + 0.5)
        except Exception:
            return None

    @staticmethod
    def _dt(val, date_only=False) -> str:
        if val is None:
            return ""
        try:
            from pandas import Timestamp, NaT as PD_NAT
            if isinstance(val, Timestamp):
                if val is PD_NAT:
                    return ""
                if date_only or (val.hour == 0 and val.minute == 0):
                    return val.strftime("%d-%m-%Y")
                return val.strftime("%d-%m-%Y %H:%M Hrs")
        except Exception:
            pass
        s = str(val).strip()
        if s in ("", "nan", "NaT", "None", "NaN"):
            return ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                if date_only or (dt.hour == 0 and dt.minute == 0):
                    return dt.strftime("%d-%m-%Y")
                return dt.strftime("%d-%m-%Y %H:%M Hrs")
            except ValueError:
                continue
        return s

    @staticmethod
    def _parse_tr(raw: str):
        if not raw or raw in ("nan", "NaT", "None", ""):
            return "N/A", "N/A"
        m = re.match(r'^\s*(\d+(?:\.\d+)?)\s*[+Â±]\s*(\d+)', raw)
        if m:
            base   = round(float(m.group(1)))
            margin = m.group(2)
            return f"{base} \u00b1 {margin} hrs", f"{base - 48} \u00b1 {margin} hrs"
        try:
            base = round(float(raw))
            return f"{base} \u00b1 2 hrs", f"{base - 48} \u00b1 2 hrs"
        except Exception:
            return raw, "N/A"
