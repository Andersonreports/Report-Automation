from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, PageBreak, Image, KeepTogether, CondPageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from PIL import Image as PILImage
import os
import sys
import base64
from io import BytesIO
from datetime import datetime
from pgta_assets import HEADER_LOGO_B64, FOOTER_BANNER_B64, SIGN_ANAND_B64, SIGN_SACHIN_B64, SIGN_DIRECTOR_B64
import pgta_classify as clf


def registered_or(name, registered, fallback):
    """Return name if it's in registered list, else return fallback."""
    return name if name in registered else fallback


class NumberedCanvas(canvas.Canvas):
    """Canvas that supports 'Page X of Y' numbering by deferring page writes until all pages are known."""

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for page_num, state in enumerate(self._saved_page_states, 1):
            self.__dict__.update(state)
            self._draw_page_number(page_num, num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_page_number(self, page_num, total_pages):
        self.saveState()
        self.setFont("Helvetica-Bold", 9)
        self.setFillColorRGB(0.12, 0.29, 0.49)
        self.drawCentredString(306, 118, f"Page {page_num} of {total_pages}")
        self.restoreState()


class PGTAReportTemplate:
 
    COLORS = {
        'patient_info_bg': '#F1F1F7',
        'results_header_bg': '#F9BE8F',
        'grey_bg': '#F2F2F2',
        'blue_title': '#1F497D',
        'approval_blue': '#4F81BD'
    }
    
    PAGE_WIDTH = 612
    PAGE_HEIGHT = 792
    MARGIN_LEFT = 58
    MARGIN_RIGHT = 58
    MARGIN_TOP = 90
    MARGIN_BOTTOM = 150
    DOSE_MARGIN_TOP = 100
    DOSE_MARGIN_BOTTOM = 150
    CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    
    ASSETS_DIR = "assets/pgta"
    HEADER_LOGO = os.path.join(ASSETS_DIR, "image_page1_0.png")
    FOOTER_BANNER = os.path.join(ASSETS_DIR, "image_page1_1.png")
    FOOTER_LOGO = os.path.join(ASSETS_DIR, "image_page1_2.png")
    
    METHODOLOGY_TEXT = """Chromosomal aneuploidy analysis was performed using ChromInst® PGT-A kit from Yikon Genomics (Suzhou) Co., Ltd - China. The Yikon - ChromInst® PGT-A kit with the Genemind - SURFSeq 5000* High-throughput Sequencing Platform allows detection of aneuploidies in all 23 sets of Chromosomes. Probes are not covering the p arm of acrocentric chromosomes as they are rich in repeat regions and RNA markers and devoid of genes. Changes in this region will not be detected. However, these regions have less clinical significance due to the absence of genes. Chromosomal aneuploidy can be detected by copy number variations (CNVs), which represent a class of variation in which segments of the genome have been duplicated (gains) or deleted (losses). Large, genomic copy number imbalances can range from sub-chromosomal regions to entire chromosomes. Inherited and de-novo CNVs (up to 10 Mb) have been associated with many disease conditions. This assay was performed on DNA extracted from embryo biopsy&nbsp;samples."""
    
    MOSAICISM_TEXT = """Mosaicism arises in the embryo due to mitotic errors which lead to the production of karyotypically distinct cell lineages within a single embryo [1]. NGS has the sensitivity to detect mosaicism when 30% or the above cells are abnormal [2]. Mosaicism is reported in our laboratory as follows [3]."""
    
    MOSAICISM_BULLETS = [
        "Embryos with less than 30% mosaicism are considered as euploid.",
        "Embryos with 30% to 50% mosaicism will be reported as low level mosaic, 51% to 80% mosaicism will be reported as high level mosaic.",
        "When three chromosomes or more than three chromosomes showing mosaic change, it will be denoted as complex mosaic.",
        "If greater than 80% mosaicism detected in an embryo it will be considered aneuploid."
    ]
    
    MOSAICISM_CLINICAL = """Clinical significance of transferring mosaic embryos is still under evaluation. Based on Preimplantation Genetic Diagnosis International Society (PGDIS) Position Statement – 2019, transfer of these embryos should be considered only after appropriate counselling of the patient and alternatives have been discussed. Invasive prenatal testing with karyotyping in the amniotic fluid needs to be advised in such cases [4]. As shown in published literature evidence, such transfers can result in normal pregnancy or miscarriage or an offspring with chromosomal mosaicism [5,6,7]."""
    
    LIMITATIONS = [
        "This technique cannot detect point mutations, balanced translocations, inversions, triploidy, uniparental disomy and epigenetic modifications.",
        "Probes used do not cover the p arm of acrocentric chromosomes as they are rich in repeat regions and RNA markers and devoid of genes. Changes in this region will not be detected. However, these regions have less clinical significance due to the absence of genes.",
        "Deletions and duplications with the size of < 10 Mb cannot be detected.",
        "Risk of misinterpretation of the actual embryo karyotype due to the presence of chromosomal mosaicism, either at cleavage-stage or at blastocyst stage may exist.",
        "This technique cannot detect variants of polyploidy and haploidy",
        "NGS without genotyping cannot identify the nature (meiotic or mitotic) nor the parental origin of aneuploidies",
        "Due to the intrinsic nature of chromosomal mosaicism, the chromosomal make-up achieved from a biopsy only may represent a picture of a small part of the embryo and may not necessarily reflect the chromosomal content of the entire embryo. Also, the mosaicism level inferred from a multi-cell TE biopsy might not unequivocally represent the exact chromosomal mosaicism percentage of the TE cells or the inner cell mass constitution."
    ]
    
    REFERENCES = [
        'McCoy, Rajiv C. "Mosaicism in Preimplantation human embryos: when chromosomal abnormalities are the norm." Trends in genetics 33.7 (2017): 448-463.',
        'ESHRE PGT-SR/PGT-A Working Group, et al. "ESHRE PGT Consortium good practice recommendations for the detection of structural and numerical chromosomal aberrations." Human reproduction open 2020.3 (2020): hoaa017.',
        'ESHRE Working Group on Chromosomal Mosaicism, et al. "ESHRE survey results and good practice recommendations on managing chromosomal mosaicism." Hum Reprod Open. 2022 Nov 7;2022(4):hoac044.',
        'Cram, D. S., et al. "PGDIS position statement on the transfer of mosaic embryos 2019." Reproductive biomedicine online 39 (2019): e1-e4.',
        'Victor, Andrea R., et al. "One hundred mosaic embryos transferred prospectively in a single clinic: exploring when and why they result in healthy pregnancies." Fertility and sterility 111.2 (2019): 280-293.',
        'Lin, Pin-Yao, et al. "Clinical outcomes of single mosaic embryo transfer: high-level or low-level mosaic embryo, does it matter?" Journal of clinical medicine 9.6 (2020): 1695.',
        'Kahraman, Semra, et al. "The birth of a baby with mosaicism resulting from a known mosaic embryo transfer: a case report." Human Reproduction 35.3 (2020): 727-733.'
    ]
    
    SIGNATURES = [
        {"name": "Anand Babu. K, Ph.D", "title": "Molecular Biologist"},
        {"name": "Sachin D Honguntikar, Ph.D", "title": "Molecular Geneticist"},
        {"name": "Dr Suriyakumar G", "title": "Director"}
    ]
    
    @staticmethod
    def get_resource_path(relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        return os.path.abspath(os.path.join(base_path, relative_path))

    def __init__(self, assets_dir="assets/pgta"):
        """Initialize template with asset directory"""
        self.ASSETS_DIR = self.get_resource_path(assets_dir)
        print(f"INFO: Assets Directory resolved to: {self.ASSETS_DIR}")
        
        self.HEADER_LOGO = os.path.join(self.ASSETS_DIR, "image_page1_0.png")
        self.FOOTER_BANNER = os.path.join(self.ASSETS_DIR, "image_page1_1.png")
        self.FOOTER_LOGO = os.path.join(self.ASSETS_DIR, "image_page1_2.png")
        self.GENQA_LOGO = os.path.join(self.ASSETS_DIR, "genqa_logo.png")
        self.SIGNS_IMAGE = os.path.join(self.ASSETS_DIR, "signs.png")
        
        for label, path in [("Header", self.HEADER_LOGO), ("Footer", self.FOOTER_BANNER), ("Signs", self.SIGNS_IMAGE)]:
            if not os.path.exists(path):
                print(f"CRITICAL: {label} missing at {path}")
            else:
                print(f"FOUND: {label} ({os.path.getsize(path)} bytes)")
        
        self.styles = getSampleStyleSheet()
        self._register_fonts()
        self._create_custom_styles()
    
    def _register_fonts(self):
        """Register custom fonts if they exist in assets/fonts.
        Uses a case-insensitive file scan so font files work regardless
        of whether they were uploaded with uppercase or mixed-case names.
        """
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase.pdfmetrics import registerFontFamily

        fonts_dir = os.path.join(self.ASSETS_DIR, "fonts")
        if not os.path.exists(fonts_dir):
            return

        available = {}
        for fname in os.listdir(fonts_dir):
            available[fname.lower()] = fname

        def _find(candidates):
            for c in candidates:
                key = c.lower()
                if key in available:
                    return os.path.join(fonts_dir, available[key])
            return None

        font_configs = [
            ('SegoeUI',               ['SegoeUI.ttf', 'SEGOEUI.TTF']),
            ('SegoeUI-Bold',          ['SegoeUI-Bold.ttf', 'SEGOEUIB.TTF']),
            ('SegoeUI-Italic',        ['SegoeUI-Italic.ttf', 'SEGOEUII.TTF']),
            ('SegoeUI-BoldItalic',    ['SegoeUI-BoldItalic.ttf', 'SEGOEUIZ.TTF']),
            ('GillSansMT',            ['GillSansMT.ttf', 'GillSans.ttf', 'GIL_____.TTF']),
            ('GillSansMT-Bold',       ['GillSansMT-Bold.ttf', 'GillSansMTBold.ttf', 'GILB____.TTF']),
            ('GillSansMT-Italic',     ['GillSansMT-Italic.ttf', 'GILI____.TTF']),
            ('GillSansMT-BoldItalic', ['GillSansMT-BoldItalic.ttf', 'GILBI___.TTF']),
            ('Calibri',               ['Calibri.ttf', 'CALIBRI.TTF']),
            ('Calibri-Bold',          ['Calibri-Bold.ttf', 'CALIBRIB.TTF']),
            ('Calibri-Italic',        ['Calibri-Italic.ttf', 'CALIBRII.TTF']),
            ('Calibri-BoldItalic',    ['Calibri-BoldItalic.ttf', 'CALIBRIZ.TTF']),
        ]

        registered = []
        for name, candidates in font_configs:
            font_path = _find(candidates)
            if font_path:
                try:
                    pdfmetrics.registerFont(TTFont(name, font_path))
                    registered.append(name)
                    print(f"Registered font: {name} <- {os.path.basename(font_path)}")
                except Exception as e:
                    print(f"Error registering font {name}: {e}")

        if 'SegoeUI' in registered and 'SegoeUI-Bold' in registered:
            registerFontFamily('SegoeUI', normal='SegoeUI', bold='SegoeUI-Bold',
                               italic=registered_or('SegoeUI-Italic', registered, 'SegoeUI'),
                               boldItalic=registered_or('SegoeUI-BoldItalic', registered, 'SegoeUI-Bold'))
        if 'GillSansMT-Bold' in registered:
            _gill_normal = 'GillSansMT' if 'GillSansMT' in registered else 'GillSansMT-Bold'
            registerFontFamily('GillSansMT', normal=_gill_normal, bold='GillSansMT-Bold',
                               italic=registered_or('GillSansMT-Italic', registered, _gill_normal),
                               boldItalic=registered_or('GillSansMT-BoldItalic', registered, 'GillSansMT-Bold'))
        if 'Calibri' in registered and 'Calibri-Bold' in registered:
            registerFontFamily('Calibri', normal='Calibri', bold='Calibri-Bold',
                               italic=registered_or('Calibri-Italic', registered, 'Calibri'),
                               boldItalic=registered_or('Calibri-BoldItalic', registered, 'Calibri-Bold'))
    
    def _get_font(self, name, fallback):
        """Helper to get best available font"""
        try:
            from reportlab.pdfbase import pdfmetrics
            pdfmetrics.getFont(name)
            return name
        except:
            return fallback

    def _create_custom_styles(self):
        """Create custom paragraph styles"""

        self.styles.add(ParagraphStyle(
            name='PGTAReportTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            leading=18,
            textColor=colors.HexColor(self.COLORS['blue_title']),
            alignment=TA_CENTER,
            spaceAfter=12,
            fontName=self._get_font('GillSansMT-Bold', 'Helvetica-Bold')
        ))

        self.styles.add(ParagraphStyle(
            name='PGTASectionHeader',
            parent=self.styles['Heading2'],
            fontSize=11,
            leading=13,
            textColor=colors.HexColor(self.COLORS['blue_title']),
            spaceBefore=12,
            spaceAfter=3,
            keepWithNext=True,
            fontName=self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        ))
        
        self.styles.add(ParagraphStyle(
            name='PGTABodyText',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=13,
            alignment=TA_JUSTIFY,
            fontName=self._get_font('Calibri', 'Helvetica')
        ))
        
        self.styles.add(ParagraphStyle(
            name='PGTASmallText',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10,
            fontName=self._get_font('SegoeUI', 'Helvetica')
        ))
        
        self.styles.add(ParagraphStyle(
            name='PGTADisclaimer',
            parent=self.styles['Normal'],
            fontSize=10.5, 
            leading=12,
            alignment=TA_CENTER,
            fontName=self._get_font('SegoeUI-SemiboldItalic', 'Helvetica-BoldOblique'),
            textColor=colors.black
        ))
        
        self.styles.add(ParagraphStyle(
            name='PGTABulletText',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=13,
            leftIndent=20,
            bulletIndent=10,
            alignment=TA_JUSTIFY,
            fontName=self._get_font('Calibri', 'Helvetica')
        ))
        
        self.styles.add(ParagraphStyle(
            name='PGTASigApproval',
            parent=self.styles['Normal'],
            fontSize=12.48,
            leading=14.5,
            textColor=colors.HexColor(self.COLORS['approval_blue']),
            fontName=self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        ))
        
        self.styles.add(ParagraphStyle(
            name='PGTACenteredBodyText',
            parent=self.styles['PGTABodyText'],
            alignment=TA_CENTER
        ))
        
        self.styles.add(ParagraphStyle(
            name='PGTALeftBodyText',
            parent=self.styles['PGTABodyText'],
            alignment=TA_LEFT
        ))
        
        self.styles.add(ParagraphStyle(
            name='PGTALabelText',
            parent=self.styles['Normal'],
            fontSize=10, 
            leading=12,
            alignment=TA_LEFT,
            wordWrap='CJK',
            fontName=self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        ))

        self.styles.add(ParagraphStyle(
            name='PGTALabelTextRight',
            parent=self.styles['Normal'],
            fontSize=10, 
            leading=12,
            alignment=TA_RIGHT,
            wordWrap='CJK',
            fontName=self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        ))

        self.styles.add(ParagraphStyle(
            name='PGTABannerValueText',
            parent=self.styles['Normal'],
            fontSize=10, 
            leading=12,
            alignment=TA_LEFT,
            fontName=self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        ))
    
    def _get_grid_style(self):
        """Return grid style if enabled"""
        if hasattr(self, 'show_grid') and self.show_grid:
            return [('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0"))]
        return []

    def generate_pdf(self, output_path, patient_data, embryos_data, show_logo=True, show_grid=False):
        """Generate PGT-A report PDF"""
        self.show_grid = show_grid
        top_margin = self.MARGIN_TOP if show_logo else self.DOSE_MARGIN_TOP
        bottom_margin = self.MARGIN_BOTTOM if show_logo else self.DOSE_MARGIN_BOTTOM
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=self.MARGIN_LEFT,
            rightMargin=self.MARGIN_RIGHT,
            topMargin=top_margin,
            bottomMargin=bottom_margin
        )
        
        self._show_logo = show_logo
        
        story = []
        
        story.extend(self._build_cover_page(patient_data, embryos_data))
        story.extend(self._build_methodology_page(embryos_data))
        
        all_low_dna = True if embryos_data else False
        for embryo in embryos_data:
            interp = str(embryo.get('interpretation', '')).upper()
            res = str(embryo.get('result_summary', '')).upper()
            if "LOW DNA" not in interp and "LOW DNA" not in res:
                all_low_dna = False
                break

        if all_low_dna:
            story.append(Spacer(1, 24))
            story.append(self._create_signature_table())
        else:
            story.append(PageBreak())
        
        for idx, embryo in enumerate(embryos_data):
            interp = str(embryo.get('interpretation', '')).upper()
            res = str(embryo.get('result_summary', '')).upper()
            if "LOW DNA" in interp or "LOW DNA" in res:
                continue
                
            story.extend(self._build_embryo_page(patient_data, embryo))
            story.append(Spacer(1, 12))
            story.append(self._create_signature_table())
            story.append(PageBreak())
        
        doc.build(story, onFirstPage=self._add_header_footer,
                  onLaterPages=self._add_header_footer,
                  canvasmaker=NumberedCanvas)
        
        return output_path
    
    def _add_header_footer(self, canvas, doc):
        """Add header and footer to each page using Base64 assets for robustness"""
        show_logo = getattr(self, '_show_logo', True)
            
        canvas.saveState()
        
        def draw_b64_img(b64_str, x, y, w, h):
            try:
                img_data = base64.b64decode(b64_str)
                img = PILImage.open(BytesIO(img_data))
                canvas.drawInlineImage(img, x, y, width=w, height=h, preserveAspectRatio=True)
                return True
            except Exception as e:
                print(f"Error drawing Base64 image: {e}")
                return False

        if show_logo:
            def natural_height(b64, target_w):
                try:
                    img = PILImage.open(BytesIO(base64.b64decode(b64)))
                    pw, ph = img.size
                    return target_w * ph / pw
                except:
                    return 72

            cw = self.CONTENT_WIDTH
            hdr_h = natural_height(HEADER_LOGO_B64, cw)
            ftr_h = natural_height(FOOTER_BANNER_B64, cw)

            draw_b64_img(HEADER_LOGO_B64, self.MARGIN_LEFT, 792 - hdr_h, cw, hdr_h)
            draw_b64_img(FOOTER_BANNER_B64, self.MARGIN_LEFT, 0, cw, ftr_h)

        if os.path.exists(self.GENQA_LOGO):
             try:
                 genqa_w = 67
                 genqa_x = self.MARGIN_LEFT + self.CONTENT_WIDTH - genqa_w
                 canvas.drawImage(self.GENQA_LOGO, genqa_x, 66.5, width=genqa_w, height=36, preserveAspectRatio=True, mask='auto')
             except:
                 pass
        
        canvas.restoreState()
    
    def _build_cover_page(self, patient_data, embryos_data):
        """Build cover page with patient info and results summary"""
        elements = []
        
        title_style = self.styles['PGTAReportTitle']
        title = Paragraph(
            "Preimplantation Genetic Testing for Aneuploidies (PGT-A)",
            title_style
        )
        elements.append(title)
        elements.append(Spacer(1, 6))
        
        patient_table = self._create_patient_info_table(patient_data)
        elements.append(patient_table)
        elements.append(Spacer(1, 12))
        
        disclaimer = Paragraph(
            "<b>This test does not reveal sex of the fetus & confers to PNDT act, 1994</b>",
            self.styles['PGTADisclaimer']
        )
        disclaimer_table = Table([[disclaimer]], colWidths=[490], hAlign='CENTER')
        disclaimer_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(self.COLORS['grey_bg'])),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ] + self._get_grid_style()))
        elements.append(KeepTogether(disclaimer_table))
        elements.append(Spacer(1, 12))
        
        if 'indication' in patient_data and patient_data['indication']:
            elements.append(self._create_section_header("Indication"))
            elements.append(Spacer(1, 8))
            indication_text = Paragraph(patient_data['indication'], self.styles['PGTABodyText'])
            elements.append(indication_text)
            elements.append(Spacer(1, 12))
        
        elements.append(self._create_section_header("Results summary"))
        elements.append(Spacer(1, 8))
        
        results_table = self._create_results_summary_table(embryos_data)
        elements.append(results_table)
        elements.append(Spacer(1, 8))
        
        results_summary_comment = self._clean(patient_data.get('results_summary_comment', ''))
        if results_summary_comment:
            comment_para = Paragraph(results_summary_comment, self.styles['PGTABodyText'])
            elements.append(comment_para)
            elements.append(Spacer(1, 8))
        
        elements.append(Spacer(1, 4))
        
        return elements
    
    def _clean(self, val, default=""):
        """Sanitize value to remove 'nan' and trim whitespace"""
        if val is None: return default
        s = str(val).strip()
        if s.lower() == "nan": return default
        return s
    
    def _wrap_text(self, text, bold=False, font_size=None, align='LEFT', max_width=None):
        """Wrap text in a Paragraph for table cells, with automatic Line Break support"""
        if not text: return ""
        
        content = str(text).replace('\r\n', '\n').replace('\r', '\n')
        content = content.replace('\n', '<br/>\u00A0')
        content = content.strip(' \t\r\f\v')
        
        if content.lower() == "nan" or content.lower() == "<br/>":
            if content.lower() != "<br/>":
                return "" if content.lower() == "nan" else Paragraph(content, self.styles['PGTALeftBodyText'])
            
        if align == 'CENTER':
            style_name = 'PGTACenteredBodyText'
        elif align == 'LEFT':
            style_name = 'PGTALeftBodyText'
        else:
            style_name = 'PGTABodyText'
        
        use_style = self.styles[style_name]
        if font_size:
            use_style = ParagraphStyle(
                name=f'{style_name}_custom_{font_size}',
                parent=self.styles[style_name],
                fontSize=font_size,
                leading=font_size * 1.2
            )
            
        final_text = content
        if bold:
            if not (final_text.startswith('<b>') and final_text.endswith('</b>')):
                final_text = f"<b>{content}</b>"
            
        return Paragraph(final_text, use_style)

    def _wrap_label(self, text):
        """Wrap label text with forced RIGHT alignment and no word gaps"""
        if not text: return ""
        return Paragraph(f"<nobr>{str(text)}</nobr>", self.styles['PGTALabelText'])

    def _create_patient_info_table(self, patient_data):
        """Create patient information table"""
        
        import re
        patient_name = re.sub(r'\s+', ' ', self._clean(patient_data.get('patient_name'))).strip()
        spouse_name = re.sub(r'\s+', ' ', self._clean(patient_data.get('spouse_name'))).strip()
        combined_name = f"{patient_name}<br/>{spouse_name}" if spouse_name else patient_name
        
        data = [
            [self._wrap_text('<b>PATIENT NAME</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{combined_name}</b>", max_width=140), self._wrap_text('<b>PIN</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('pin'))}</b>", max_width=144)],
            [self._wrap_text('<b>DATE OF BIRTH/ AGE</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('age'))}</b>", max_width=140), self._wrap_text('<b>SAMPLE NUMBER</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('sample_number'))}</b>", max_width=144)],
            [self._wrap_text('<b>REFERRING CLINICIAN</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('referring_clinician'))}</b>", max_width=140), self._wrap_text('<b>BIOPSY DATE</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('biopsy_date'))}</b>", max_width=144)],
            [self._wrap_text('<b>HOSPITAL/CLINIC</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('hospital_clinic'))}</b>", max_width=140), self._wrap_text('<b>SAMPLE COLLECTION DATE</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('sample_collection_date'))}</b>", max_width=144)],
            [self._wrap_text('<b>SPECIMEN</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('specimen'))}</b>", max_width=140), self._wrap_text('<b>SAMPLE RECEIPT DATE</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('sample_receipt_date'))}</b>", max_width=144)],
            [self._wrap_text('<b>BIOPSY PERFORMED BY</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('biopsy_performed_by'))}</b>", max_width=140), self._wrap_text('<b>REPORT DATE</b>', True), self._wrap_text(':'), self._wrap_text(f"<b>{self._clean(patient_data.get('report_date'))}</b>", max_width=144)]
        ]
        
        table = Table(data, colWidths=[108, 12, 161, 108, 12, 89], hAlign='LEFT')
        
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self._get_font('SegoeUI-Bold', 'Helvetica-Bold')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (0, -1), 4),
            ('LEFTPADDING', (3, 0), (3, -1), 4),
            ('LEFTPADDING', (1, 0), (2, -1), 0),
            ('LEFTPADDING', (4, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(self.COLORS['patient_info_bg'])),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ] + self._get_grid_style()))

        return table

    def _create_results_summary_table(self, embryos_data):
        """Create results summary table"""
        header_labels = ['S. No.', 'Sample', 'Result', 'MTcopy', 'Interpretation']
        data = [[self._wrap_text(label, bold=True, align='CENTER') for label in header_labels]]

        for idx, embryo in enumerate(embryos_data, 1):
            raw_result = self._clean(embryo.get('result_summary') or embryo.get('result_description') or '')
            
            info = clf.classify_embryo(raw_result)
            res_sum = info["summary_text"]

            if info["classification"] == clf.LOW_DNA:
                interp_text = "NA"
            else:
                interp_text = self._clean(embryo.get('interpretation'), '')
                if not interp_text:
                    interp_text = info["classification"].replace("_", " ").title() if info["is_mosaic"] else "NA"

            auto_val = self._clean(embryo.get('autosomes')).upper()
            sex_val = self._clean(embryo.get('sex_chromosomes', 'Normal')).upper()
            is_auto_norm = not auto_val.strip() or "NORMAL" in auto_val or "EUPLOID" in auto_val
            is_sex_norm = "NORMAL" in sex_val
            if is_auto_norm and is_sex_norm and clf.is_ambiguous_or_normal_interp(interp_text):
                interp_text = "Euploid"
            interp = interp_text

            result_color = self._classify_color(raw_result)
            interp_display_color = self._get_interp_only_color(interp_text)

            raw_mt = self._clean(embryo.get('mtcopy'), 'NA')
            mtcopy = raw_mt if interp_text.upper() == "EUPLOID" else "NA"

            full_id = self._clean(embryo.get('embryo_id'))
            short_id = full_id
            if '-' in full_id:
                parts = full_id.split('-')
                if len(parts) >= 2:
                    id_part = parts[1]
                    short_id = id_part.split('_')[0] if '_' in id_part else id_part

            data.append([
                self._wrap_text(str(idx), align='CENTER'),
                self._wrap_text(short_id, align='CENTER'),
                self._wrap_text(self._wrap_colored(res_sum, result_color, bold=False), align='CENTER'),
                self._wrap_text(mtcopy, align='CENTER'),
                self._wrap_text(self._wrap_colored(interp, interp_display_color, bold=False), align='CENTER'),
            ])
        
        table = Table(data, colWidths=[50, 95, 185, 80, 86])
        
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), self._get_font('Calibri-Bold', 'Helvetica-Bold')),
            ('FONTNAME', (0, 1), (-1, -1), self._get_font('Calibri', 'Helvetica')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(self.COLORS['results_header_bg'])),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor(self.COLORS['patient_info_bg'])),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ] + self._get_grid_style()))
        
        return table
    
    def _build_methodology_page(self, embryos_data=None):
        """Build methodology and static content page - sections flow continuously"""
        elements = []

        elements.append(self._create_section_header("Methodology"))
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(self.METHODOLOGY_TEXT, self.styles['PGTABodyText']))
        elements.append(Spacer(1, 12))

        elements.append(KeepTogether([
            self._create_section_header("Conditions for reporting mosaicism"),
            Spacer(1, 8),
            Paragraph(self.MOSAICISM_TEXT, self.styles['PGTABodyText']),
        ]))
        elements.append(Spacer(1, 6))
        for bullet in self.MOSAICISM_BULLETS:
            elements.append(Paragraph(f"• {bullet}", self.styles['PGTABulletText']))
        elements.append(Spacer(1, 6))

        if clf.any_mosaic(embryos_data or []):
            elements.append(Paragraph(self.MOSAICISM_CLINICAL, self.styles['PGTABodyText']))
        elements.append(Spacer(1, 12))

        elements.append(self._create_section_header("Limitations"))
        elements.append(Spacer(1, 8))
        for limitation in self.LIMITATIONS:
            elements.append(Paragraph(f"• {limitation}", self.styles['PGTABulletText']))

        elements.append(Spacer(1, 12))
        elements.append(Spacer(1, 12))

        ref_block = [self._create_section_header("References"), Spacer(1, 8)]
        for idx, ref in enumerate(self.REFERENCES, 1):
            ref_block.append(Paragraph(f"{idx}. {ref}", self.styles['PGTABodyText']))
        elements.append(KeepTogether(ref_block))

        return elements
    
    def _build_embryo_page(self, patient_data, embryo_data):
        """Build individual embryo results page"""
        elements = []
        
        title = Paragraph(
            "Preimplantation Genetic Testing for Aneuploidies (PGT-A)",
            self.styles['PGTAReportTitle']
        )
        elements.append(title)
        elements.append(Spacer(1, 8))
        
        def _wrap_banner(text):
            if not text: return ""
            return Paragraph(str(text), self.styles['PGTABannerValueText'])

        patient_name = self._clean(patient_data.get('patient_name'))
        spouse_name = self._clean(patient_data.get('spouse_name'))
        combined_name = f"{patient_name}<br/>{spouse_name}" if spouse_name else patient_name

        info_data = [[
            self._wrap_label('PATIENT NAME:'),
            _wrap_banner(f"<b>{combined_name}</b>"),
            Paragraph(f"<nobr>PIN:</nobr>", self.styles['PGTALabelTextRight']),
            _wrap_banner(f"<b>{self._clean(patient_data.get('pin'))}</b>")
        ]]
        
        info_table = Table(info_data, colWidths=[82, 254, 24, 130], hAlign='LEFT')
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(self.COLORS['patient_info_bg'])),
            ('FONTNAME', (0, 0), (-1, -1), self._get_font('SegoeUI-Bold', 'Helvetica-Bold')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (0, -1), 4),
            ('LEFTPADDING', (1, 0), (1, -1), 0),
            ('LEFTPADDING', (2, 0), (2, -1), 0),
            ('LEFTPADDING', (3, 0), (3, -1), 4),
            ('RIGHTPADDING', (0, 0), (0, -1), 0),
            ('RIGHTPADDING', (1, 0), (1, -1), 0),
            ('RIGHTPADDING', (2, 0), (2, -1), 4),
            ('RIGHTPADDING', (3, 0), (3, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ] + self._get_grid_style()))
        elements.append(info_table)
        elements.append(Spacer(1, 8))
        
        disclaimer = Paragraph(
            "<b>This test does not reveal sex of the fetus & confers to PNDT act, 1994</b>",
            self.styles['PGTADisclaimer']
        )
        disclaimer_table = Table([[disclaimer]], colWidths=[490], hAlign='CENTER')
        disclaimer_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(self.COLORS['grey_bg'])),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ] + self._get_grid_style()))
        elements.append(KeepTogether(disclaimer_table))
        elements.append(Spacer(1, 12))
        
        raw_result = self._clean(embryo_data.get('result_summary') or embryo_data.get('result_description') or '')
        info = clf.classify_embryo(raw_result)

        res_text = info["result_text"]

        existing_auto = self._clean(embryo_data.get('autosomes', ''))
        chr_statuses = embryo_data.get('chromosome_statuses') or {}
        if not chr_statuses:
            chr_statuses = clf.derive_chromosome_statuses(raw_result)
            chr_statuses = clf.validate_statuses(chr_statuses, raw_result)
        autosomes_text = clf.derive_autosomes(raw_result, chr_statuses, existing_auto)

        existing_sex = self._clean(embryo_data.get('sex_chromosomes', ''))
        sex_text = clf.sanitize_sex_chromosomes(existing_sex, raw_result, info["classification"])

        interp_text = self._clean(embryo_data.get('interpretation'), 'NA')
        is_auto_norm = not autosomes_text.strip() or "NORMAL" in autosomes_text.upper() or "EUPLOID" in autosomes_text.upper()
        is_sex_norm = "NORMAL" in sex_text.upper()
        if is_auto_norm and is_sex_norm and clf.is_ambiguous_or_normal_interp(interp_text):
            interp_text = "Euploid"
        interp_color = self._get_interp_only_color(interp_text)

        auto_color = colors.black
        auto_upper = autosomes_text.upper()
        
        if "MULTIPLE CHROMOSOMAL ABNORMALITIES" in res_text.upper():
            auto_color = colors.red
        elif 'NORMAL' in auto_upper or 'EUPLOID' in auto_upper or not autosomes_text.strip():
            auto_color = colors.black
        elif '%' in autosomes_text:
            auto_color = colors.blue
        elif any(x in auto_upper for x in ['DEL(', 'DUP(', '-', '+', 'STATUS L', 'STATUS G', 'STATUS SL', 'STATUS SG', ' SL', ' SG', ' L,', ' G,', ' L ', ' G ']) or auto_upper.endswith(' L') or auto_upper.endswith(' G'):
            auto_color = colors.red
        elif 'CNV STATUS' in auto_upper:
            auto_color = colors.red

        interp_upper_for_auto = interp_text.upper()
        if 'ANEUPLOID' in interp_upper_for_auto or 'CHAOTIC' in interp_upper_for_auto:
            auto_color = colors.red
        elif 'MOSAIC' in interp_upper_for_auto:
            auto_color = colors.blue
        elif 'INCONCLUSIVE' in interp_upper_for_auto:
            auto_color = colors.black

        sex_up = sex_text.upper().strip()
        sex_color = colors.black
        if "MOSAIC" in sex_up:
            sex_color = colors.blue
        elif sex_up and sex_up not in ("NORMAL", "NO RESULT"):
            sex_color = colors.red

        raw_mt = self._clean(embryo_data.get('mtcopy', ''), 'NA')
        mtcopy = raw_mt if interp_text.upper() == "EUPLOID" else "NA"

        detail_embryo_id = self._clean(embryo_data.get('embryo_id_detail')) or self._clean(embryo_data.get('embryo_id'))
        if '-' in detail_embryo_id:
            parts = detail_embryo_id.split('-')
            if len(parts) >= 2:
                id_part = parts[1]
                detail_embryo_id = id_part.split('_')[0] if '_' in id_part else id_part

        embryo_id_style = ParagraphStyle(
            name='EmbryoIDStyle',
            parent=self.styles['Normal'],
            fontSize=12,
            leading=14,
            fontName=self._get_font('GillSansMT-Bold', 'Helvetica-Bold'),
            textColor=colors.HexColor(self.COLORS['blue_title'])
        )
        elements.append(Paragraph(f"<b>EMBRYO: {detail_embryo_id}</b>", embryo_id_style))
        elements.append(Spacer(1, 6))

        detail_data = [
            [self._wrap_text(f"<b>Result:</b> {self._wrap_colored(res_text, colors.black, bold=False)}", False)],
            [self._wrap_text(f"<b>Autosomes:</b> {self._wrap_colored(autosomes_text, auto_color, bold=False)}", False)],
            [self._wrap_text(f"<b>Sex Chromosomes:</b> {self._wrap_colored(sex_text, sex_color, bold=False)}", False)],
            [self._wrap_text(f"<b>Interpretation:</b> {self._wrap_colored(interp_text, interp_color, bold=False)}", False)],
            [self._wrap_text(f"<b>MTcopy:</b> {mtcopy}", False)],
        ]
        
        detail_table = Table(detail_data, colWidths=[490], hAlign='CENTER')
        detail_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(self.COLORS['patient_info_bg'])),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ] + self._get_grid_style()))
        elements.append(detail_table)
        elements.append(Spacer(1, 12))
        
        elements.append(self._create_section_header("COPY NUMBER CHART", show_line=False))
        elements.append(Spacer(1, 6))
        
        if 'cnv_image_path' in embryo_data and embryo_data['cnv_image_path'] and os.path.exists(embryo_data['cnv_image_path']):
            try:
                img = Image(embryo_data['cnv_image_path'], width=self.CONTENT_WIDTH)
                
                aspect = img.imageWidth / img.imageHeight
                img.drawHeight = self.CONTENT_WIDTH / aspect
                
                img.hAlign = 'CENTER'
                elements.append(img)
                elements.append(Spacer(1, 12))
            except Exception as e:
                print(f"Error loading image: {e}")
        
        result_summary = self._clean(embryo_data.get('result_summary', ''))
        result_desc = self._clean(embryo_data.get('result_description', ''))
        is_inconclusive = "INCONCLUSIVE" in result_summary.upper() or "INCONCLUSIVE" in result_desc.upper() or "INCONCLUSIVE" in interp_text.upper()
        
        if is_inconclusive:
            inconclusive_comment = self._clean(embryo_data.get('inconclusive_comment', ''))
            if inconclusive_comment:
                comment_para = Paragraph(
                    f"{inconclusive_comment}",
                    self.styles['PGTABodyText']
                )
                elements.append(comment_para)
                elements.append(Spacer(1, 12))
        
        if not is_inconclusive:
            cnv_table = self._create_cnv_table(embryo_data)
            elements.append(cnv_table)
            elements.append(Spacer(1, 6))
            
            legend = Paragraph(
                "<i>N – Normal, G-Gain, L-Loss, SG-Segmental Gain, SL-Segmental Loss, "
                "M-Mosaic, MG- Mosaic Gain, ML-Mosaic Loss, SMG-Segmental Mosaic Gain, "
                "SML-Segmental Mosaic Loss</i>",
                self.styles['PGTASmallText']
            )
            elements.append(legend)
            elements.append(Spacer(1, 12))
        
        return elements
    
    def _create_cnv_table(self, embryo_data):
        """Create CNV status table"""
        chr_statuses = embryo_data.get('chromosome_statuses') or {}
        if not chr_statuses:
            raw_result = self._clean(embryo_data.get('result_summary') or embryo_data.get('result_description') or '')
            chr_statuses = clf.derive_chromosome_statuses(raw_result)
            chr_statuses = clf.validate_statuses(chr_statuses, raw_result)
        mosaic_percentages = embryo_data.get('mosaic_percentages', {})
        
        autosomes = str(embryo_data.get('autosomes', '')).upper()
        sex_chrs = str(embryo_data.get('sex_chromosomes', '')).upper()
        
        import re as re_mos
        has_mosaic = any(
            v and str(v).strip() and str(v).strip() != '-' and re_mos.search(r'\d', str(v))
            for v in mosaic_percentages.values()
        )
        
        is_autosomes_normal = 'NORMAL' in autosomes or 'EUPLOID' in autosomes or not autosomes.strip()
        is_sex_mosaic = 'MOSAIC' in sex_chrs
        
        if is_autosomes_normal and is_sex_mosaic:
            has_mosaic = False
            
        if has_mosaic:
            header = [self._wrap_text('Chromosome', bold=True, align='CENTER', font_size=9)] + [self._wrap_text(str(i), bold=True, align='CENTER', font_size=9) for i in range(1, 23)]
            cnv_row = [self._wrap_text('CNV status', bold=True, align='CENTER', font_size=9)]
            mosaic_row = [self._wrap_text('Mosaic (%)', bold=True, align='CENTER', font_size=9)]
            
            for i in range(1, 23):
                status = chr_statuses.get(str(i), 'N')
                perc = mosaic_percentages.get(str(i), '-')
                s_color = self._get_status_color(status)
                
                f_size = 8 if len(status) > 2 else 9
                cnv_row.append(self._wrap_text(self._wrap_colored(status, s_color, bold=True), bold=True, font_size=f_size, align='CENTER'))
                mosaic_row.append(self._wrap_text(self._wrap_colored(str(perc), s_color, bold=True), bold=True, font_size=9, align='CENTER'))
            
            data = [header, cnv_row, mosaic_row]
            col_widths = [75] + [19.13] * 22
        else:
            header = [self._wrap_text('Chromosome', bold=True, align='CENTER', font_size=9)] + [self._wrap_text(str(i), bold=True, align='CENTER', font_size=9) for i in range(1, 23)]
            cnv_row = [self._wrap_text('CNV status', bold=True, align='CENTER', font_size=9)]
            for i in range(1, 23):
                status = chr_statuses.get(str(i), 'N')
                s_color = self._get_status_color(status)

                f_size = 8 if len(status) > 2 else 9
                cnv_row.append(self._wrap_text(self._wrap_colored(status, s_color, bold=True), bold=True, font_size=f_size, align='CENTER'))

            data = [header, cnv_row]
            col_widths = [75] + [19.13] * 22

        table = Table(data, colWidths=col_widths)
        
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self._get_font('SegoeUI-Bold', 'Helvetica-Bold')),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(self.COLORS['patient_info_bg'])),
            ('GRID', (0, 0), (-1, -1), 1.0, colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (1, 0), (-1, -1), 0),
            ('RIGHTPADDING', (1, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ] + self._get_grid_style()))
        
        return table

    def _create_signature_table(self):
        """Create signature section with precise structural metrics from source PDF"""
        elements = []
        
        elements.append(Paragraph(
            "<b>This report has been reviewed and approved by: </b>", 
            self.styles['PGTASigApproval']
        ))
        elements.append(Spacer(1, 12.7))
        
        try:
            from io import BytesIO
            def get_sig_img(b64):
                if not b64: return Paragraph('', self.styles['Normal'])
                img_data = base64.b64decode(b64)
                return Image(BytesIO(img_data), width=100, height=40)

            sig1 = get_sig_img(SIGN_ANAND_B64)
            sig2 = get_sig_img(SIGN_SACHIN_B64)
            sig3 = get_sig_img(SIGN_DIRECTOR_B64)
            
            sig_img_table = Table([[sig1, sig2, sig3]], colWidths=[156, 156, 156])
            sig_img_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ] + self._get_grid_style()))
            elements.append(sig_img_table)
        except Exception as e:
            print(f"Error drawing individual signatures: {e}")

        data = []
        names_row = []
        titles_row = []
        
        sig_name_style = ParagraphStyle('SigName', parent=self.styles['Normal'], 
                                       fontName=self._get_font('SegoeUI', 'Helvetica'), 
                                       fontSize=11.04, alignment=TA_CENTER)
        sig_title_style = ParagraphStyle('SigTitle', parent=self.styles['Normal'], 
                                        fontName=self._get_font('SegoeUI', 'Helvetica'), 
                                        fontSize=11.04, alignment=TA_CENTER)

        for sig in self.SIGNATURES:
            names_row.append(Paragraph(sig['name'], sig_name_style))
            titles_row.append(Paragraph(sig['title'], sig_title_style))
        
        data = [names_row, titles_row]
        
        table = Table(data, colWidths=[156, 156, 156])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0, colors.white),
            ('BOX', (0, 0), (-1, -1), 0, colors.white),
            ('LINEABOVE', (0, 0), (-1, -1), 0, colors.white),
            ('LINEBELOW', (0, 0), (-1, -1), 0, colors.white),
            ('LINEBEFORE', (0, 0), (-1, -1), 0, colors.white),
            ('LINEAFTER', (0, 0), (-1, -1), 0, colors.white),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ] + self._get_grid_style()))
        
        elements.append(table)
        
        return KeepTogether(elements)

    def _create_section_header(self, text, show_line=True):
        """Create a section header with navy blue text and a slight lighter line below"""
        header = Paragraph(f"<b>{text}</b>", self.styles["PGTASectionHeader"])
        
        if not show_line:
            return KeepTogether([header])
            
        header_table = Table([[header]], colWidths=[490], hAlign='CENTER')
        header_table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#989998")),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ] + self._get_grid_style()))
        return KeepTogether(header_table)

    def _classify_color(self, result_text):
        """Red for Aneuploid/Segmental, Blue for Mosaic, Black for Euploid/Inconclusive"""
        cls = clf.classify_embryo(result_text)["classification"]
        if cls in (clf.ANEUPLOID, clf.SEGMENTAL):
            return colors.red
        if cls in (clf.LOW_MOSAIC, clf.HIGH_MOSAIC, clf.COMPLEX_MOSAIC):
            return colors.blue
        return colors.black

    def _get_interp_only_color(self, interp_text):
        """Color driven strictly by the Interpretation text itself (NA/Inconclusive always black)"""
        i = (interp_text or "").upper()
        if any(kw in i for kw in ("ANEUPLOID", "CHAOTIC", "(-)")):
            return colors.red
        if "MOSAIC" in i:
            return colors.blue
        return colors.black

    def _get_autosome_color(self, autosome_text):
        """Special color logic for autosomes field"""
        if not autosome_text: return colors.black
        txt = autosome_text.upper()
        if "MULTIPLE CHROMOSOMAL ABNORMALITIES" in txt:
            return colors.red
        if "MULTIPLE MOSAIC CHROMOSOME COMPLEMENT" in txt:
            return colors.blue
        return colors.black

    def _get_status_color(self, status):
        """Color logic for CNV status codes"""
        if not status: return colors.black
        s = status.upper().strip()
        
        red_combos = ["SL/SG", "SG/SL"]
        blue_combos = ["SML/SMG", "SMG/SML"]
        if s in red_combos: return colors.red
        if s in blue_combos: return colors.blue
        
        red_codes = ["G", "L", "SG", "SL"]
        blue_codes = ["M", "MG", "ML", "SMG", "SML"]
        if s in red_codes: return colors.red
        if s in blue_codes: return colors.blue
        
        try:
            val = float(s.replace('%', ''))
            if val > 0: return colors.blue
        except:
            pass
            
        return colors.black

    def _wrap_colored(self, text, color, bold=False):
        """Standard wrapper for colored text with optional bolding"""
        if not text: return text
        if color == colors.black:
            return f"<b>{text}</b>" if bold else str(text)
        hex_color = color.hexval()[2:]
        if len(hex_color) > 6: hex_color = hex_color[:6]
        
        if bold:
            return f'<b><font color="#{hex_color}">{text}</font></b>'
        return f'<font color="#{hex_color}">{text}</font>'


if __name__ == "__main__":
    template = PGTAReportTemplate()
    
    patient_data = {
        'patient_name': 'Mrs. Priya (PNM00791)',
        'patient_spouse': 'Mrs. Priya (PNM00791)',
        'spouse_name': 'Mr. Saranraj',
        'pin': 'AND25630004206',
        'age': '34 Years',
        'sample_number': '632504349',
        'referring_clinician': 'Dr. Ajantha. B',
        'biopsy_date': '03-01-2026',
        'hospital_clinic': 'Rhea Healthcare Private Limited Annanagar (NOVA IVF)',
        'sample_collection_date': '03-01-2026',
        'specimen': 'DAY 5 TROPHECTODERM BIOPSY',
        'sample_receipt_date': '03-01-2026',
        'biopsy_performed_by': 'Raj Priya Pandian',
        'report_date': '14-01-2026',
        'indication': 'History of implantation failure.'
    }
    
    embryos_data = [
        {
            'embryo_id': 'PS4',
            'result_summary': 'Trisomy of chromosome 16',
            'mtcopy': 'NA',
            'interpretation': 'Aneuploid',
            'result_description': 'The embryo contains abnormal chromosome complement',
            'autosomes': 'Trisomy of chromosome 16',
            'sex_chromosomes': 'Normal',
            'chromosome_statuses': {str(i): 'N' for i in range(1, 23)},
            'mosaic_percentages': {},
            'cnv_image_path': os.path.join(os.path.dirname(os.path.abspath(__file__)), "PRIYA-PS4_L00_R1_noXY_nomos.png")
        }
    ]
    
    embryos_data[0]['chromosome_statuses']['16'] = 'SML'
    
    output_path = "test_report.pdf"
    template.generate_pdf(output_path, patient_data, embryos_data, show_grid=True)
    print(f"Test report generated: {output_path}")
