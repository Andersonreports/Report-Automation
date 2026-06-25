
import os, io, re, base64, sys, uuid
from datetime import datetime
from pathlib import Path


def _resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


from reportlab.pdfgen           import canvas
from reportlab.lib.colors       import Color, black, white, HexColor
from reportlab.lib.utils        import ImageReader
from reportlab.lib.styles       import ParagraphStyle
from reportlab.lib.enums        import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.platypus         import Paragraph
from reportlab.pdfbase          import pdfmetrics
from reportlab.pdfbase.ttfonts  import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

import karyotype_assets as _assets

DARK_BLUE  = HexColor('#1F3864')
RED        = Color(1, 0, 0)
GREEN      = HexColor('#00B050')
AMBER_BG   = HexColor('#F2F2F2')
AMBER_BRD  = HexColor('#D9D9D9')
GRAY_DIV   = Color(0.6, 0.6, 0.6)
FIELD_BG   = HexColor('#D9D9D9')
BLACK      = black
WHITE      = white

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

_reg("GillSansMT-Bold",       "GillSansMT-Bold.ttf")
_reg("GillSansMT",            "GillSansMT.ttf")
_reg("GillSansMT-BoldItalic", "GillSansMT-BoldItalic.ttf")
_reg("SegoeUI-Bold",          "SegoeUI-Bold.ttf")
_reg("SegoeUI",               "SegoeUI.ttf")
_reg("SegoeUI-Italic",        "SegoeUI-Italic.ttf")
_reg("Calibri",               "Calibri.ttf")
_reg("Calibri-Bold",          "Calibri-Bold.ttf")
_reg("Calibri-Italic",        "Calibri-Italic.ttf")
_reg("Calibri-BoldItalic",    "Calibri-BoldItalic.ttf")
_reg("Arial",                 "ArialMT.ttf")
_reg("Arial-Bold",            "Arial-BoldMT.ttf")

def _font_ok(n):
    try: pdfmetrics.getFont(n); return True
    except: return False

if _font_ok("Calibri") and _font_ok("Calibri-Bold"):
    registerFontFamily("Calibri", normal="Calibri", bold="Calibri-Bold",
                       italic="Calibri-Italic" if _font_ok("Calibri-Italic") else "Calibri",
                       boldItalic="Calibri-BoldItalic" if _font_ok("Calibri-BoldItalic") else "Calibri-Bold")
if _font_ok("Arial") and _font_ok("Arial-Bold"):
    registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                       italic="Arial", boldItalic="Arial-Bold")
if _font_ok("SegoeUI") and _font_ok("SegoeUI-Bold"):
    registerFontFamily("SegoeUI", normal="SegoeUI", bold="SegoeUI-Bold",
                       italic="SegoeUI-Italic" if _font_ok("SegoeUI-Italic") else "SegoeUI",
                       boldItalic="SegoeUI-Bold")
if _font_ok("GillSansMT") and _font_ok("GillSansMT-Bold"):
    registerFontFamily("GillSansMT", normal="GillSansMT", bold="GillSansMT-Bold",
                       italic="GillSansMT", boldItalic="GillSansMT-BoldItalic" if _font_ok("GillSansMT-BoldItalic") else "GillSansMT-Bold")

F_TITLE  = "GillSansMT-Bold" if _font_ok("GillSansMT-Bold") else "Helvetica-Bold"
F_HDG    = "GillSansMT-Bold" if _font_ok("GillSansMT-Bold") else "Helvetica-Bold"
F_TBL_LBL = "SegoeUI-Bold"  if _font_ok("SegoeUI-Bold")    else "Helvetica-Bold"
F_TBL_VAL = "SegoeUI"       if _font_ok("SegoeUI")         else "Helvetica"
F_LBL    = "Calibri-Bold"   if _font_ok("Calibri-Bold")    else "Helvetica-Bold"
F_BODY   = "Calibri"        if _font_ok("Calibri")         else "Helvetica"
F_ITALIC = "Calibri-Italic" if _font_ok("Calibri-Italic")  else "Helvetica"
F_BBOLD  = "Calibri-Bold"   if _font_ok("Calibri-Bold")    else "Helvetica-Bold"
F_SIG    = "Calibri"        if _font_ok("Calibri")         else "Helvetica"

W, H = 612.0, 792.0

def _rl(pdfplumber_top):
    return H - pdfplumber_top

HDR_X, HDR_Y, HDR_W, HDR_H   =  1.4,  _rl(67.8),   609.8, 67.8
FTR_X, FTR_Y, FTR_W, FTR_H   =  1.4,  0.2,         610.6, 48.0
STAMP_X, STAMP_Y, STAMP_W, STAMP_H = 276.4, _rl(216.0), 62.8, 78.8

LX = 39.6
RX = 575.0
CW = RX - LX

LEFT_VAL_X  = 136.8
RIGHT_LBL_X = 373.7
RIGHT_VAL_X = 487.3
COLON_X_L   = 130.2
COLON_X_R   = 481.8

TABLE_ROW_H = 29.2

DIV_X0, DIV_X1 = 72.0, 540.0

def _img(b64: str) -> ImageReader:
    return ImageReader(io.BytesIO(base64.b64decode(b64)))

def _img_white_to_alpha(b64: str, threshold: int = 235) -> ImageReader:
    from PIL import Image as PILImage
    img = PILImage.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
    pixels = img.getdata()
    new_pixels = [
        (r, g, b, 0) if r >= threshold and g >= threshold and b >= threshold else (r, g, b, a)
        for (r, g, b, a) in pixels
    ]
    img.putdata(new_pixels)
    return ImageReader(img)

def _divider(c, rl_y, lw=0.48):
    c.setStrokeColor(GRAY_DIV)
    c.setLineWidth(lw)
    c.line(DIV_X0, rl_y, DIV_X1, rl_y)

def _clean(v) -> str:
    s = str(v).strip()
    return "" if s in ("nan", "NaT", "None", "NaN", "") else s

def _fmt_date(v) -> str:
    if not v: return ""
    s = _clean(v)
    if not s: return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.split(" ")[0], fmt.split(" ")[0]).strftime("%d-%m-%Y")
        except Exception:
            pass
    return s

def _wrap_text(c, text, x, y, max_w, font, size, leading=None) -> float:
    if leading is None:
        leading = size * 1.45
    c.setFont(font, size)
    words = text.split()
    line  = ""
    for w in words:
        trial = (line + " " + w).strip()
        if c.stringWidth(trial, font, size) <= max_w:
            line = trial
        else:
            if line:
                c.drawString(x, y, line)
                y -= leading
            line = w
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y

def _paragraph_height(text, font, size, max_w, leading=None) -> float:
    if not text: return 0.0
    if leading is None:
        leading = size * 1.45
    try:
        from reportlab.pdfgen.canvas import Canvas as _C
        buf = io.BytesIO()
        dummy = _C(buf, pagesize=(W, H))
        words = text.split()
        line, lines = "", 0
        for w in words:
            trial = (line + " " + w).strip()
            if dummy.stringWidth(trial, font, size) <= max_w:
                line = trial
            else:
                lines += 1
                line = w
        if line: lines += 1
        return lines * leading
    except Exception:
        avg_char_w = size * 0.5
        chars_per_line = int(max_w / avg_char_w)
        n_lines = max(1, len(text) // chars_per_line + 1)
        return n_lines * (leading or size * 1.35)

def _draw_section_heading(c, text, rl_y, color=DARK_BLUE, size=16) -> float:
    cap_offset = size * 0.74
    c.setFont(F_HDG, size)
    c.setFillColor(color)
    c.drawString(DIV_X0, rl_y - cap_offset, text)
    div_y = rl_y - size - 3
    _divider(c, div_y)
    return div_y - 4

def _draw_bullet_list(c, items, x, y, max_w, font, size, leading=None) -> float:
    if leading is None:
        leading = size * 1.45
    bullet = "\u2022"
    indent = 18.0
    for item in items:
        c.setFont("Helvetica", size)
        c.setFillColor(BLACK)
        c.drawString(x, y, bullet)
        y = _wrap_text(c, item, x + indent, y, max_w - indent, font, size, leading)
    return y


def _draw_justified(c, text: str, x: float, y: float, max_w: float,
                    font: str, size: float, leading: float = None) -> float:
    if not text:
        return y
    if leading is None:
        leading = size * 1.41
    style = ParagraphStyle(
        'body_just',
        fontName=font,
        fontSize=size,
        leading=leading,
        alignment=TA_JUSTIFY,
        wordWrap='LTR',
    )
    para = Paragraph(text, style)
    w, h = para.wrap(max_w, 9999)
    para.drawOn(c, x, y - h)
    return y - h


class KaryotypeReportGenerator:

    def __init__(self, data_row: dict, image_paths: list, output_dir: str,
                 include_logo: bool = True):
        self.d      = {k.strip().upper(): _clean(v) for k, v in data_row.items()}
        self.out    = output_dir
        self.images = self._prepare_images(image_paths)
        self.include_logo = include_logo

        name   = " ".join((self._get("NAME") or "Unknown").split())
        sample = " ".join((self._get("SAMPLE NUMBER") or "NoSN").split())
        safe_name = re.sub(r'[^\w\s\-\(\)\.]', '', name).strip()
        logo_tag = "with logo" if include_logo else "without logo"
        self.filename = f"{safe_name} ({sample}) PBCKT {logo_tag}.pdf"
        self.filepath = os.path.join(output_dir, self.filename)

        has_comments = bool(self._get("COMMENTS"))
        self.three_page = has_comments

    def _prepare_images(self, image_paths: list) -> list:
        prepared = []
        os.makedirs(self.out, exist_ok=True)
        for p in image_paths or []:
            if not p or not os.path.isfile(p):
                continue
            try:
                from PIL import Image as PILImage, ImageOps
                with PILImage.open(p) as im:
                    im = ImageOps.exif_transpose(im)
                    if im.mode in ("RGBA", "LA"):
                        bg = PILImage.new("RGB", im.size, "white")
                        bg.paste(im, mask=im.getchannel("A"))
                        im = bg
                    else:
                        im = im.convert("RGB")
                    out_path = os.path.join(self.out, f"karyo_img_{uuid.uuid4().hex[:10]}.jpg")
                    im.save(out_path, "JPEG", quality=95)
                    prepared.append(out_path)
            except Exception:
                prepared.append(p)
        return prepared

    def _is_normal(self) -> bool:
        auto = self._get("AUTOSOME").lower()
        sex  = self._get("SEX CHROMOSOME", "SEX CHROMOSOME ").lower()
        return not ("abnormal" in auto or "abnormal" in sex or
                    "variant" in auto or "variant" in sex)

    def _iscn_color(self):
        auto = self._get("AUTOSOME").lower()
        sex  = self._get("SEX CHROMOSOME", "SEX CHROMOSOME ").lower()
        if "abnormal" in auto or "abnormal" in sex:
            return RED
        if "variant" in auto or "variant" in sex:
            return BLACK
        return GREEN

    def _get(self, *keys) -> str:
        for k in keys:
            v = self.d.get(k.upper().strip(), "")
            if v: return v
        return ""

    def generate(self) -> str:
        os.makedirs(self.out, exist_ok=True)
        c = canvas.Canvas(self.filepath, pagesize=(W, H))
        c.setTitle(f"Karyotype Report - {self._get('NAME')}")

        if self.three_page:
            self._page1(c)
            c.showPage()
            self._page2_abnormal(c)
            c.showPage()
            self._page3_signatures(c)
        else:
            self._page1_with_metaphase(c)
            c.showPage()
            self._page2_normal(c)

        c.save()
        return self.filepath

    def _page1_common(self, c, page_num=1, total_pages=None) -> float:
        if total_pages is None:
            total_pages = 3 if self.three_page else 2

        self._draw_chrome(c, page_num, total_pages)

        title_y = _rl(86.1) - int(18 * 0.74)
        c.setFont(F_TITLE, 18)
        c.setFillColor(DARK_BLUE)
        c.drawCentredString(W / 2, title_y, "Peripheral Blood Karyotyping")

        c.setFillColor(FIELD_BG)
        c.rect(LX, _rl(120.0) - 5 * 29.5, RX - LX, 5 * 29.5, fill=1, stroke=0)

        c.drawImage(_img_white_to_alpha(_assets.STAMP),
                    STAMP_X, STAMP_Y, STAMP_W, STAMP_H, mask="auto")

        self._draw_patient_table(c)

        ti_y = _rl(282.0)
        section_y = _draw_section_heading(c, "Test Indication", ti_y)
        c.setFont(F_BODY, 11)
        c.setFillColor(BLACK)
        indication = self._get("TEST INDICATION") or "To rule out gross chromosomal abnormality"
        section_y = _draw_justified(c, indication, DIV_X0, section_y - 10, DIV_X1 - DIV_X0,
                                    F_BODY, 11)

        res_y = section_y - 10
        _divider(c, section_y - 4, lw=0.5)
        res_y = _draw_section_heading(c, "Result", res_y)

        iscn = self._get("RESULT")
        prefix = "International System for Human Cytogenomic Nomenclature (ISCN 2024):"
        full_text = prefix + "  " + iscn
        box_x0, box_x1 = DIV_X0, DIV_X1 + 7
        pad   = 8
        pad_v = 7
        avail_w = box_x1 - box_x0 - pad * 2

        font_sz = 12
        for try_sz in [12, 11, 10, 9, 8]:
            c.setFont(F_LBL, try_sz)
            if c.stringWidth(full_text, F_LBL, try_sz) <= avail_w:
                font_sz = try_sz
                lines   = [full_text]
                break
        else:
            font_sz = 10
            c.setFont(F_LBL, font_sz)
            words = full_text.split()
            lines, cur = [], ""
            for w in words:
                trial = (cur + " " + w).strip()
                if c.stringWidth(trial, F_LBL, font_sz) <= avail_w:
                    cur = trial
                else:
                    if cur: lines.append(cur)
                    cur = w
            if cur: lines.append(cur)

        line_h  = font_sz * 1.3
        n_lines = len(lines)
        box_h   = n_lines * line_h + pad_v * 2
        box_y   = res_y - 5
        box_bot = box_y - box_h

        c.setFillColor(AMBER_BG)
        c.setStrokeColor(AMBER_BRD)
        c.setLineWidth(0.6)
        c.rect(box_x0, box_bot, box_x1 - box_x0, box_h, fill=1, stroke=1)

        iscn_color = self._iscn_color()
        c.setFont(F_LBL, font_sz)
        c.setFillColor(iscn_color)
        box_cx = (box_x0 + box_x1) / 2
        text_block_h = n_lines * line_h
        first_y = box_bot + (box_h + text_block_h) / 2 - line_h + (line_h - font_sz * 0.74) / 2
        for idx, line in enumerate(lines):
            c.drawCentredString(box_cx, first_y - idx * line_h, line)

        karyogram_top_y = box_bot - 6
        return karyogram_top_y

    def _page1_with_metaphase(self, c):
        top_y  = self._page1_common(c, page_num=1, total_pages=2)
        meta_h = 19.5 * 2

        meta_bot  = FTR_Y + FTR_H + 22
        kgram_bot = meta_bot + meta_h + 8

        self._draw_karyograms(c, top_y, kgram_bot)
        self._draw_metaphase_table(c, meta_bot)

    def _page1(self, c):
        top_y  = self._page1_common(c, page_num=1, total_pages=3)
        meta_h = 19.5 * 2
        meta_bot  = FTR_Y + FTR_H + 22
        kgram_bot = meta_bot + meta_h + 8
        self._draw_karyograms(c, top_y, kgram_bot)
        self._draw_metaphase_table(c, meta_bot)

    def _page2_normal(self, c):
        self._draw_chrome(c, 2, 2)
        y = _rl(67.8) - 52

        y = _draw_section_heading(c, "Interpretation", y)
        c.setFillColor(BLACK)
        y = _draw_justified(c, self._get("INTERPRETATION"), DIV_X0, y - 10,
                            DIV_X1 - DIV_X0, F_BODY, 11)

        y = self._draw_recommendations_block(c, y - 12)
        y = self._draw_methodology_block(c, y - 12)
        y = self._draw_limitations_block(c, y - 12)
        y = self._draw_references_block(c, y - 8)
        self._draw_signatures(c, y - 11)

    def _page2_abnormal(self, c):
        self._draw_chrome(c, 2, 3)
        y = _rl(67.8) - 52

        y = _draw_section_heading(c, "Interpretation", y)
        c.setFillColor(BLACK)
        y = _draw_justified(c, self._get("INTERPRETATION"), DIV_X0, y - 10,
                            DIV_X1 - DIV_X0, F_BODY, 11)

        comments = self._get("COMMENTS")
        if comments:
            y = y - 12
            y = _draw_section_heading(c, "Comments", y)
            c.setFillColor(BLACK)
            y = _draw_justified(c, comments, DIV_X0, y - 10,
                                DIV_X1 - DIV_X0, F_BODY, 11)

        y = self._draw_recommendations_block(c, y - 12)
        y = self._draw_methodology_block(c, y - 12)
        self._draw_limitations_block(c, y - 12)

    def _page3_signatures(self, c):
        self._draw_chrome(c, 3, 3)
        y = _rl(67.8) - 52
        y = self._draw_references_block(c, y)
        self._draw_signatures(c, y - 20)

    def _draw_chrome(self, c, page_num: int, total_pages: int):
        if self.include_logo:
            c.drawImage(_img(_assets.HEADER), HDR_X, HDR_Y, HDR_W, HDR_H, mask="auto")
            c.drawImage(_img(_assets.FOOTER), FTR_X, FTR_Y, FTR_W, FTR_H, mask="auto")

        if self.include_logo:
            c.setFont(F_BODY, 8)
            c.setFillColor(BLACK)
            pg_str = f"{page_num}  |  P a g e"
            c.drawRightString(DIV_X1, FTR_Y + FTR_H + 4, pg_str)

    def _draw_patient_table(self, c):
        rows = [
            ("Patient name",      self._get("NAME"),
             "PIN",               self._get("PIN")),
            ("Gender/ Age",
             self._get("GENDER", "GENDER ") + " / " + self._get("AGE") + " Year" +
             ("s" if str(self._get("AGE")) != "1" else ""),
             "Sample Number",     self._get("SAMPLE NUMBER")),
            ("Specimen",          self._get("SPECIMEN"),
             "Sample collection date",
             _fmt_date(self._get("SAMPLE COLLECTION DATE", "SAMPLE COLLECTION DATE "))),
            ("Referring Clinician",
             self._get("REFERRING CLINICIAN"),
             "Sample receipt date",
             _fmt_date(self._get("SAMPLE RECEIPT DATE", "SAMPLE RECEIPT DATE "))),
            ("Hospital/Clinic",   self._get("HOSPITAL/CLINIC"),
             "Report Date",
             datetime.today().strftime("%d-%m-%Y")),
        ]

        row_top = _rl(120.0)
        row_h   = 29.5
        label_size = 9
        value_size = 10

        for i, (ll, lv, rl, rv) in enumerate(rows):
            baseline = row_top - (i * row_h) - row_h * 0.55

            c.setFont(F_TBL_LBL, label_size)
            c.setFillColor(BLACK)
            c.drawString(LX, baseline, ll)
            c.drawString(COLON_X_L, baseline, ":")

            c.setFont(F_TBL_LBL, value_size)
            _wrap_text(c, lv.title(), LEFT_VAL_X, baseline,
                       RIGHT_LBL_X - LEFT_VAL_X - 8, F_TBL_LBL, value_size, leading=11)

            c.setFont(F_TBL_LBL, label_size)
            c.setFillColor(BLACK)
            c.drawString(RIGHT_LBL_X, baseline, rl)
            c.drawString(COLON_X_R - 2, baseline, ":")

            c.setFont(F_TBL_LBL, value_size)
            _wrap_text(c, rv, RIGHT_VAL_X, baseline,
                       RX - RIGHT_VAL_X, F_TBL_LBL, value_size, leading=11)

        pass

    def _draw_karyograms(self, c, top_y: float, bottom_y: float):
        if not self.images:
            avail_h = top_y - bottom_y
            avail_w = DIV_X1 - DIV_X0
            c.setStrokeColor(AMBER_BRD)
            c.setLineWidth(0.5)
            c.rect(DIV_X0, bottom_y, avail_w, avail_h, fill=0, stroke=1)
            c.setFont(F_ITALIC, 10)
            c.setFillColor(Color(0.45, 0.45, 0.45))
            c.drawCentredString(DIV_X0 + avail_w / 2, bottom_y + avail_h / 2,
                                "Karyogram image not uploaded")
            return

        avail_h = top_y - bottom_y
        avail_w = DIV_X1 - DIV_X0

        n = len(self.images)

        if n == 1:
            self._place_image(c, self.images[0],
                              DIV_X0, bottom_y, avail_w, avail_h)

        elif n == 2:
            gap   = 8
            img_w = (avail_w - gap) / 2

            def _get_dims(path):
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(path) as im:
                        return im.size
                except Exception:
                    return (img_w, avail_h)

            iw0, ih0 = _get_dims(self.images[0])
            iw1, ih1 = _get_dims(self.images[1])
            common_scale = min(img_w / iw0, avail_h / ih0,
                               img_w / iw1, avail_h / ih1)
            self._place_image(c, self.images[0],
                              DIV_X0, bottom_y, img_w, avail_h, fixed_scale=common_scale)
            self._place_image(c, self.images[1],
                              DIV_X0 + img_w + gap, bottom_y, img_w, avail_h, fixed_scale=common_scale)

        else:
            left_w  = avail_w * 0.37
            right_w = avail_w * 0.59
            gap     = avail_w - left_w - right_w

            scatter_h = avail_h * 0.54
            zoom_h    = avail_h * 0.44

            try:
                from PIL import Image as PILImage
                with PILImage.open(self.images[0]) as _im:
                    _s_iw, _s_ih = _im.size
                _scatter_scale = min(left_w / _s_iw, scatter_h / _s_ih)
                scatter_dh = _s_ih * _scatter_scale
            except Exception:
                scatter_dh = scatter_h

            scatter_slot_y = bottom_y + avail_h - scatter_h
            scatter_rendered_bottom = scatter_slot_y + scatter_h - scatter_dh
            IMG_GAP = 4
            zoom_slot_y = scatter_rendered_bottom - IMG_GAP - zoom_h

            self._place_image(c, self.images[0],
                              DIV_X0, scatter_slot_y, left_w, scatter_h,
                              valign='top')
            self._place_image(c, self.images[1],
                              DIV_X0, zoom_slot_y, left_w, zoom_h,
                              valign='top')

            self._place_image(c, self.images[2],
                              DIV_X0 + left_w + gap, bottom_y, right_w, avail_h,
                              valign='top')

    @staticmethod
    def _image_has_border(path: str) -> bool:
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as im:
                rgb = im.convert('RGB')
                w, h = rgb.size
            step_x = max(1, w // 20)
            step_y = max(1, h // 20)
            min_avg = 255.0
            for inset in range(16):
                i = inset
                samples = []
                for px in range(i, w - i, step_x):
                    samples.append(rgb.getpixel((px, i)))
                    samples.append(rgb.getpixel((px, h - 1 - i)))
                for py in range(i, h - i, step_y):
                    samples.append(rgb.getpixel((i, py)))
                    samples.append(rgb.getpixel((w - 1 - i, py)))
                avg = sum(sum(px) / 3 for px in samples) / len(samples)
                if avg < min_avg:
                    min_avg = avg
            return min_avg < 230
        except Exception:
            return False

    def _place_image(self, c, path: str, x: float, y: float, max_w: float, max_h: float,
                     fixed_scale: float = None, valign: str = 'center'):
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as im:
                iw, ih = im.size
        except Exception:
            iw, ih = max_w, max_h

        if fixed_scale is not None:
            scale = fixed_scale
        else:
            scale = min(max_w / iw, max_h / ih)

        dw, dh = iw * scale, ih * scale
        cx = x + (max_w - dw) / 2
        if valign == 'top':
            cy = y + max_h - dh
        elif valign == 'bottom':
            cy = y
        else:
            cy = y + (max_h - dh) / 2

        try:
            c.drawImage(path, cx, cy, dw, dh, mask="auto")
        except Exception:
            pass

        if not self._image_has_border(path):
            c.setStrokeColor(BLACK)
            c.setLineWidth(0.5)
            c.rect(cx, cy, dw, dh, fill=0, stroke=1)

    def _draw_metaphase_table(self, c, rl_y: float) -> float:
        met_val  = self._get("METAPHASE ANALYSED", "METAPHASE ANALYSED ")
        auto_val = self._get("AUTOSOME")
        band_val = self._get("ESTIMATED BAND RESOLUTION")
        sex_val  = self._get("SEX CHROMOSOME", "SEX CHROMOSOME ")

        row_h  = 19.5
        tbl_x0 = LX + 12
        tbl_x1 = RX - 12
        mid_x  = (tbl_x0 + tbl_x1) / 2
        col1_x = tbl_x0 + 8
        col2_x = col1_x + 175
        col3_x = mid_x + 18
        col4_x = col3_x + 175

        c.setFillColor(FIELD_BG)
        c.rect(tbl_x0, rl_y, tbl_x1 - tbl_x0, row_h * 2, fill=1, stroke=0)


        cap_h9 = 9 * 0.74 / 2
        label_y1 = rl_y + row_h * 2 - row_h / 2 - cap_h9
        label_y2 = rl_y + row_h       - row_h / 2 - cap_h9

        c.setFont(F_BODY, 9)
        left_colon_x  = col1_x + max(c.stringWidth("Metaphase analysed",        F_BODY, 9),
                                     c.stringWidth("Estimated band resolution",  F_BODY, 9)) + 8
        right_colon_x = col3_x + max(c.stringWidth("Autosome",      F_BODY, 9),
                                     c.stringWidth("Sex chromosome", F_BODY, 9)) + 8
        left_val_x    = left_colon_x  + c.stringWidth(":", F_BODY, 9) + 10
        right_val_x   = right_colon_x + c.stringWidth(":", F_BODY, 9) + 10

        def _cell(lbl, val, lx, colon_x, val_x, ly):
            c.setFont(F_BODY, 9); c.setFillColor(BLACK)
            c.drawString(lx, ly, lbl)
            c.drawString(colon_x, ly, ":")
            c.drawString(val_x, ly, val)

        _cell("Metaphase analysed",       met_val,  col1_x, left_colon_x,  left_val_x,  label_y1)
        _cell("Autosome",                 auto_val, col3_x, right_colon_x, right_val_x, label_y1)
        _cell("Estimated band resolution",band_val, col1_x, left_colon_x,  left_val_x,  label_y2)
        _cell("Sex chromosome",           sex_val,  col3_x, right_colon_x, right_val_x, label_y2)

        return rl_y

    def _draw_recommendations_block(self, c, y: float) -> float:
        y = _draw_section_heading(c, "Recommendations", y)
        c.setFillColor(BLACK)
        default_items = [
            "Genetic counseling is recommended to discuss the implications of the result.",
            "Additional genetic testing may be warranted based on the specific phenotypic indication.",
        ]
        items = list(default_items)
        recs = self._get("RECOMMENDATIONS").strip()
        if recs:
            raw_items = [r.strip() for r in re.split(r'[\n\uf0b7\u2022]', recs) if r.strip()]
            custom_items = []
            for item in raw_items:
                if custom_items and item and item[0].islower():
                    custom_items[-1] = custom_items[-1] + " " + item
                else:
                    custom_items.append(item)
            seen_defaults = {d.strip().lower().rstrip('.') for d in default_items}
            custom_items = [it for it in custom_items
                            if it.strip().lower().rstrip('.') not in seen_defaults]
            items.extend(custom_items)
        y = _draw_bullet_list(c, items, DIV_X0, y - 18,
                              DIV_X1 - DIV_X0, F_BODY, 11)
        return y

    def _draw_methodology_block(self, c, y: float) -> float:
        y = _draw_section_heading(c, "Test Methodology", y)
        text = ("A 72-hour PHA-M stimulated culture of the received peripheral blood sample was "
                "processed, according to a protocol adapted from the AGT Cytogenetics Laboratory "
                "Manual, Third Edition. Numerical and structural chromosomal abnormalities were "
                "ruled out at a banding resolution suitable for the referral indication, in "
                "accordance with current ISCN guidelines.")
        c.setFillColor(BLACK)
        y = _draw_justified(c, text, DIV_X0, y - 10, DIV_X1 - DIV_X0, F_BODY, 11)
        return y

    def _draw_limitations_block(self, c, y: float) -> float:
        y = _draw_section_heading(c, "Limitations", y)
        items = [
            "All genetic disorders cannot be ruled out by conventional karyotyping.",
            "The accuracy of the test is about 99%.",
            "G-banded analysis cannot detect small rearrangements and submicroscopic deletions.",
            "Low-level mosaicism may not be detected.",
        ]
        c.setFillColor(BLACK)
        y = _draw_bullet_list(c, items, DIV_X0, y - 18, DIV_X1 - DIV_X0, F_BODY, 11)
        return y

    def _draw_references_block(self, c, y: float) -> float:
        y = _draw_section_heading(c, "References", y)
        refs = [
            ("1.", "The AGT Cytogenetics Laboratory Manual Third Edition (1997)  ",
             "Editors: Margaret J. Barch, TuridKnutsen, Jack L. Spurbeck."),
            ("2.", "ISCN- An International System for Human Cytogenetic Nomenclature (2024)  ",
             "Editors: Ros J. Hastings, Sarah Moore, Nicole Chia."),
        ]
        c.setFillColor(BLACK)
        indent = 22.0
        ref_w = DIV_X1 - DIV_X0 - indent
        ref_italic = F_ITALIC
        first_gap = 14
        inter_gap = 10
        for i, (num, normal_part, italic_part) in enumerate(refs):
            y -= (first_gap if i == 0 else inter_gap)
            c.setFont(F_BBOLD, 11)
            c.setFillColor(BLACK)
            c.drawString(DIV_X0, y, num)
            markup = (normal_part +
                      f'<font name="{ref_italic}" color="black"><i>{italic_part}</i></font>')
            style = ParagraphStyle(
                'ref_just',
                fontName=F_BODY,
                fontSize=11,
                leading=15.5,
                alignment=TA_JUSTIFY,
                wordWrap='LTR',
            )
            para = Paragraph(markup, style)
            pw, ph = para.wrap(ref_w, 9999)
            para.drawOn(c, DIV_X0 + indent, y - ph + 10)
            y = y - ph + 10
        return y

    def _draw_signatures(self, c, y: float):
        c.setFont(F_HDG, 14)
        c.setFillColor(DARK_BLUE)
        c.drawString(DIV_X0, y - 14, "This report has been reviewed and approved by:")

        sig_y  = y - 14 - 8
        sig_w  = 538.8 - 97.4
        sig_h  = 81.6
        sig_x  = 97.4
        c.drawImage(_img(_assets.SIGN_DEEPIKA),
                    sig_x,                  sig_y - sig_h,
                    sig_w / 3, sig_h, mask="auto")
        c.drawImage(_img(_assets.SIGN_TEENA),
                    sig_x + sig_w / 3,      sig_y - sig_h,
                    sig_w / 3, sig_h, mask="auto")
        c.drawImage(_img(_assets.SIGN_SURIYA),
                    sig_x + 2 * sig_w / 3,  sig_y - sig_h,
                    sig_w / 3, sig_h, mask="auto")
