
import os
import re
import sys
import base64
import tempfile
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, PageBreak, Image, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

from nipt_assets import (
    HEADER_LOGO_B64, FOOTER_BANNER_B64, GENQA_LOGO_B64,
    ALGO_CHART_B64, SACHIN_SIGN_B64, DIRECTOR_SIGN_B64,
)

_FONTS_REGISTERED = False
_IMG_HEADER:   bytes = None
_IMG_FOOTER:   bytes = None
_IMG_GENQA:    bytes = None
_IMG_ALGO:     bytes = None
_IMG_SACHIN:   bytes = None
_IMG_DIRECTOR: bytes = None

def _ensure_fonts_registered():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    base_path = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(base_path, "fonts")
    if not os.path.exists(fonts_dir):
        fonts_dir = os.path.join(base_path, "assets", "pgta", "fonts")
    if not os.path.exists(fonts_dir):
        _FONTS_REGISTERED = True
        return
    font_configs = [
        ('SegoeUI',        'SEGOEUI.TTF'),
        ('SegoeUI-Bold',   'SEGOEUIB.TTF'),
        ('GillSansMT',     'GIL_____.TTF'),
        ('GillSansMT-Bold','GILB____.TTF'),
        ('Calibri',        'CALIBRI.TTF'),
        ('Calibri-Bold',   'CALIBRIB.TTF'),
    ]
    registered = []
    for name, fname in font_configs:
        fp = os.path.join(fonts_dir, fname)
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont(name, fp))
                registered.append(name)
            except Exception:
                pass
    if 'SegoeUI' in registered and 'SegoeUI-Bold' in registered:
        registerFontFamily('SegoeUI', normal='SegoeUI', bold='SegoeUI-Bold')
    if 'GillSansMT' in registered and 'GillSansMT-Bold' in registered:
        registerFontFamily('GillSansMT', normal='GillSansMT', bold='GillSansMT-Bold')
    if 'Calibri' in registered and 'Calibri-Bold' in registered:
        registerFontFamily('Calibri', normal='Calibri', bold='Calibri-Bold')
    _FONTS_REGISTERED = True

def _ensure_images_decoded():
    global _IMG_HEADER, _IMG_FOOTER, _IMG_GENQA, _IMG_ALGO, _IMG_SACHIN, _IMG_DIRECTOR
    if _IMG_HEADER   is None: _IMG_HEADER   = base64.b64decode(HEADER_LOGO_B64)
    if _IMG_FOOTER   is None: _IMG_FOOTER   = base64.b64decode(FOOTER_BANNER_B64)
    if _IMG_GENQA    is None: _IMG_GENQA    = base64.b64decode(GENQA_LOGO_B64)
    if _IMG_ALGO     is None: _IMG_ALGO     = base64.b64decode(ALGO_CHART_B64)
    if _IMG_SACHIN   is None: _IMG_SACHIN   = base64.b64decode(SACHIN_SIGN_B64)
    if _IMG_DIRECTOR is None: _IMG_DIRECTOR = base64.b64decode(DIRECTOR_SIGN_B64)

try:
    _ensure_fonts_registered()
    _ensure_images_decoded()
except Exception:
    pass


class NIPTReportTemplate:
    
    COLORS = {
        'blue_header': '#1F497D',
        'low_risk': '#15803D',
        'high_risk': '#B91C1C',
        'grey_text': '#666666',
        'patient_info_bg': '#F1F1F7',
        'results_header_bg': '#F9BE8F',
        'grey_bg': '#F2F2F2'
    }
    
    PAGE_WIDTH = 612
    PAGE_HEIGHT = 792
    MARGIN_LEFT = 50
    MARGIN_RIGHT = 50
    MARGIN_TOP = 40
    MARGIN_BOTTOM = 80
    CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    
    METHODOLOGY_TEXT = """Maternal whole blood sample was taken from the pregnant mother after 10-week gestation with no risk to the fetus. The circulating cell-free placental DNA was isolated and purified, which was then converted into genomic DNA library using Yourgene cfDNA Library prep kit. This was followed by automated size selection of fragment lengths by QS250 for enriching fetal fraction. The enriched sample pool was subjected to high throughput sequencing using Ion GeneStudio S5 Plus™ System. Finally, analysis was performed using Sage Link V2."""
    
    LIMITATIONS_TEXT = [
        "Test performance is valid only for full chromosomal aneuploidies involving all the autosomes and sex chromosomes with an accuracy of up to 99% for aneuploidies pertaining to chromosomes 13, 18 and 21. The method is intended for use in pregnant women who are at least 10+ weeks pregnant. The method is suitable for both singleton and twin pregnancies. The accuracy may be slightly lower in twin pregnancies due to multiple sources of fetal DNA. Patients with malignancy or a history of malignancy, patients with bone marrow or organ transplant, patients pregnant with more than 2 fetuses are not eligible for the test.",
        "<b>For vanishing twins, sampling must be performed 8 weeks after vanishing event.</b> The test is not intended and not validated for mosaicism, triploidy, partial trisomy/monosomy, uniparental disomy or translocations. Other genomic abnormalities not covered by this assay may impact the phenotype.",
        "A high risk result for twin pregnancies indicates high probability for the presence of at least one affected fetus.",
        "<b>Pregnant women with a low risk test result do not ensure an unaffected pregnancy as this is a screening test.</b> Although this test is accurate, there is still a small possibility for false positive or false negative results. This may be caused by technical and/or biological limitations, including but not limited to confined placental mosaicism (CPM) or other types of mosaicism, maternal constitutional or somatic chromosomal abnormalities, residual cfDNA from a vanished twin or other rare molecular events.",
        "<b>This test is not a diagnostic but a screening test and results should be considered in the context of other clinical criteria.</b> Clinical correlation with ultrasound findings, and other clinical data and tests is recommended.",
        "<b>If definitive diagnosis is desired, invasive prenatal testing by chorionic villus biopsy (CVS) or amniocentesis is necessary.</b> The referral clinician is responsible for counselling before and after the test including the provision of advice regarding the need for additional invasive genetic testing."
    ]
    
    DISCLAIMER_TEXT = """No irreversible actions should be taken based solely upon the results of this screening test. The manner in which this information is used to guide patient care is the responsibility of the health care provider, including advising for the need for genetic counseling or diagnostic testing. Any test should be interpreted in the context of all available clinical findings. As with any screening test, any positive result should be confirmed with diagnostic testing."""
    
    REFERENCES = [
        "Bianchi DW, Platt LD, Goldberg JD, Abuhamad AZ, Sehnert AJ, Rava RP. Genome-wide fetal aneuploidy detection by maternal plasma DNA sequencing. <i>Obstetrics & Gynecology</i>. 2012 May 1;119(5):890-901.",
        "Chiu RW, Akolekar R, Zheng YW, Leung TY, Sun H, Chan KA, Lun FM, Go AT, Lau ET, To WW, Leung WC. Non-invasive prenatal assessment of trisomy 21 by multiplexed maternal plasma DNA sequencing: large scale validity study. <i>Bmj</i>. 2011 Jan 11;342:c7401.",
        "Chiu RW, Lo YM. Noninvasive prenatal diagnosis empowered by high‐throughput sequencing. <i>Prenatal diagnosis</i>. 2012 Apr 1;32(4):401-6.",
        "Dugoff L. Cell-Free DNA Screening for Fetal Aneuploidy. <i>Topics in Obstetrics & Gynecology</i>. 2017 Jan 15;37(1):1-7."
    ]
    
    SIGNATURES = [
        {"name": "Dr. Sachin D. Honguntikar", "title": "Head – Anderson Clinical Genetics"},
        {"name": "Dr. Suriyakumar.G", "title": "Director"}
    ]
    
    def __init__(self, output_path):
        self.output_path = output_path
        self.doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=self.MARGIN_LEFT,
            rightMargin=self.MARGIN_RIGHT,
            topMargin=self.MARGIN_TOP,
            bottomMargin=self.MARGIN_BOTTOM
        )
        self.styles = getSampleStyleSheet()
        _ensure_fonts_registered()
        _ensure_images_decoded()
        self._create_custom_styles()

    def _get_font(self, name, fallback):
        try:
            pdfmetrics.getFont(name)
            return name
        except:
            return fallback

    def _create_custom_styles(self):
        main_font = self._get_font('SegoeUI', 'Helvetica')
        main_bold = self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        header_font = self._get_font('GillSansMT-Bold', 'Helvetica-Bold')
        
        self.styles.add(ParagraphStyle(
            name='NIPS_Header',
            fontSize=18,
            textColor=colors.HexColor(self.COLORS['blue_header']),
            alignment=TA_RIGHT,
            fontName=header_font
        ))
        self.styles.add(ParagraphStyle(
            name='Section_Header',
            fontSize=16,
            textColor=colors.HexColor(self.COLORS['blue_header']),
            alignment=TA_LEFT,
            spaceBefore=6,
            spaceAfter=4,
            fontName=header_font
        ))
        self.styles.add(ParagraphStyle(
            name='Label',
            fontSize=10,
            textColor=colors.black,
            fontName=main_bold
        ))
        self.styles.add(ParagraphStyle(
            name='Label_White',
            fontSize=10,
            textColor=colors.white,
            fontName=main_bold
        ))
        self.styles.add(ParagraphStyle(
            name='Value',
            fontSize=10,
            textColor=colors.black,
            fontName=main_font
        ))
        self.styles.add(ParagraphStyle(
            name='Result_Green',
            fontSize=10,
            textColor=colors.HexColor(self.COLORS['low_risk']),
            fontName=self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        ))
        self.styles.add(ParagraphStyle(
            name='Result_Red',
            fontSize=10,
            textColor=colors.HexColor(self.COLORS['high_risk']),
            fontName=self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        ))
        self.styles.add(ParagraphStyle(
            name='Detail_Text',
            fontSize=10,
            textColor=colors.black,
            fontName=main_font,
            alignment=TA_JUSTIFY,
            leading=13
        ))
        self.styles.add(ParagraphStyle(
            name='Sig_Name',
            fontSize=11,
            textColor=colors.black,
            fontName=main_font,
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name='Sig_Title',
            fontSize=10,
            textColor=colors.black,
            fontName=main_font,
            alignment=TA_CENTER
        ))

    def generate(self, data, z_scores, with_logo=True):
        if not with_logo:
            self.doc = SimpleDocTemplate(
                self.output_path,
                pagesize=letter,
                leftMargin=self.MARGIN_LEFT,
                rightMargin=self.MARGIN_RIGHT,
                topMargin=self.MARGIN_TOP + 15,
                bottomMargin=self.MARGIN_BOTTOM + 13,
            )

        story = []

        def header_footer(canvas, doc):
            canvas.saveState()
            if with_logo:
                try:
                    img = Image(BytesIO(_IMG_HEADER), width=self.CONTENT_WIDTH, height=75)
                    img.drawOn(canvas, self.MARGIN_LEFT, self.PAGE_HEIGHT - 65)
                except: pass

            if with_logo:
                try:
                    f_img = Image(BytesIO(_IMG_FOOTER), width=468, height=66)
                    f_img.drawOn(canvas, 72, 10)
                except: pass

            try:
                gq_img = Image(BytesIO(_IMG_GENQA), width=85, height=40)
                gq_img.drawOn(canvas, self.PAGE_WIDTH - self.MARGIN_RIGHT - 85, 78)
            except: pass
            canvas.setFont(self._get_font('GillSansMT', 'Helvetica'), 12)
            canvas.setFillColor(colors.black)
            canvas.drawRightString(self.PAGE_WIDTH - self.MARGIN_RIGHT, 74, f"Page {doc.page} of 6")
            canvas.restoreState()

        if with_logo:
            story.append(Spacer(1, 30))
        else:
            story.append(Spacer(1, 15))
        
        title_style = ParagraphStyle(
            name='Title',
            fontName=self._get_font('GillSansMT-Bold', 'Helvetica-Bold'),
            fontSize=18,
            textColor=colors.HexColor(self.COLORS['blue_header']),
            alignment=TA_CENTER,
            spaceAfter=15
        )
        story.append(Paragraph("Non-Invasive Prenatal Screening (NIPS)", title_style))
        story.append(Spacer(1, 2))
        
        story.append(self._create_patient_grid(data))
        story.append(Spacer(1, 3))
        
        pndt_style = ParagraphStyle(name='PNDT', parent=self.styles['Value'], alignment=TA_CENTER)
        pndt_p = Paragraph("<font name='Helvetica-BoldOblique'><i><b>This test does not reveal sex of the fetus &amp; confers to PNDT act, 1994</b></i></font>", pndt_style)
        pndt_t = Table([[pndt_p]], colWidths=[self.CONTENT_WIDTH])
        pndt_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(self.COLORS['grey_bg'])),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(pndt_t)
        story.append(Spacer(1, 5))
        
        story.append(self._create_section_header("Test Indication"))
        story.append(Spacer(1, 2))
        story.append(Paragraph(data.get('indication') or 'To screen for chromosomal aneuploidies', self.styles['Value']))
        story.append(Spacer(1, 4))
        
        story.append(self._create_section_header("Test Performed"))
        story.append(Spacer(1, 2))
        story.append(Paragraph("NIPS for 23 pairs of chromosomes (including sex chromosomal aneuploidies)", self.styles['Value']))
        story.append(Spacer(1, 4))
        
        ff = z_scores.get('fetal_fraction', 0)
        overall_risk = "Low risk"
        is_high = any(z_scores.get(f'chr{i}', 0) > (2.8 if i in [13,18,21] else 6.0) for i in range(1, 23))
        if is_high or z_scores.get('chrX', 0) > 6.0: overall_risk = "High risk"
        
        story.append(self._create_section_header("Result Summary"))
        story.append(Spacer(1, 3))
        res_text_left = f"<b>Screen result: </b><font color='{self.COLORS['low_risk'] if overall_risk=='Low risk' else self.COLORS['high_risk']}'><b>{overall_risk}</b></font>"
        res_text_right = f"<b>Fetal fraction: {ff:.2f}%</b>"
        
        res_style = ParagraphStyle(name='RS_Text', parent=self.styles['Value'], alignment=TA_CENTER)
        res_t = Table([[Paragraph(res_text_left, res_style), Paragraph(res_text_right, res_style)]], colWidths=[self.CONTENT_WIDTH*0.5, self.CONTENT_WIDTH*0.5])
        res_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(self.COLORS['patient_info_bg'])),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(res_t)
        story.append(Spacer(1, 4))
        
        story.append(self._create_summary_table(z_scores))
        
        story.append(PageBreak())
        
        story.append(Spacer(1, 40))
        story.append(self._create_detailed_table(z_scores))
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>*As per PCPNDT act, the reference Z scores for sex chromosomal aneuploidies will not be provided.</b>", self.styles['Value']))
        
        story.append(PageBreak())
        
        story.append(Spacer(1, 30))
        story.append(self._create_section_header("Interpretation and follow-up"))
        story.append(Spacer(1, 5))
        interp = [
            f"The results show {overall_risk.lower()} for all the autosomes and sex chromosomes.",
            "The fetal fraction was sufficient for analysis.",
            "A low risk result means that the baby has a low probability of having the condition listed in the report. The results should be communicated by the clinician with appropriate counseling.",
            "A low-risk result does not eliminate the possibility of aneuploidy or other genetic disorders.",
            "All results must be correlated with clinical findings, ultrasound, and maternal risk factors.",
            "Diagnostic confirmation is strongly recommended if any of the below are:<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Positive/high-risk NIPT<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Ultrasound abnormalities<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;High-risk maternal age or prior affected pregnancy<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;No-call/low fetal fraction samples"
        ]
        for line in interp:
            story.append(Paragraph(f"• {line}", self.styles['Detail_Text']))
        
        story.append(Spacer(1, 10))
        story.append(self._create_section_header("Recommendation"))
        story.append(Spacer(1, 5))
        story.append(Paragraph("• Genetic counseling is recommended.", self.styles['Detail_Text']))
        story.append(Paragraph("• If ultrasound/NT scan shows any abnormality or serum markers indicate high risk, invasive testing by amniocentesis with chromosomal microarray is mandated even if NIPS is low risk.", self.styles['Detail_Text']))
        
        story.append(Spacer(1, 10))
        story.append(self._create_section_header("Test Method"))
        story.append(Spacer(1, 5))
        story.append(Paragraph(self.METHODOLOGY_TEXT, self.styles['Detail_Text']))
        
        story.append(Spacer(1, 10))
        story.append(self._create_section_header("Test Limitations"))
        story.append(Spacer(1, 5))
        for p in self.LIMITATIONS_TEXT[:2]:
            story.append(Paragraph(p, self.styles['Detail_Text']))
            story.append(Spacer(1, 4))
        
        story.append(PageBreak())
        
        story.append(Spacer(1, 40))
        for p in self.LIMITATIONS_TEXT[2:]:
            story.append(Paragraph(p, self.styles['Detail_Text']))
            story.append(Spacer(1, 4))
        
        story.append(Spacer(1, 10))
        story.append(self._create_section_header("Regulatory & Validation Notes"))
        story.append(Spacer(1, 5))
        story.append(Paragraph("Test performance is based on laboratory-validated parameters; results may vary across populations and platforms. Not intended for use in multi-fetal reduction, mosaic embryo transfer, or post-transplant pregnancies.", self.styles['Detail_Text']))
        
        story.append(Spacer(1, 10))
        story.append(self._create_section_header("Disclaimer"))
        story.append(Spacer(1, 5))
        story.append(Paragraph(self.DISCLAIMER_TEXT, self.styles['Detail_Text']))
        
        story.append(PageBreak())
        
        story.append(Spacer(1, 30))
        story.append(self._create_section_header("Test specifications"))
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Table 1: Performance of Sage 32 NIPT workflow in singleton pregnancies</b>", self.styles['Value']))
        story.append(Spacer(1, 10))
        story.append(self._create_metrics_table_1())
        story.append(Spacer(1, 5))
        story.append(Paragraph("PPV – Positive predictive value; NPV – Negative predictive value; FPR – False positive rate; FNR – False negative rate", ParagraphStyle('tiny', parent=self.styles['Detail_Text'], fontSize=7, alignment=TA_CENTER)))
        story.append(Spacer(1, 20))
        story.append(Paragraph("<b>Table 2: Performance of Sage 32 NIPT workflow in twin pregnancies</b>", self.styles['Value']))
        story.append(Spacer(1, 10))
        story.append(self._create_metrics_table_2())
        story.append(Spacer(1, 5))
        story.append(Paragraph("PPV – Positive predictive value; NPV – Negative predictive value; FPR – False positive rate; FNR – False negative rate", ParagraphStyle('tiny', parent=self.styles['Detail_Text'], fontSize=7, alignment=TA_CENTER)))
        
        story.append(PageBreak())
        
        story.append(Spacer(1, 15))
        story.append(self._create_section_header("Prenatal Testing Algorithm"))
        story.append(Spacer(1, 5))
        try:
            img_algo = Image(BytesIO(_IMG_ALGO), width=self.CONTENT_WIDTH, height=250)
            story.append(img_algo)
        except:
            story.append(Paragraph("[Algorithm Flowchart Placeholder]", self.styles['Detail_Text']))
        story.append(Spacer(1, 10))
        
        story.append(self._create_section_header("References"))
        story.append(Spacer(1, 5))
        for i, ref in enumerate(self.REFERENCES, 1):
            story.append(Paragraph(f"{i}. {ref}", self.styles['Detail_Text']))
            story.append(Spacer(1, 5))
            
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"<font color='{self.COLORS['blue_header']}'><b>This report has been reviewed and approved by:</b></font>", self.styles['Value']))
        story.append(Spacer(1, 10))
        story.append(self._create_signature_row())
        
        self.doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
        return self.output_path

    def _create_section_header(self, text):
        header = Paragraph(f"{text}", self.styles['Section_Header'])
        header_table = Table([[header]], colWidths=[self.CONTENT_WIDTH])
        header_table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.5, colors.HexColor(self.COLORS['blue_header'])),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ]))
        return KeepTogether([header_table])

    def _create_patient_grid(self, data):
        main_bold = self._get_font('SegoeUI-Bold', 'Helvetica-Bold')
        lbl_style = ParagraphStyle('Lbl', fontName=main_bold, fontSize=10, leading=14)
        val_style = ParagraphStyle('Val', fontName=main_bold, fontSize=10, leading=14)
        
        def L(txt): return Paragraph(f"<b>{txt}</b>", lbl_style)
        def V(txt): return Paragraph(f"<b>: {txt}</b>", val_style)
        
        def fmt_date(d):
            if not d: return ""
            d = str(d).strip()
            m = re.match(r'(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})', d)
            if m: return f"{int(m.group(3)):02d}/{int(m.group(2)):02d}/{m.group(1)}"
            m = re.match(r'(\d{1,2})[-\/](\d{1,2})[-\/](\d{4})', d)
            if m: return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
            m = re.match(r'[A-Za-z]{3}\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})', d)
            if m:
                _months = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                           'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
                mo = _months.get(m.group(1).lower())
                if mo: return f"{int(m.group(2)):02d}/{mo:02d}/{m.group(3)}"
            return d

        _preg_abbr = re.compile(r'\b([A-Za-z]{1,5})\b')
        def fmt_preg(text):
            return _preg_abbr.sub(lambda mo: mo.group().upper(), text.title())

        _dob = fmt_date(data.get('dob',''))
        _age = str(data.get('age','') or '').strip()
        if _dob and _age:
            dob_age_label, dob_age_value = "Date of Birth / Age", f"{_dob} / {_age}"
        elif _dob:
            dob_age_label, dob_age_value = "Date of Birth", _dob
        elif _age:
            dob_age_label, dob_age_value = "Age", _age
        else:
            dob_age_label, dob_age_value = "Date of Birth / Age", ""
        _clin_name = data.get('clinician', '')
        _clin_qual = data.get('clinician_qual', '').strip()
        clinician_display = f"{_clin_name}, {_clin_qual}" if _clin_name and _clin_qual else _clin_name or _clin_qual
        table_data = [
            [L("Patient name"), V(data.get('name','')), L("Specimen"), V(data.get('specimen','Peripheral blood').title())],
            [L(dob_age_label), V(dob_age_value), L("PIN"), V(data.get('pin',''))],
            [L("Gestational Age"), V(data.get('ga','')), L("Sample Number"), V(data.get('sample_id',''))],
            [L("Pregnancy Type; status"), V(f"{fmt_preg(data.get('preg_type',''))}; {fmt_preg(data.get('preg_status',''))}".strip('; ')), L("Sample collection date"), V(fmt_date(data.get('collection_date','')))],
            [L("Referring Clinician"), V(clinician_display), L("Sample received date"), V(fmt_date(data.get('received_date','')))],
            [L("Hospital/Clinic"), V(data.get('hospital','')), L("Report date"), V(fmt_date(data.get('report_date', datetime.now().strftime('%d/%m/%Y'))))]
        ]
        
        w = self.CONTENT_WIDTH
        col_widths = [w*0.20, w*0.38, w*0.22, w*0.20]

        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), main_bold),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 3),
            ('RIGHTPADDING', (0,0), (-1,-1), 3),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(self.COLORS['patient_info_bg'])),
        ]))
        return t
    def _create_summary_table(self, z_scores):
        header_style_center = ParagraphStyle(name='ST_Header_C', parent=self.styles['Label'], alignment=TA_CENTER)
        header = [Paragraph("Aneuploidies", header_style_center), Paragraph("Results", header_style_center)]
        table_data = [header]
        targets = [
            ("Chromosome 21", z_scores.get('chr21', 0), 2.8),
            ("Chromosome 18", z_scores.get('chr18', 0), 2.8),
            ("Chromosome 13", z_scores.get('chr13', 0), 2.8),
            ("Sex Chromosomes*", z_scores.get('chrX', 0), 6.0),
            ("Other Autosomes", 0, 6.0)
        ]
        
        value_style_center = ParagraphStyle(name='ST_Value_Center', parent=self.styles['Value'], alignment=TA_CENTER)
        
        for name, val, thresh in targets:
            risk = "Low risk" if val <= thresh else "High risk"
            risk_color = self.COLORS['low_risk'] if risk == "Low risk" else self.COLORS['high_risk']
            risk_text = f"<font color='{risk_color}'><b>{risk}</b></font>"
            table_data.append([Paragraph(name, value_style_center), Paragraph(risk_text, value_style_center)])
            
        t = Table(table_data, colWidths=[self.CONTENT_WIDTH*0.5, self.CONTENT_WIDTH*0.5])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor(self.COLORS['results_header_bg'])),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.white),
            ('BOX', (0,0), (-1,-1), 0.5, colors.white),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor(self.COLORS['grey_bg'])])
        ]))
        return t

    def _create_detailed_table(self, z_scores):
        header_style = ParagraphStyle(name='DT_Header', parent=self.styles['Value'], fontName=self._get_font('SegoeUI-Bold', 'Helvetica-Bold'), alignment=TA_CENTER)
        
        hdr = [
            Paragraph("<b>Chromosome tested</b>", header_style),
            Paragraph("<b>Z Score</b>", header_style),
            Paragraph("<b>Test result</b>", header_style),
            Paragraph("<b>Reference interval</b>", header_style)
        ]
        table_data = [hdr]
        
        value_style_center = ParagraphStyle(name='DT_Value_Center', parent=self.styles['Value'], alignment=TA_CENTER)
        
        for i in range(1, 23):
            val = z_scores.get(f'chr{i}', 0)
            thresh = 2.8 if i in [13, 18, 21] else 6.0
            risk = "Low risk" if val <= thresh else "High risk"
            ref = "-6&lt;Z score&lt;2.8" if i in [13, 18, 21] else "-6&lt;Z score&lt;6"
            table_data.append([
                Paragraph(f"Chromosome {i}", value_style_center),
                Paragraph(f"{val:.2f}", value_style_center),
                Paragraph(risk, value_style_center),
                Paragraph(ref, value_style_center)
            ])
            
        t = Table(table_data, colWidths=[self.CONTENT_WIDTH*0.3, self.CONTENT_WIDTH*0.2, self.CONTENT_WIDTH*0.2, self.CONTENT_WIDTH*0.3])
        t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(self.COLORS['results_header_bg'])),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, colors.white),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor(self.COLORS['grey_bg'])])
    ]))
        return t

    def _create_signature_row(self):
        try:
            img_sachin   = Image(BytesIO(_IMG_SACHIN),   width=100, height=40)
            img_director = Image(BytesIO(_IMG_DIRECTOR), width=100, height=40)
            table_data = [
                [img_sachin, img_director],
                [Paragraph(self.SIGNATURES[0]['name'], self.styles['Sig_Name']), Paragraph(self.SIGNATURES[1]['name'], self.styles['Sig_Name'])],
                [Paragraph(self.SIGNATURES[0]['title'], self.styles['Sig_Title']), Paragraph(self.SIGNATURES[1]['title'], self.styles['Sig_Title'])]
            ]
        except:
            table_data = [
                [Paragraph("", self.styles['Sig_Name']), Paragraph("", self.styles['Sig_Name'])],
                [Paragraph(self.SIGNATURES[0]['name'], self.styles['Sig_Name']), Paragraph(self.SIGNATURES[1]['name'], self.styles['Sig_Name'])],
                [Paragraph(self.SIGNATURES[0]['title'], self.styles['Sig_Title']), Paragraph(self.SIGNATURES[1]['title'], self.styles['Sig_Title'])]
            ]
        t = Table(table_data, colWidths=[self.CONTENT_WIDTH*0.5, self.CONTENT_WIDTH*0.5])
        t.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        return t

    def _create_metrics_table_1(self):
        header_style = ParagraphStyle(name='MT_Header', parent=self.styles['Label'], alignment=TA_CENTER)
        hdr = [Paragraph(f"<b>{x}</b>", header_style) for x in ["Condition", "Sensitivity", "Specificity", "PPV", "NPV", "FPR", "FNR"]]
        data = [
            hdr,
            ["Trisomy 21", "99% <font size='5.5'>95%CI:99.49-100%</font>", ">99% <font size='5.5'>95%CI:99.99-100%</font>", ">99.99%", "99.99%", "<0.1%", "0.1%"],
            ["Trisomy 18", "99% <font size='5.5'>95%CI:96.82-99.99%</font>", ">99% <font size='5.5'>95%CI:99.99-100%</font>", ">99.99%", "99.99%", "<0.1%", "0.58%"],
            ["Trisomy 13", ">99% <font size='5.5'>95%CI:96.87-100%</font>", ">99% <font size='5.5'>95%CI:99.99-100%</font>", ">99.99%", ">99.99%", "<0.1%", "<0.1%"],
            ["<b>Sex chromosomal\naneuploidies</b>", ">98 % <font size='5.5'>95%CI:99.31-100%</font>", ">98% <font size='5.5'>95%CI:99.99-100%</font>", "99.81%", ">99.99%", "0.0014%", "<0.01%"],
            ["<b>Other autosomal\naneuploidies</b>", ">90% <font size='5.5'>95%CI:98.03-100%</font>", ">90% <font size='5.5'>95%CI:99.99-100%</font>", ">99.99%", ">99.99%", "<0.01%", "<0.01%"]
        ]
        
        formatted_data = []
        value_style_center = ParagraphStyle(name='MT_Value_Center', parent=self.styles['Value'], alignment=TA_CENTER)
        
        for i, row in enumerate(data):
            if i == 0:
                formatted_data.append(row)
                continue
            
            formatted_row = []
            for j, cell in enumerate(row):
                if isinstance(cell, str):
                    if j == 0 and not cell.startswith('<b>'):
                        cell = f"<b>{cell}</b>"
                    formatted_row.append(Paragraph(cell.replace('\n', '<br/>'), value_style_center))
                else:
                    formatted_row.append(cell)
            formatted_data.append(formatted_row)
            
        t = Table(formatted_data, colWidths=[self.CONTENT_WIDTH*0.22, self.CONTENT_WIDTH*0.15, self.CONTENT_WIDTH*0.15, self.CONTENT_WIDTH*0.12, self.CONTENT_WIDTH*0.12, self.CONTENT_WIDTH*0.12, self.CONTENT_WIDTH*0.12])
        t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(self.COLORS['results_header_bg'])),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,1), (-1,-1), 8),
        ('TOPPADDING', (0,1), (-1,-1), 8),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, colors.white),
        ('FONTNAME', (0,0), (-1,-1), self._get_font('SegoeUI', 'Helvetica')),
        ('FONTSIZE', (0,0), (-1,-1), 8),
    ]))
        for i in range(1, len(data)):
            t.setStyle(TableStyle([('BACKGROUND', (0,i), (0,i), colors.HexColor('#E2E2E2'))]))
            t.setStyle(TableStyle([('BACKGROUND', (1,i), (-1,i), colors.HexColor(self.COLORS['grey_bg']))]))
        
        return t

    def _create_metrics_table_2(self):
        header_style = ParagraphStyle(name='MT_Header2', parent=self.styles['Label'], alignment=TA_CENTER)
        hdr = [Paragraph(f"<b>{x}</b>", header_style) for x in ["Condition", "Sensitivity", "Specificity", "PPV", "NPV", "FPR", "FNR"]]
        data = [
            hdr,
            ["Trisomy 21", ">98%", ">98%", ">99.99%", ">99.99%", "<0.01%", "<0.01%"],
            ["Trisomy 18", ">98%", ">98%", ">98%", ">99.99%", "<0.01%", "<0.01%"],
            ["Trisomy 13", ">98%", ">98%", ">98%", ">99.99%", "<0.01%", "<0.01%"],
            ["<b>Sex chromosomal\naneuploidies</b>", ">97%", ">97%", ">97%", ">99.99%", "0.0014%", "<0.01%"],
            ["<b>Other autosomal\naneuploidies</b>", ">95%", ">95%", ">95%", ">99.99%", "<0.01%", "<0.01%"]
        ]
        
        formatted_data = []
        value_style_center = ParagraphStyle(name='MT_Value_Center2', parent=self.styles['Value'], alignment=TA_CENTER)
        
        for i, row in enumerate(data):
            if i == 0:
                formatted_data.append(row)
                continue
            
            formatted_row = []
            for j, cell in enumerate(row):
                if isinstance(cell, str):
                    if j == 0 and not cell.startswith('<b>'):
                        cell = f"<b>{cell}</b>"
                    formatted_row.append(Paragraph(cell.replace('\n', '<br/>'), value_style_center))
                else:
                    formatted_row.append(cell)
            formatted_data.append(formatted_row)
            
        t = Table(formatted_data, colWidths=[self.CONTENT_WIDTH*0.22, self.CONTENT_WIDTH*0.15, self.CONTENT_WIDTH*0.15, self.CONTENT_WIDTH*0.12, self.CONTENT_WIDTH*0.12, self.CONTENT_WIDTH*0.12, self.CONTENT_WIDTH*0.12])
        t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(self.COLORS['results_header_bg'])),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,1), (-1,-1), 8),
        ('TOPPADDING', (0,1), (-1,-1), 8),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, colors.white),
        ('FONTNAME', (0,0), (-1,-1), self._get_font('SegoeUI', 'Helvetica')),
        ('FONTSIZE', (0,0), (-1,-1), 8),
    ]))
        for i in range(1, len(data)):
            t.setStyle(TableStyle([('BACKGROUND', (0,i), (0,i), colors.HexColor('#E2E2E2'))]))
            t.setStyle(TableStyle([('BACKGROUND', (1,i), (-1,i), colors.HexColor(self.COLORS['grey_bg']))]))
        return t

if __name__ == "__main__":
    t = NIPTReportTemplate("test_nipt_v3.pdf")
    dummy_p = {'name': 'TEST PATIENT', 'sample_id': '202401', 'clinician': 'Dr. Smith', 'hospital': 'General Hosp', 'preg_status': 'Singleton', 'preg_type': 'Natural Pregnancy', 'specimen': 'Peripheral blood', 'dob': '01-01-1990 / 36 Years'}
    dummy_z = {f'chr{i}': 0.1 for i in range(1, 23)}
    dummy_z['fetal_fraction'] = 8.5
    t.generate(dummy_p, dummy_z)
    print("V3 Template Corrected.")
