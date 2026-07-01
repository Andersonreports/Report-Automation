

import io
import os
import re
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, PageBreak, PageBreakIfNotEmpty, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

import hla_assets


class _BorderedTable(Table):
    """A Table that strokes its own outer border on every page fragment.

    ReportLab's ``BOX``/``OUTLINE`` style only closes the bottom edge on the
    *final* fragment of a split table, so a long table that spills onto the next
    page leaves the page-ending fragment open at the bottom. Drawing the border
    rectangle ourselves in ``draw`` (which runs once per fragment) guarantees a
    fully closed border on each page â without adding any inner row lines.
    """

    _border_width = 0.5
    _border_color = colors.HexColor("#A0A0A0")

    def draw(self):
        Table.draw(self)
        c = self.canv
        c.saveState()
        c.setStrokeColor(self._border_color)
        c.setLineWidth(self._border_width)
        c.rect(0, 0, self._width, self._height, stroke=1, fill=0)
        c.restoreState()

PAGE_W, PAGE_H = letter        
MARGIN_L = 15 * mm           
MARGIN_R = 15 * mm
MARGIN_T = 2  * mm
MARGIN_B = 3  * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R   
QR_ZONE   = 30 * mm  
C_NGS_TITLE     = colors.HexColor("#002060")   
C_INFO_BG       = colors.HexColor("#E2E2E2")  
C_HLA_HDR       = colors.HexColor("#FABF8F")   
C_HLA_ROW       = colors.HexColor("#F2F2F2")   
C_APPROVAL      = colors.HexColor("#2C6BAA")   
C_RPL_TITLE     = colors.HexColor("#001F5F")   
C_RPL_BORDER    = colors.black   
              # RPL table borders
C_TITLE         = C_NGS_TITLE
C_SECTION_BAR   = C_NGS_TITLE

WHITE = colors.white
BLACK = colors.black
ORANGE = colors.HexColor("#E8772E")

C_CDC_SECTION  = colors.HexColor("#C0392B")   
C_CDC_NEG      = colors.HexColor("#27AE60")   
C_CDC_POS      = colors.HexColor("#E74C3C")  
C_CDC_DOUBTFUL = colors.HexColor("#E67E22")   
C_CDC_REL_BG   = colors.HexColor("#FABF8F")   
C_CDC_DTT_HDR  = colors.HexColor("#2C3E50")   

C_SAB_HEADING  = colors.HexColor("#C55A11")   
C_SAB_TBL_HDR  = colors.HexColor("#9DC3E6")   

COVERAGE_LINES = [
    ": Class I (HLA-A, -B & -C) - Whole gene",
    ": Class II (HLA-DRB1) - Whole gene except Intron 1",
    ": Class II (HLA-DQB1) - Upto Exon 5",
    ": Class II (HLA-DPB1) - Exon 2 to Exon 4",
]

EXTRA_COVERAGE_LINES_11LOCI = [
    ": Class II (HLA-DRB3/4/5) - Whole gene except Intron 1",
    ": Class II (HLA-DQA1) - Whole gene",
    ": Class II (HLA-DPA1) - Upto Exon 4",
]
METHODOLOGY_MINISEQ = "Typing by NGS illumina MiniSeq using MIA FORA NGS Kits from IMMUCOR"
METHODOLOGY_SURFSEQ  = "Typing by NGS Surfseq using GENDx Kit"

RPL_BACKGROUND = (
    "The HLA region maps to chromosome 6p21.31 and spans approximately 7.6 Mb. "
    "The classical HLA genes are divided into Class I (HLA-A, B, C) and Class II "
    "(HLA-DR, DQ, DP) gene families. The gene products (HLA molecules) are expressed "
    "on cell surfaces and play a key role in immune recognition. Sharing of HLA "
    "antigens between couples has been associated with recurrent pregnancy loss (RPL) "
    "and recurrent implantation failure (RIF). Increased HLA compatibility between "
    "partners may impair the development of protective immune responses required for "
    "successful pregnancy. The clinical relevance of individual HLA allele sharing "
    "should be interpreted in the context of the patient's complete clinical history."
)
RPL_DISCLAIMERS = [
    "This test is intended for use in conjunction with clinical evaluation and other "
    "diagnostic procedures. Results should be interpreted by a qualified clinician.",
    "HLA allele frequencies and their association with reproductive outcomes vary "
    "across populations. Reference data used are based on published literature.",
    "The HLA-C supertype (C1/C2) classification is based on published Killer-cell "
    "Immunoglobulin-like Receptor (KIR) ligand groupings.",
    "This report covers Class I (HLA-A, B, C) whole gene and Class II partial gene at "
    "high-resolution allele level.",
    "DPB1 alleles are reported separately; their inclusion in compatibility scoring "
    "is at the discretion of the treating clinician.",
    "Results are reported based on the IMGT/HLA database release version stated above. "
    "Novel alleles may not be detected.",
    "This report is generated for clinical use only and should not be used for "
    "forensic or immigration purposes.",
    "Anderson Diagnostics and Labs shall not be held liable for clinical decisions "
    "made solely on the basis of this report without clinical correlation.",
]

SINGLE_RPL_BACKGROUND = (
    "The HLA region comprises several genetic loci located on chromosome 6 and it "
    "contains the most polymorphic genes known in humans. Genes in most HLA loci are "
    "involved in interactions in the immune system through various mechanisms. So called "
    "classical HLA class I genes (HLA-A, -B and C) play important roles in "
    "transplantation immunology. In addition, class I HLA molecules seem to play a role "
    "in immune interactions of importance to pregnancy. Fetal HLA-C can interact with "
    "maternal natural killer (NK) cell receptors that may influence the risk of pregnancy "
    "loss. HLA antigen (HLA)âDRB1 and -DQB1 polymorphisms are associated with most "
    "autoimmune disorders and studies of HLA-DRB1 polymorphism in RPL patients are thus "
    "relevant. In previous studies, the HLA-DRB1*03 allele was found with increased "
    "prevalence in RPL patients."
)
SINGLE_RPL_DISCLAIMERS = [
    "This immunology report is conducted based on the recommendation of the Doctor and "
    "has to be viewed along with clinical data for interpretation.",
    "Baseline normal range values for each ligand, cytokine, cell evaluated is from "
    "patients with similar age-profile and successful live birth.",
    "Recommendation to clinician for suitability is purely at the discretion of the "
    "clinician NOT to be construed as a recommendation for treatment.",
    "Test results released pertain to the specimen submitted and all test results are "
    "dependent on the quality of sample received by the laboratory.",
    "Test results should be interpreted in the context of clinical findings, family "
    "history, and other laboratory data. Misinterpretation of results may occur if the "
    "information provided is inaccurate or incomplete. Test results may show "
    "interlaboratory variations.",
    "Laboratory investigations are only a tool to facilitate arriving at a diagnosis "
    "and should be clinically correlated by the referring physician.",
    "This is not a diagnostic report and therefore should be used for Investigational "
    "Use Only (IUO) or for Clinical research Use Only (RUO) and should be interpreted "
    "or used exclusively by or under the guidance of a Professional Practitioners- "
    "including but not limited to, certified physicians, clinicians, dietitians, "
    "nutritionists, sports therapists and such other persons in similar profession "
    "having appropriate validation to undertake such practice.",
]

# âââ Single Locus (Luminex reverse SSO) text constants ââââââââââââââââââââââ
SINGLE_LOCUS_METHODOLOGY = (
    "HLA Typing by Luminex technology applies reverse SSO DNA typing method. Target DNA is PCR-amplified using a "
    "group-specific primer and the PCR product is biotinylated, which allows it to be detected using R-"
    "Phycoerythrin conjugated Streptavidin (SAPE).",
    "The PCR product is denatured and allowed to rehybridize complementary DNA probes conjugated to "
    "fluorescently coded microspheres. A flow analyzer identifies the fluorescent intensity of PE "
    "(phycoerythrin) on each microsphere. The assignment of the HLA typing is based on the reaction pattern "
    "compared to patterns associated with published HLA gene sequences.",
    "The number of nucleotide mismatches with each allele is determined, as well as the number of "
    "mismatches with the determined phasing data. Mismatches at exons are treated separately. A list of "
    "alleles is selected with a limited number of mismatches.",
)
SINGLE_LOCUS_DISCLAIMER = (
    "The occurrence of HLA typing results and the number of different allele combinations by a SSO "
    "method for an individual may change according to the version of the IMGT/HLA database."
)
SINGLE_LOCUS_REFERENCES = [
    "1. Terasaki, PI, Bernoco, F, Park MS, Ozturk G, Iwaki Y. Microdroplet testing for HLA-A, -B, -C, "
    "and âD antigens. American Journal of Clinical Pathology 69:103-120, 1978.",
    "2. Slater RD, Parham P. Mutually exclusive public epitomes of HLA-A, B, C Molecules. Human "
    "Immunology 26: 85-89, 1989.",
    "3. The LuminexÂ® 100 Userâs Manual, Luminex Corporation, PN 89-00002-00-005 Rev. B.",
    "4. LuminexÂ® FLEXMAP 3DÂ® Hardware User Manual, Luminex Corporation PN 89-00002-00-187.",
    "5. Ng J, Hurley CK, Baxter-Lowe LA, et al. Large-scale oligonucleotide typing for HLA-DRB1/3/4 and "
    "HLA-DQB1 is highly accurate, specific, and reliable. Tissue Antigens. 1993; 42: 473-479.",
    "6. Bodmer JG, Marsh SGE, Albert E, Bodmer WF, Bontrop RE, Dupont B, Erlich HA, Hansen JA, Mach B, "
    "Mayr WR, Parham P, Petersdorf EW, Sasasuki T, Schreuder GMT, Strominger JL, Svejgaard A, Terasaki "
    "PI. Nomenclature for factors of the HLA system, 1998. Tissue Antigens, 53, 407-446, 1999. Human "
    "Immunology, 60, 361-395, 1999. European Journal of Immunogenetics, 26, 81-116, 1999.",
    "7. Colinas RJ, Bellisario R et al. Multiplexed genotyping of beta-globin variants from PCR-amplified "
    "newborn blood spot DNA by hybridization with allele-specific oligo deoxynucleotides coupled to an "
    "array of fluorescent microspheres. Clinical Chemistry 46: 996-998, 2000.",
]

# âââ HLA-C (fixed-locus, two-page) report constants âââââââââââââââââââââââââââ
HLA_C_METHODOLOGY = (
    "HLA Typing by Luminex technology applies SSO DNA typing method. Target DNA is PCR-amplified using a "
    "group-specific primer and the PCR product is biotinylated, which allows it to be detected using R-"
    "Phycoerythrin conjugated Streptavidin (SAPE).",
    "The PCR product is denatured and allowed to rehybridize complementary DNA probes conjugated to "
    "fluorescently coded microspheres. A flow analyzer identifies the fluorescent intensity of PE "
    "(phycoerythrin) on each microsphere. The assignment of the HLA typing is based on the reaction pattern "
    "compared to patterns associated with published HLA gene sequences.",
    "The number of nucleotide mismatches with each allele is determined, as well as the number of "
    "mismatches with the determined phasing data. Mismatches at exons are treated separately. A list of "
    "alleles is selected with a limited number of mismatches.",
)
HLA_C_DISCLAIMER = SINGLE_LOCUS_DISCLAIMER
HLA_C_REFERENCES = SINGLE_LOCUS_REFERENCES

# âââ Font registration ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "assets", "hla", "fonts")
_REGISTERED: set[str] = set()

def _register_fonts():
    """Register custom TTF fonts once (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    font_configs = [
        ("SegoeUI",               "SEGOEUI.TTF"),
        ("SegoeUI-Bold",          "SEGOEUIB.TTF"),
        ("SegoeUI-Italic",        "SEGOEUII.TTF"),
        ("SegoeUI-BoldItalic",    "SEGOEUIZ.TTF"),
        ("GillSansMT",            "GIL_____.TTF"),
        ("GillSansMT-Bold",       "GILB____.TTF"),
        ("Calibri",               "CALIBRI.TTF"),
        ("Calibri-Bold",          "CALIBRIB.TTF"),
        ("Calibri-Italic",        "CALIBRII.TTF"),
        ("Calibri-BoldItalic",    "CALIBRIZ.TTF"),
    ]
    for name, fname in font_configs:
        path = os.path.join(_FONTS_DIR, fname)
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                _REGISTERED.add(name)
            except Exception:
                pass
    if {"SegoeUI", "SegoeUI-Bold"} <= _REGISTERED:
        try:
            registerFontFamily("SegoeUI", normal="SegoeUI", bold="SegoeUI-Bold",
                               italic="SegoeUI-Italic", boldItalic="SegoeUI-BoldItalic")
        except Exception:
            pass
    if {"GillSansMT", "GillSansMT-Bold"} <= _REGISTERED:
        try:
            registerFontFamily("GillSansMT", normal="GillSansMT", bold="GillSansMT-Bold",
                               italic="GillSansMT-Italic")
        except Exception:
            pass
    if {"Calibri", "Calibri-Bold"} <= _REGISTERED:
        try:
            registerFontFamily("Calibri", normal="Calibri", bold="Calibri-Bold",
                               italic="Calibri-Italic", boldItalic="Calibri-BoldItalic")
        except Exception:
            pass


def _f(preferred: str, fallback: str = "Helvetica") -> str:
    """Return preferred font name if registered, else fallback."""
    try:
        pdfmetrics.getFont(preferred)
        return preferred
    except Exception:
        return fallback


# âââ Style factory ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def _styles() -> dict:
    """Return a dict of ParagraphStyle objects, chosen to match reference PDFs."""
    _register_fonts()

    # Font aliases (resolved at call time so fallbacks work)
    F_GILL_BOLD  = _f("GillSansMT-Bold",  "Helvetica-Bold")
    F_SEGOE      = _f("SegoeUI",           "Helvetica")
    F_SEGOE_BOLD = _f("SegoeUI-Bold",      "Helvetica-Bold")
    F_CALI       = _f("Calibri",           "Helvetica")
    F_CALI_BOLD  = _f("Calibri-Bold",      "Helvetica-Bold")

    return {
        # ââ NGS title ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
        "title_ngs": ParagraphStyle(
            "title_ngs", fontName=F_GILL_BOLD, fontSize=18,
            textColor=C_TITLE, alignment=TA_CENTER,
            spaceBefore=0, spaceAfter=4, leading=22
        ),
        # ââ RPL title (SegoeUI-Bold 14pt #001F5F â confirmed by fitz audit) ââââ
        "title_rpl": ParagraphStyle(
            "title_rpl", fontName=F_SEGOE_BOLD, fontSize=14,
            textColor=C_RPL_TITLE, alignment=TA_CENTER,
            spaceBefore=0, spaceAfter=4, leading=18
        ),
        # ââ NGS section bar text (white on blue) ââââââââââââââââââââââââââââââ
        "section_bar": ParagraphStyle(
            "section_bar", fontName=F_SEGOE_BOLD, fontSize=9.5,
            textColor=WHITE, leading=12
        ),
        # ââ Patient info table ââââââââââââââââââââââââââââââââââââââââââââââââ
        "lbl": ParagraphStyle(
            "lbl", fontName=F_SEGOE_BOLD, fontSize=10,
            textColor=BLACK, leading=12
        ),
        "lbl_center": ParagraphStyle(
            "lbl_center", fontName=F_SEGOE_BOLD, fontSize=10,
            textColor=BLACK, alignment=TA_CENTER, leading=12
        ),
        "val": ParagraphStyle(
            "val", fontName=F_SEGOE_BOLD, fontSize=10,
            textColor=BLACK, leading=12
        ),
        # ââ HLA table (font sizes reduced 1pt to prevent header overflow) ââââ
        "hla_hdr": ParagraphStyle(
            "hla_hdr", fontName=F_CALI_BOLD, fontSize=11,
            textColor=BLACK, alignment=TA_CENTER, leading=13
        ),
        "hla_val": ParagraphStyle(
            "hla_val", fontName=F_CALI, fontSize=10,
            textColor=BLACK, alignment=TA_CENTER, leading=12
        ),
        "hla_lbl": ParagraphStyle(
            "hla_lbl", fontName=F_CALI_BOLD, fontSize=10,
            textColor=BLACK, alignment=TA_CENTER, leading=12
        ),
        # ââ Body text ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
        "body": ParagraphStyle(
            "body", fontName=F_CALI, fontSize=11,
            textColor=BLACK, leading=13, spaceAfter=2
        ),
        "body_bold": ParagraphStyle(
            "body_bold", fontName=F_CALI_BOLD, fontSize=11,
            textColor=BLACK, leading=13, spaceAfter=2
        ),
        "body_small": ParagraphStyle(
            "body_small", fontName=F_CALI, fontSize=10,
            textColor=BLACK, leading=12
        ),
        "coverage": ParagraphStyle(
            "coverage", fontName=F_CALI, fontSize=11,
            textColor=BLACK, leading=13, leftIndent=10, spaceAfter=1
        ),
        # ââ RPL couple table âââââââââââââââââââââââââââââââââââââââââââââââââ
        "rpl_lbl": ParagraphStyle(
            "rpl_lbl", fontName=F_CALI_BOLD, fontSize=11,
            textColor=BLACK, leading=13
        ),
        "rpl_lbl_center": ParagraphStyle(
            "rpl_lbl_center", fontName=F_CALI_BOLD, fontSize=11,
            textColor=BLACK, alignment=TA_CENTER, leading=13
        ),
        "rpl_val": ParagraphStyle(
            "rpl_val", fontName=F_CALI, fontSize=11,
            textColor=BLACK, alignment=TA_CENTER, leading=13
        ),
        "rpl_hla_lbl": ParagraphStyle(
            "rpl_hla_lbl", fontName=F_CALI_BOLD, fontSize=11,
            textColor=BLACK, leading=13
        ),
        "rpl_hla_val": ParagraphStyle(
            "rpl_hla_val", fontName=F_CALI_BOLD, fontSize=11,
            textColor=BLACK, alignment=TA_CENTER, leading=13
        ),
        "rpl_hdr_name": ParagraphStyle(
            "rpl_hdr_name", fontName=F_CALI_BOLD, fontSize=11,
            textColor=WHITE, alignment=TA_CENTER, leading=13
        ),
        # ââ Match / Comment ââââââââââââââââââââââââââââââââââââââââââââââââââââ
        "match": ParagraphStyle(
            "match", fontName=F_CALI_BOLD, fontSize=11,
            textColor=BLACK, alignment=TA_LEFT, leading=13, spaceAfter=3
        ),
        "comment": ParagraphStyle(
            "comment", fontName=F_CALI, fontSize=11,
            textColor=BLACK, leading=13, spaceAfter=3
        ),
        # ââ Reference heading âââââââââââââââââââââââââââââââââââââââââââââââââ
        "ref_hdr": ParagraphStyle(
            "ref_hdr", fontName=F_CALI_BOLD, fontSize=14,
            textColor=C_NGS_TITLE, leading=18, spaceBefore=4, spaceAfter=2
        ),
        # ââ RPL section headings (BACKGROUND, DISCLAIMERS) ââââââââââââââââââââ
        "section_hdr": ParagraphStyle(
            "section_hdr", fontName=F_SEGOE_BOLD, fontSize=12,
            textColor=C_NGS_TITLE, leading=15, spaceBefore=6, spaceAfter=2
        ),
        # ââ RPL body/disclaimers ââââââââââââââââââââââââââââââââââââââââââââââ
        "justify": ParagraphStyle(
            "justify", fontName=F_CALI, fontSize=11,
            textColor=BLACK, leading=15, alignment=TA_JUSTIFY, spaceAfter=4
        ),
        "disc_item": ParagraphStyle(
            "disc_item", fontName=F_CALI, fontSize=11,
            textColor=BLACK, leading=15, alignment=TA_JUSTIFY, leftIndent=12, spaceAfter=3
        ),
        # ââ Signature block âââââââââââââââââââââââââââââââââââââââââââââââââââ
        # Cambria-Bold 12.2pt in reference PDF; SegoeUI-Bold is closest available
        "sign_approval": ParagraphStyle(
            "sign_approval", fontName=F_SEGOE_BOLD, fontSize=12.2,
            textColor=C_APPROVAL, leading=15, spaceBefore=2, spaceAfter=2
        ),
        "sign_name": ParagraphStyle(
            "sign_name", fontName=F_CALI_BOLD, fontSize=10,
            textColor=BLACK, alignment=TA_CENTER, leading=12
        ),
        "sign_role": ParagraphStyle(
            "sign_role", fontName=F_CALI_BOLD, fontSize=10,
            textColor=BLACK, alignment=TA_CENTER, leading=12
        ),
    }


# âââ Image helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def _img_b64(b64: str, width: float, height: Optional[float] = None) -> Image:
    data = hla_assets.get_image_bytes(b64)
    return Image(io.BytesIO(data), width=width, height=height)


def _strip_prefix(allele: str) -> str:
    """'A*02:11:01' â '02:11:01'; returns 'â' if falsy."""
    if not allele:
        return "â"
    m = re.match(r"[A-Za-z0-9]+\*(.+)", allele)
    return m.group(1) if m else allele


def _merged_drb345(hla: dict) -> list:
    """Return [a1, a2] for whichever of DRB3/DRB4/DRB5 has data.

    Only one of the three is biologically present per genotype (it depends on
    the DRB1 allele group), so the report shows them as a single "DRB3/4/5"
    column rather than three mostly-empty columns. The allele value keeps its
    locus prefix (e.g. "DRB5*01:01:01") since the shared column header alone
    can't say which of the three it is.
    """
    for k in ("DRB3", "DRB4", "DRB5"):
        v = hla.get(k)
        if v and any(str(x).strip() for x in v if x is not None):
            return v
    return [None, None]


def _split_drb345(hla: dict) -> dict:
    """Route DRB3/4/5 alleles to correct sub-key for separate column display.

    The manual form stores all three under the 'DRB3' slot with an explicit
    prefix (e.g. 'DRB5*01:01:01'). Bulk imports store under the correct key
    already. Parse the allele prefix so the value always lands in the right
    column ('DRB3', 'DRB4', or 'DRB5') regardless of where it was stored.
    """
    out: dict = {}
    for k in ("DRB3", "DRB4", "DRB5"):
        v = hla.get(k)
        if not v or not any(x for x in v if x and str(x).strip()):
            continue
        a1 = next((x for x in v if x and str(x).strip()), "")
        m = re.match(r"(DRB[345])\*", str(a1).strip(), re.IGNORECASE)
        dest = m.group(1).upper() if m else k
        out[dest] = v
    return out


def _clean_display(val) -> str:
    """Render layer: replace empty / N/A / any value containing 'Insufficient Data' with em-dash.
    'Insufficient Data' is a substring match (mirrors /insufficient data/i.test(val)).
    N/A is a whole-string match only."""
    s = str(val).strip() if val else ""
    if not s:
        return "\u2014"
    # Round 4 safety net: collapse ALL whitespace before testing so "I n s u f f i c i e n t   d a t a" is caught
    if re.sub(r"\s+", "", s).lower() == "insufficientdata":
        return "\u2014"
    if re.search(r"insufficient\s*data", s, re.I):   # catches standard spacing variants
        return "\u2014"
    # NOTE: "NA" / "N/A" values are kept as-is; only empty cells and Insufficient Data become â
    return s


def _normalize_hla_alleles(text: str) -> str:
    """Normalize HLA allele nomenclature in remarks/comments.
    Handles: hladpb1 â HLA-DPB1, Hla-dpb1 â HLA-DPB1, hla-dpb1 â HLA-DPB1, etc.
    Covers: A, B, C, DRA, DRB1-9, DQA1, DQB1, DPA1, DPB1"""
    if not text:
        return text
    
    # Common HLA gene names (case-insensitive patterns)
    hla_genes = r"(?:DRA|DRB\d|DQA1|DQB1|DPA1|DPB1|A|B|C)(?:\*[0-9:]+)?"
    
    # Replace patterns like "hla-dpb1", "hladpb1", "Hla-dpb1" with proper format
    # First, match: [optional spaces] HLA [optional hyphen] [gene name with optional allele]
    def capitalize_hla(match):
        full_match = match.group(0)
        # Extract the HLA gene part (e.g., "dpb1" or "dpb1*04:01:01")
        # Pattern: hla[- ]?gene_name[*allele]?
        m = re.search(r"hla\s*-?\s*(" + hla_genes + r")", full_match, re.IGNORECASE)
        if m:
            gene_and_allele = m.group(1).upper()
            # Ensure hyphen between HLA and gene name
            return f"HLA-{gene_and_allele}"
        return full_match
    
    # Match: "hla" (with optional space/hyphen) followed by gene name and optional allele
    result = re.sub(
        r"\bhla\s*-?\s*(" + hla_genes + r")",
        lambda m: f"HLA-{m.group(1).upper()}",
        text,
        flags=re.IGNORECASE
    )
    
    return result


def _format_relationship(rel: str, other_name: str) -> str:
    """Return 'Rel of Other Name'. Skips when rel is empty/NA or already contains 'of'."""
    r = (rel or "").strip()
    if not r or r.upper() in ("NA", "N/A") or r == "\u2014":
        return r
    if " of " in r.lower():
        return r  # already formatted
    name = (other_name or "").strip()
    if not name:
        return r
    return f"{r} of {name}"


def _normalize_age(gender_age: str) -> str:
    """Reformat the age portion of a combined 'Gender / Age' string.
    Rule: if years present â keep years only, drop months and days.
          if months only   â keep months only, drop days.
    Examples: '14 Years 24 D / Male'       â '14 Years / Male'
              '2 Years 3 Months / Female'  â '2 Years / Female'
              '3 Months 5 Days / Male'     â '3 Months / Male'
              '33Y/Female'                 â '33 Years/Female'
    """
    if not gender_age:
        return gender_age
    _DAY = r'(?:\s*\d+\s*[Dd](?:ays?)?)?'
    # Group 1=years, Group 2=months-with-years, Group 3=standalone-months, Group 4=plain-number
    _PAT = (r'(\d+)\s*[Yy](?:ears?)?(?:\s*(\d+)\s*[Mm](?:onths?)?)?' + _DAY +
            r'|(\d+)\s*[Mm](?:onths?)?' + _DAY +
            r'|(?<![/\w])(\d+)(?![/\w])')   # plain integer not adjacent to / or word chars
    def _yr(n):  return f"{n} {'Year' if n == 1 else 'Years'}"
    def _mo(n):  return f"{n} {'Month' if n == 1 else 'Months'}"
    def _repl(m):
        y, mo_with_y, mo_only, plain = m.group(1), m.group(2), m.group(3), m.group(4)
        if y:
            base  = int(y)
            extra = int(mo_with_y) if mo_with_y else 0
            years = base + extra // 12
            if years > 0:
                return _yr(years)
            # 0 years â fall back to remaining months
            return _mo(extra) if extra else _yr(0)
        if mo_only:
            months = int(mo_only)
            return _yr(months // 12) if months >= 12 else _mo(months)
        return _yr(int(plain))
    return re.sub(_PAT, _repl, gender_age)


def _fit_one_line(text: str, avail_pts: float, base_style: ParagraphStyle,
                  min_size: float = 6.5) -> Paragraph:
    """Render *text* at full font, wrapping onto extra lines when it is too wide.

    Used for free-text demography values such as a lengthy Hospital/Clinic name.
    The value keeps its normal font size and is allowed to wrap to a second line
    rather than being shrunk to fit on one line; the demography row simply grows
    taller to accommodate the extra line (the rows top-align, so the label stays
    anchored to the first wrapped line).

    (*avail_pts* and *min_size* are retained for call-site compatibility; the
    Paragraph wraps to its cell width on its own, so they are no longer used.)
    """
    return Paragraph(text or "", base_style)


def _demography_col_widths(patient: dict, donor: dict, nabl: bool = False) -> list:
    """Compute the 7 column widths for the patient/donor demography table.

    Layout: [lbl_L, colon_L, val_L, GAP, lbl_R, colon_R, val_R].  The patient
    value column (val_L â Hospital/Clinic, names) and the donor value column
    (val_R) share a fixed horizontal budget.  Donor values are usually short
    (dates, 'NA', 'Male / 41 Years'), leaving the donor column half-empty, so
    val_R is sized to just fit its widest entry and *all* the leftover space is
    handed to val_L â letting a long Hospital/Clinic name render at full font
    instead of being shrunk.  When a donor value (e.g. a long donor name) is
    itself wide, the split shifts back the other way automatically.
    """
    cw = CONTENT_W
    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    # Label / colon / gap columns stay fixed (sized for their longest labels:
    # "Sample Number" left, "Sample receipt date" right).
    f0, f1, f3, f4, f5 = 0.176, 0.016, 0.012, 0.196, 0.016
    gap_w = _NABL_GAP_LOGO_W if nabl else (f3 * cw)
    fixed = (f0 + f1 + f4 + f5) * cw + gap_w
    pool = cw - fixed                      # shared by val_L (col2) + val_R (col6)

    def _w(s):
        return pdfmetrics.stringWidth(s or "", F_BOLD, 10)

    # Measure the full donor display name including any trailing phone number in
    # parentheses â IV_name only inserts a line-break when the text exceeds the
    # column, so sizing the column for the full string keeps the name on one line.
    _donor_name_display = _title_case(_clean_display(donor.get("name", "")), is_name=True)
    donor_name_w = _w(_donor_name_display)
    donor_vals = [
        donor_name_w,
        _w(_normalize_age(donor.get("gender_age", ""))),
        _w(_clean_display(donor.get("pin", "")) or "NA"),
        _w(_clean_display(donor.get("sample_number", "")) or "NA"),
        _w(_clean_display(donor.get("receipt_date", ""))),
        _w(_clean_display(donor.get("report_date", ""))),
    ]
    need6 = max(donor_vals) + 8             # widest donor value + cell padding
    col6 = max(58.0, min(need6, 280.0))     # wide enough for long donor names
    col2 = pool - col6
    MIN2 = 120.0                            # never starve the patient value column
    if col2 < MIN2:
        col2, col6 = MIN2, pool - MIN2
    return [f0 * cw, f1 * cw, col2, gap_w, f4 * cw, f5 * cw, col6]


def _append_match_pct(match_str: str) -> str:
    """Append (X%) to 'N of M' match strings when no % is already present."""
    if not match_str or "%" in match_str:
        return match_str
    m = re.search(r'(\d+)\s+of\s+(\d+)', match_str, re.I)
    if m:
        x, y = int(m.group(1)), int(m.group(2))
        pct = round(x / y * 100) if y else 0
        return f"{match_str} ({pct}%)"
    return match_str


def _underline_match_score(match_str: str) -> str:
    """Underline the score numerator in an 'N of M' match string for PDF markup."""
    if not match_str:
        return match_str
    return re.sub(r'(\d+\s+of\s+\d+)', r'<u>\1</u>', match_str, count=1)


def _capitalize_initials(name: str) -> str:
    """Capitalize standalone single-letter initials within a name string.

    Handles patterns like:
      'Mrs Abirami s'   â 'Mrs Abirami S'
      'Mr Koushik a.m'  â 'Mr Koushik A.M'
    Single lowercase letters that are surrounded by word boundaries
    (spaces, dots, start/end) are uppercased.
    """
    return re.sub(r'\b([a-z])\b', lambda m: m.group(0).upper(), name)


_DEGREE_MAP = {
    "mbbs": "MBBS", "md": "MD", "ms": "MS", "dm": "DM",
    "dnb": "DNB", "phd": "PhD", "dgo": "DGO", "frcs": "FRCS", "mrcp": "MRCP",
}
# Fix 2: expanded to include medical/lab abbreviations that must always be uppercased.
# Also includes common hospital/organization acronyms (e.g. ESIC, AIIMS) â these
# contain vowels so the no-vowel abbreviation rule (6b) would otherwise miss them,
# and Hospital/Clinic name fields re-case ALL-CAPS input (is_name=True) so they'd
# fall through to default title-casing without this explicit whitelist entry.
_ABBREV_SET = {"edta", "dna", "rna", "pcr", "bmt", "hla", "rpl", "rif", "nips", "poc", "ngs", "wbc", "rbc", "idd",
               "esic", "aiims", "kims"}
_PREFIX_MAP_TC = {"mr": "Mr", "mrs": "Mrs", "ms": "Ms", "master": "Master", "dr": "Dr"}


def _title_case(text: str, is_name: bool = False) -> str:
    """Render-layer smart title case for names, degrees, and specimen types.

    When `is_name` is True (patient/donor names, hospital/clinic names), an
    ALL-CAPS word is NOT preserved as-is â it falls through to the other rules,
    so a name typed in full caps (e.g. "JEEVA JAGAN") renders as "Jeeva Jagan",
    while genuine acronyms (no vowels, e.g. "KMCH") still render upper-case via
    rule 6b and known abbreviations (e.g. "HLA") still render upper-case via
    rule 6a / the degree map.

    Rules (applied per token, where tokens split on whitespace and commas):
    - Already ALL-CAPS words of length > 1 are preserved as-is (e.g. HLA, NGS),
      unless `is_name` is True.
    - Known degrees (mbbs, md, ms, dm, dnb, phd, dgo, frcs, mrcp) â fixed uppercase/mixed form.
    - Known abbreviations (edta, bmt, hla, rpl, rif, etc.) â always uppercase.
    - Short forms enclosed in parentheses â always uppercase (e.g. (hbii) â (HBII)).
    - Period-concatenated tokens like Dr.S.k.gupta â split at dots, process each segment:
        Â· first segment checked as prefix (Dr â Dr)
        Â· middle single-letter segments â uppercase initial
        Â· last multi-letter segment â title-cased name
    - Known prefixes at word boundaries (Mr/Mrs/Ms/Master/Dr) â canonical casing.
    - All other words â first letter upper, rest lower.
    """
    if not text or text == "\u2014":
        return text

    def _process_token(token: str) -> str:
        if not token:
            return token

        # Fix 2: strip any trailing parenthesised short-form so the base word is
        # processed correctly, then reattach the short-form fully uppercased.
        # e.g. "International(hbii)" â base="International", paren="(HBII)"
        paren_m = re.search(r'\(([^)]+)\)$', token)
        if paren_m:
            base  = token[:paren_m.start()]
            paren = '(' + paren_m.group(1).upper() + ')'
        else:
            base  = token
            paren = ''

        # If the whole token is just a parenthesised form (no base), return uppercased.
        if not base:
            return paren

        result = _process_base(base)
        return result + paren

    def _process_base(token: str) -> str:
        """Apply capitalization rules to a bare token (no parenthesised suffix).

        Rules (in priority order):
        1. Already all-uppercase (length > 1) â preserve (e.g. HLA, EDTA typed in caps).
        2. Known degrees â fixed mixed-case form (e.g. PhD, MBBS).
        3. Period-concatenated initials/tokens â split and process each segment.
        4. Single-letter alpha â uppercase (standalone initial like "r" in "Ramya r").
        5. Known name prefix (Dr, Mr, Mrs, Ms, Master) â canonical casing.
        6. Short word (â¤4 chars, alpha-only, no vowels) â uppercase abbreviation.
        7. Short word (â¤4 chars, alpha-only) â uppercase (catches BMT, CKD, HD, IDD, etc.).
        8. Default â title-case.
        """
        # Rule 1: Preserve all-uppercase words of length > 1 (already in caps),
        # unless this is a name/place field (is_name=True), where ALL-CAPS input
        # should be re-cased like any other word. Alphanumeric tokens (e.g. gene/
        # diagnosis abbreviations like PIK3CD, TP53, BRCA1) are included â only
        # the letters need to already be uppercase; digits are case-invariant.
        if (not is_name and len(token) > 1 and token == token.upper()
                and any(c.isalpha() for c in token) and token.isalnum()):
            if token.lower() in _DEGREE_MAP:
                return _DEGREE_MAP[token.lower()] + "."
            return token
        lower = token.lower()
        # Rule 2a: Known name prefix (checked before degree map to avoid "Ms"/"Ms." â "MS").
        # Accept an optional trailing dot so "Ms." is treated as the prefix, not the
        # "ms" (Master of Surgery) degree.
        _pfx = lower.rstrip(".")
        if _pfx in _PREFIX_MAP_TC and lower in (_pfx, _pfx + "."):
            return _PREFIX_MAP_TC[_pfx] + ("." if token.endswith(".") else "")
        # Rule 2b: Known degrees â fixed form with trailing dot
        if lower in _DEGREE_MAP:
            return _DEGREE_MAP[lower] + "."
        # Rule 3: Period-concatenated token (e.g. Dr.Priya, S.K.Gupta, MD.)
        if "." in token:
            # Fast-path: whole token without dots maps to a known degree (e.g. Ph.D â PhD)
            _no_dots = token.replace(".", "").lower()
            if _no_dots in _DEGREE_MAP:
                return _DEGREE_MAP[_no_dots] + "."
            has_trailing_dot = token.endswith(".")
            parts = [p for p in token.split(".") if p]
            if not parts:
                return token
            result_parts = []
            for i, part in enumerate(parts):
                p_lower = part.lower()
                if i == 0 and p_lower in _PREFIX_MAP_TC:
                    result_parts.append(_PREFIX_MAP_TC[p_lower])
                elif len(part) == 1:
                    result_parts.append(part.upper())
                elif p_lower in _DEGREE_MAP:
                    result_parts.append(_DEGREE_MAP[p_lower])
                elif p_lower in _ABBREV_SET:
                    result_parts.append(part.upper())
                elif part.isalpha() and not any(c in "aeiou" for c in p_lower):
                    result_parts.append(part.upper())
                else:
                    result_parts.append(part[0].upper() + part[1:].lower())
            # Prefix + name â "Prefix.Name" (no space)
            if result_parts[0] in _PREFIX_MAP_TC.values():
                rest = ".".join(result_parts[1:])
                return result_parts[0] + "." + rest if rest else result_parts[0]
            # Initials / degrees â join with ".", preserve trailing "."
            joined = ".".join(result_parts)
            return joined + "." if has_trailing_dot else joined
        # Rule 4: Single-letter initial (e.g. "r" in "Ramya r") â uppercase
        if len(token) == 1 and token.isalpha():
            return token.upper()
        # Rule 6a: Known lab/specimen abbreviation whitelist â always uppercase (checked before vowel rule)
        if lower in _ABBREV_SET:
            return token.upper()
        # Rule 6b: All-alpha, no vowels â uppercase abbreviation (CKD, HD, BMT, PVT, LTD, etc.)
        # Words containing vowels are never treated as abbreviations regardless of length.
        if token.isalpha() and not any(c in "aeiou" for c in lower):
            return token.upper()
        # Rule 8: Default â title-case
        return token[0].upper() + token[1:].lower()

    # Split preserving whitespace and comma delimiters
    parts = re.split(r"(\s+|,)", text)
    result = "".join(_process_token(p) if not re.match(r"^(\s+|,)$", p) else p for p in parts)
    # Normalise standalone prefix before a name: "Mr Arun" / "Dr. Priya" â "Mr. Arun" / "Dr. Priya"
    # (keep the conventional space after the prefix dot, e.g. "Mrs. Sasikala").
    result = re.sub(r'(?<!\w)(Mr|Mrs|Ms|Miss|Master|Dr|Prof)\.?\s+(?=[A-Za-z])', r'\1. ', result)
    result = re.sub(r'(?<!\w)(Mr|Mrs|Ms|Miss|Master|Dr|Prof)\.?\s+(?=\d)', r'\1. ', result)
    return result


# âââ NABL seal cropped from the NABL header banner (cached) ââââââââââââââââââ
_nabl_seal_bytes_cache: bytes | None = None

def _get_nabl_seal_bytes() -> bytes:
    """Return NABL seal bytes with white background replaced by the table cell grey (C_INFO_BG).
    Result is cached so pixel processing only runs once per process.
    """
    global _nabl_seal_bytes_cache
    if _nabl_seal_bytes_cache is not None:
        return _nabl_seal_bytes_cache
    import numpy as np
    from PIL import Image as PILImage
    raw = hla_assets.get_image_bytes(hla_assets.NABL_SEAL_DEMOG_B64)
    img = PILImage.open(io.BytesIO(raw)).convert("RGB")
    data = np.array(img, dtype=np.uint8)
    # Replace near-white pixels (all channels > 240) with the table cell background colour
    bg_rgb = [int(round(c * 255)) for c in (C_INFO_BG.red, C_INFO_BG.green, C_INFO_BG.blue)]
    mask = (data[:, :, 0] > 240) & (data[:, :, 1] > 240) & (data[:, :, 2] > 240)
    data[mask] = bg_rgb
    buf = io.BytesIO()
    PILImage.fromarray(data, "RGB").save(buf, format="JPEG", quality=95)
    _nabl_seal_bytes_cache = buf.getvalue()
    return _nabl_seal_bytes_cache


# Width reserved for the NABL seal when it sits in a demography-table gap column
# (logo width + a small natural gap either side) â shared by _ngs_info_table and
# the ngs_photo combined patient|donor table.
_NABL_GAP_LOGO_W = 21 * mm + 3 * mm


def _qr_reserve(report_type: str) -> float:
    """Height of the blank strip kept above the footer for the external QR overlay.

    HLA (NGS with Photo), Transplant Donor, and 11-Loci reports can carry long
    remarks between the patient and donor locus tables â the 11-Loci/Transplant
    Donor table is also wider (DRB3/4/5, DQA1, DPA1 columns), so its header
    wraps to two lines and uses more vertical space than the base 6-locus
    table. To keep both tables (and their remarks) on one page they are
    allowed to reclaim half of this strip; the page number and the
    content-frame bottom both move down with the reduced reservation so
    nothing overlaps.
    """
    return (QR_ZONE / 2 if report_type in ("ngs_photo", "transplant_donor", "loci11")
            else QR_ZONE)


# âââ Canvas: header + footer on every page ââââââââââââââââââââââââââââââââââââ
class _HFCanvas:
    """Draws header image (or text) and footer image on every page."""

    def __init__(self, case: dict, title: str, banner_h: float, footer_h: float, total_pages: int = 1,
                 repeat_info: bool = False, repeat_top_offset: float = 0):
        self.case              = case
        self.title             = title
        self.banner_h          = banner_h
        self.footer_h          = footer_h
        self.total_pages       = total_pages
        # When repeat_info is True the patient demography table is redrawn on
        # every page (SAB reports); repeat_top_offset is the distance from the
        # page top to the table's top edge.
        self.repeat_info       = repeat_info
        self.repeat_top_offset = repeat_top_offset

    def __call__(self, canvas, doc):
        canvas.saveState()
        nabl      = self.case.get("nabl", True)
        with_logo = self.case.get("with_logo", True)

        # ââ Header ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
        if with_logo:
            _rtype = self.case.get("report_type", "")
            _nabl_in_header = nabl and _rtype in (
                "cdc_crossmatch", "dsa_crossmatch", "flow_crossmatch",
                "sab_class1", "sab_class2")
            _hdr_raw = hla_assets.get_image_bytes(
                hla_assets.HEADER_NABL_CDC_B64 if _nabl_in_header else hla_assets.HEADER_NONNABL_B64)
            canvas.drawImage(
                ImageReader(io.BytesIO(_hdr_raw)),
                0, PAGE_H - self.banner_h,
                width=PAGE_W, height=self.banner_h,
                preserveAspectRatio=False, mask="auto"
            )
        # Without logo: header space reserved but nothing is drawn.

        # ââ Footer ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
        if with_logo:
            raw_f = hla_assets.get_image_bytes(hla_assets.FOOTER_BAR_B64)
            # Footer bar at MARGIN_B from page bottom (matches external overlay calibration)
            canvas.drawImage(
                ImageReader(io.BytesIO(raw_f)),
                0, MARGIN_B,
                width=PAGE_W, height=self.footer_h,
                preserveAspectRatio=False, mask="auto"
            )
        # Page number near the top of the reserved bottom area (above external
        # overlay content); nudged ~5mm lower for tidier bottom alignment.
        _page_num_y = MARGIN_B + self.footer_h + _qr_reserve(
            self.case.get("report_type", "")) - 3 * mm
        canvas.setFont(_f("Calibri", "Helvetica"), 9)
        canvas.setFillColor(BLACK)
        canvas.drawRightString(
            PAGE_W - MARGIN_R,
            _page_num_y,
            f"Page {doc.page} of {self.total_pages}"
        )

        # ââ Repeating patient demography table (SAB) âââââââââââââââââââââââââ
        if self.repeat_info:
            info_t = _sab_info_table(self.case)
            _w, _h = info_t.wrapOn(canvas, CONTENT_W, PAGE_H)
            info_t.drawOn(canvas, MARGIN_L,
                          PAGE_H - self.repeat_top_offset - _h)

        canvas.restoreState()


# âââ NGS: section header bar âââââââââââââââââââââââââââââââââââââââââââââââââ
def _ngs_section_bar(text: str, S: dict) -> Table:
    """Dark-blue full-width bar with white text â 'Patient: Name'."""
    p = Paragraph(text, S["section_bar"])
    t = Table([[p]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_SECTION_BAR),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    return t


# âââ NGS: 6-column patient info table (PGTA-style colon alignment) âââââââââââ
# Layout: [label] [":"] [value] | [label] [":"] [value]
# Colon in its own narrow column ensures all colons are vertically aligned.
# Widths proportioned from PGTA reference: [108, 12, 161, 108, 12, 89] on 490pt
# Scaled to CONTENT_W â 510pt: [112, 13, 168, 112, 13, 92]

def _ngs_info_table(person: dict, S: dict, is_donor: bool = False, patient_name: str = "",
                    compact: bool = False, nabl: bool = False,
                    show_relationship: bool = False) -> Table:
    pf = "Donor" if is_donor else "Patient"
    cw = CONTENT_W

    # NABL seal shown only in the patient (non-donor) table
    show_nabl = nabl and not is_donor
    _LOGO_W = 21 * mm          # rendered image width
    _LOGO_COL_W = _LOGO_W + 3 * mm   # 3 mm natural gap; keeps right column generous

    if show_nabl:
        # 7-col layout: [left-label, left-colon, left-val, NABL-logo, right-label, right-colon, right-val]
        # Logo sits between the two data sections (col 3).
        # left-val (0.330) gives hospital names 2-line wrap; right-val (0.201) gives
        # long PINs ~85pt avail (>77pt needed); right-lbl (0.237) fits "Sample Receipt Date".
        rem = cw - _LOGO_COL_W
        col_w = [rem * 0.182, rem * 0.025, rem * 0.330, _LOGO_COL_W,
                 rem * 0.237, rem * 0.025, rem * 0.201]
    else:
        # Original 6-col widths matching PGTA proportions
        col_w = [cw * 0.220, cw * 0.025, cw * 0.329, cw * 0.220, cw * 0.025, cw * 0.181]

    def L(text): return Paragraph(f"<b>{text}</b>", S["lbl"])
    def C():     return Paragraph("<b>:</b>", S["lbl"])
    def V(text): return Paragraph(_title_case(_clean_display(text)), S["val"])
    # Name/place fields (patient/donor name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def VN(text): return Paragraph(_title_case(_clean_display(text), is_name=True), S["val"])
    # Fix 4: ID/code fields must NOT be title-cased â use R() for PIN, Sample Number, MR No.
    def R(text): return Paragraph(_clean_display(text), S["val"])
    def E():     return Paragraph("", S["lbl"])

    def V_name(text):
        # Keep font size constant; let long names wrap to a second line so the
        # row grows taller rather than the text shrinking to fit one line.
        display = _title_case(_clean_display(text), is_name=True)
        return Paragraph(display, S["val"])

    left_rows = [
        [L(f"{pf} name"), C(), V_name(person.get("name", ""))],
        [L("Gender / Age"), C(), V(_normalize_age(person.get("gender_age", "")))],
        [L("Hospital MR No"), C(), R(person.get("hospital_mr_no", "") or "NA")],
    ]

    # Diagnosis for patient only, not donor
    if not is_donor:
        left_rows.append([L("Diagnosis"), C(), V(person.get("diagnosis") or "NA")])

    left_rows.extend([
        [L("Referred By"), C(), V(person.get("referred_by", ""))],
        [L("Hospital/Clinic"), C(), VN(person.get("hospital_clinic", ""))],
    ])
    # On the patient/NABL table the Referred By and Hospital rows sit below the
    # seal, so their value cells span across the (freed) logo column for extra
    # width â letting long text stay on one line at full font, wrapping only when
    # it still doesn't fit (handled via the SPANs + logo_row_end below).
    hosp_idx     = len(left_rows) - 1
    referred_idx = len(left_rows) - 2

    if is_donor:
        rel_display = _format_relationship(person.get("relationship", ""), patient_name)
        left_rows.insert(2, [L("Relationship"), C(), V(rel_display)])
    elif show_relationship:
        rel_val = person.get("relationship", "") or "NA"
        left_rows.insert(1, [L("Relationship stated/\nClaimed"), C(), V(rel_val)])
        hosp_idx     += 1
        referred_idx += 1

    right_rows = [
        [L("PIN"), C(), R(person.get("pin", ""))],
        [L("Sample Number"), C(), R(person.get("sample_number", ""))],
        [L("Specimen"), C(), V(person.get("specimen") or "Blood - EDTA")],
        [L("Collection Date"), C(), V(person.get("collection_date", ""))],
        [L("Sample receipt date"), C(), V(person.get("receipt_date", ""))],
        [L("Report date"), C(), V(person.get("report_date", ""))],
    ]

    max_r = max(len(left_rows), len(right_rows))
    while len(left_rows)  < max_r: left_rows.append([E(), E(), E()])
    while len(right_rows) < max_r: right_rows.append([E(), E(), E()])

    _vpad = 2 if compact else 4

    if show_nabl:
        raw_nabl = _get_nabl_seal_bytes()
        # new_NABL.jpg is 1080Ã-1265 px â maintain aspect ratio from _LOGO_W
        _LOGO_H = _LOGO_W * (1265 / 1080)
        logo_img = Image(io.BytesIO(raw_nabl), width=_LOGO_W, height=_LOGO_H)
        logo_cell = [logo_img]

        # Span rows 1 to max_r-2 (the middle rows) so VALIGN=MIDDLE reliably
        # centres the logo between the top and bottom rows of the table.
        # When Referred By is populated shift the span one row up (start at row 0)
        # so the logo sits slightly higher visually.
        referred_by_val = _clean_display(person.get("referred_by", ""))
        has_referred = referred_by_val not in ("â", "", "-")
        logo_row_start = 0 if has_referred else 1
        # End the seal span above the Referred By row so both Referred By and
        # Hospital/Clinic can use the full width of the (freed) logo column.
        logo_row_end   = max(logo_row_start, referred_idx - 1)

        rows = []
        for i, (lr, rr) in enumerate(zip(left_rows, right_rows)):
            mid = logo_cell if i == logo_row_start else [E()]
            rows.append(lr + [mid] + rr)

        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_INFO_BG),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), _vpad),
            ("BOTTOMPADDING", (0, 0), (-1, -1), _vpad),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            # Left colon column (col 1)
            ("LEFTPADDING",   (1, 0), (1, -1), 0),
            ("RIGHTPADDING",  (1, 0), (1, -1), 2),
            # Logo column (col 3) â spans the middle rows; VALIGN=MIDDLE centres the image
            ("SPAN",          (3, logo_row_start), (3, logo_row_end)),
            ("ALIGN",         (3, logo_row_start), (3, logo_row_start), "CENTER"),
            ("VALIGN",        (3, logo_row_start), (3, logo_row_start), "MIDDLE"),
            # Referred By + Hospital/Clinic values extend across the (freed) logo
            # column on their rows so long text fits on one line beneath the seal.
            ("SPAN",          (2, referred_idx), (3, referred_idx)),
            ("SPAN",          (2, hosp_idx), (3, hosp_idx)),
            ("LEFTPADDING",   (3, 0), (3, -1), 0),
            ("RIGHTPADDING",  (3, 0), (3, -1), 0),
            ("TOPPADDING",    (3, 0), (3, -1), 0),
            ("BOTTOMPADDING", (3, 0), (3, -1), 0),
            # Right colon column (col 5)
            ("LEFTPADDING",   (5, 0), (5, -1), 0),
            ("RIGHTPADDING",  (5, 0), (5, -1), 2),
            # Right label column (col 4)
            ("LEFTPADDING",   (4, 0), (4, -1), 4),
        ]))
    else:
        rows = [lr + rr for lr, rr in zip(left_rows, right_rows)]
        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_INFO_BG),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), _vpad),
            ("BOTTOMPADDING", (0, 0), (-1, -1), _vpad),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            # Colon columns: no left padding so colon sits flush next to label
            ("LEFTPADDING",   (1, 0), (1, -1), 0),
            ("LEFTPADDING",   (4, 0), (4, -1), 0),
            ("RIGHTPADDING",  (1, 0), (1, -1), 2),
            ("RIGHTPADDING",  (4, 0), (4, -1), 2),
            # Extra left padding on right-side label column for clear visual center gap
            ("LEFTPADDING",   (3, 0), (3, -1), 14),
        ]))
    return t


# âââ NGS: HLA allele results table ââââââââââââââââââââââââââââââââââââââââââââ
# Header row â C_HLA_HDR (#F9BE8F).  Data rows â C_HLA_ROW (#F1F2F1).
# Row labels: "1" and "2" (Calibri-Bold 11).

def _hla_table(person: dict, S: dict, compact: bool = False, separate_drb: bool = False) -> Table:
    LOCI       = ["A", "B", "C", "DRB1", "DQB1", "DPB1"]
    EXTRA_LOCI = (["DRB3", "DRB4", "DRB5", "DQA1", "DPA1"]
                  if separate_drb else ["DRB345", "DQA1", "DPA1"])
    hla = person.get("hla", {})
    _drb_split = _split_drb345(hla) if separate_drb else {}

    def _val(l):
        if l == "DRB345":
            return _merged_drb345(hla)
        if l in ("DRB3", "DRB4", "DRB5"):
            return _drb_split.get(l, hla.get(l, [None, None]))
        return hla.get(l, [None, None])

    loci = [l for l in LOCI if any(hla.get(l, [None, None]))]
    loci += [l for l in EXTRA_LOCI if any(_val(l))]
    if not loci:
        loci = LOCI

    def _hdr(l): return "HLA DRB3/4/5*" if l == "DRB345" else f"HLA-{l}*"

    F_HDR = S["hla_hdr"].fontName
    F_VAL = S["hla_val"].fontName
    _CELL_PAD = 8  # total horizontal cell padding per column

    # Compute minimum column width for each data column so that both the header
    # text and the widest allele value in that column fit on a single line.
    def _disp(l, v):
        if l == "DRB345":
            return _clean_display(str(v)) if v and str(v).strip() else "\u2014"
        s = _clean_display(str(v)) if v and str(v).strip() else ""
        return _strip_prefix(s) if s else "\u2014"

    _min_widths = []
    for l in loci:
        al = _val(l)
        v1 = al[0] if al and al[0] else "\u2014"
        v2 = al[1] if al and len(al) > 1 and al[1] else "\u2014"
        _min_widths.append(max(
            pdfmetrics.stringWidth(_hdr(l), F_HDR, 11),
            pdfmetrics.stringWidth(_disp(l, v1), F_VAL, 10),
            pdfmetrics.stringWidth(_disp(l, v2), F_VAL, 10),
        ) + _CELL_PAD)

    lbl_w = CONTENT_W * 0.10
    n = len(loci)
    _natural_w = (CONTENT_W - lbl_w) / n  # old equal-share formula

    # Each column gets at least its natural equal share so the table looks the same
    # as before when content is short. If any column needs more space (e.g. a long
    # DRB3* allele), that column expands and the table grows wider â never wraps.
    col_w = [lbl_w] + [max(_natural_w, w) for w in _min_widths]

    # Scale header font only when the smallest column can't fit its header at 11pt.
    _hdr_texts  = ["LOCUS"] + [_hdr(l) for l in loci]
    _max_hdr_w  = max(pdfmetrics.stringWidth(t, F_HDR, 11) for t in _hdr_texts)
    avail_w     = min(col_w[1:]) - 6
    hdr_size    = 11.0 if _max_hdr_w <= avail_w else max(7.5, 11.0 * avail_w / _max_hdr_w)
    hdr_style   = S["hla_hdr"] if hdr_size >= 11.0 else ParagraphStyle(
        "hla_hdr_fit", parent=S["hla_hdr"], fontSize=hdr_size, leading=hdr_size + 2)

    def HH(t): return Paragraph(t, hdr_style)
    # Fix 1: route every allele cell through _clean_display so "Insufficient Data"
    # (and any other sentinel values) is always replaced with an em-dash at render time.
    def HV(t): return Paragraph(_clean_display(t), S["hla_val"])
    def HL(t): return Paragraph(t, S["hla_lbl"])

    header = [HH("LOCUS")] + [HH(_hdr(l)) for l in loci]
    r1     = [HV("1")]
    r2     = [HV("2")]
    for l in loci:
        al = _val(l)
        if l == "DRB345":
            # 11-loci combined column: keep locus prefix so reader knows which of DRB3/4/5 it is
            r1.append(HV(al[0] if al and al[0] else "\u2014"))
            r2.append(HV(al[1] if al and len(al) > 1 and al[1] else "\u2014"))
        else:
            r1.append(HV(_strip_prefix(al[0]) if al and al[0] else "\u2014"))
            r2.append(HV(_strip_prefix(al[1]) if al and len(al) > 1 and al[1] else "\u2014"))

    t = Table([header, r1, r2], colWidths=col_w)
    _vpad = 2 if compact else 4
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_HLA_HDR),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BLACK),
        ("BACKGROUND",    (0, 1), (-1, 1), C_HLA_ROW),
        ("BACKGROUND",    (0, 2), (-1, 2), C_HLA_ROW),
        ("GRID",          (0, 0), (-1, -1), 0.5, WHITE),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), _vpad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), _vpad),
    ]))
    return t


# âââ NGS: one person block (info + HLA + optional match + remarks) ââââââââââââ
def _ngs_person_block(person: dict, is_donor: bool, match_str: str, S: dict,
                      patient_name: str = "", force_compact: bool = False,
                      spacing_scale: float = 1.0, extra_inner_gap: float = 0.0,
                      extra_post_hla_gap: float = 0.0, extra_inter_block_gap: float = 0.0,
                      no_compact: bool = False, nabl: bool = False,
                      show_relationship: bool = False, separate_drb: bool = False) -> list:
    _raw_remarks = person.get("remarks", "")
    _remarks_display = _clean_display(_raw_remarks) if _raw_remarks else ""
    # Normalize HLA allele nomenclature in remarks (capitalize and fix formatting)
    _remarks_display = _normalize_hla_alleles(_remarks_display) if _remarks_display else ""
    if _remarks_display == "â":
        _remarks_display = ""
    if len(_remarks_display) > 600:
        _remarks_display = _remarks_display[:580] + "..."

    _match_display = _clean_display(match_str) if match_str else ""
    if is_donor and _match_display:
        _match_display = re.sub(r'\s*\(\d+%\)', '', _match_display).strip()

    def _is_real(v):
        if not v or v == "\u2014": return False
        if str(v).strip().upper() in ["NA", "N/A", "NONE", "NULL", "-"]: return False
        return True

    has_remarks = _is_real(_remarks_display)
    has_match   = _is_real(_match_display)

    long_content = (has_remarks and len(_remarks_display) > 220) or (has_remarks and has_match)

    if no_compact:
        # Transplant donor / 11-Loci: never shrink table font/padding.
        # When this block has remarks or match, keep inner_gap tight (label table
        # to locus table) but give post_hla_spacer (locus table to Remarks) some
        # visible room â there's normally slack left on the page below the
        # remarks, so this still fits without spilling to another page.
        compact_info = False
        if has_remarks or has_match:
            inner_gap       = 1 * mm
            post_hla_spacer = 1 * mm
            inter_block_gap = 3 * mm
        else:
            inner_gap        = 2 * mm
            post_hla_spacer  = 4 * mm
            inter_block_gap  = 3 * mm
    elif long_content or (force_compact and (has_remarks or has_match)):
        inner_gap        = 0.5 * mm
        post_hla_spacer  = 0.5 * mm
        inter_block_gap  = 0.5 * mm
        compact_info     = True
    elif force_compact or has_remarks or has_match:
        inner_gap        = 1 * mm
        post_hla_spacer  = 1 * mm
        inter_block_gap  = 1 * mm
        compact_info     = True
    else:
        inner_gap        = 2 * mm
        post_hla_spacer  = 4 * mm
        inter_block_gap  = 3 * mm
        compact_info     = False

    if spacing_scale != 1.0:
        inner_gap       *= spacing_scale
        post_hla_spacer *= spacing_scale
        inter_block_gap *= spacing_scale
    inner_gap       += extra_inner_gap * mm
    post_hla_spacer += extra_post_hla_gap * mm
    inter_block_gap += extra_inter_block_gap * mm

    # Info table kept together as its own unit â it moves to the next page intact
    # if it doesn't fit, independent of the HLA table that follows.
    elems = [
        KeepTogether([_ngs_info_table(person, S, is_donor=is_donor, patient_name=patient_name,
                                      compact=compact_info, nabl=nabl,
                                      show_relationship=show_relationship)]),
        Spacer(1, inner_gap),
    ]

    # Remarks + match kept together so they never split across pages.
    tail = []
    if has_remarks:
        # Transplant Donor / 11-Loci render remarks 1pt larger than the other
        # NGS-style templates (single_hla, single_rpl) that share this block.
        _remarks_size = 11 if no_compact else 10
        tail.append(Paragraph(f"<b>Remarks:</b> {_remarks_display}",
                              ParagraphStyle("remarks_j", parent=S["body_small"],
                                             fontSize=_remarks_size, leading=_remarks_size + 2,
                                             wordWrap='CJK',
                                             alignment=TA_LEFT, spaceAfter=2)))
    if has_match:
        if has_remarks:
            tail.append(Spacer(1, 0.5 * mm))
        tail.append(Paragraph(
            f"<b>Match: {_match_display}</b>",
            ParagraphStyle("ms", fontName=_f("Calibri-Bold","Helvetica-Bold"),
                           fontSize=11, textColor=BLACK, alignment=TA_LEFT,
                           leading=13, spaceBefore=0, spaceAfter=1)
        ))
        tail.append(HRFlowable(width="100%", thickness=0.5, color=BLACK, spaceBefore=1, spaceAfter=1))

    # HLA table + its remarks/match are kept together as ONE unit so the table
    # never lands at the bottom of a page while its remarks spill onto the next.
    hla_and_tail = [_hla_table(person, S, compact=compact_info, separate_drb=separate_drb), Spacer(1, post_hla_spacer)] + tail
    elems.append(KeepTogether(hla_and_tail))


    elems.append(Spacer(1, inter_block_gap))
    return elems


# âââ RPL: unified 5-column couple + HLA table âââââââââââââââââââââââââââââââââ
# Demographic rows: SPAN cols 1-2 for patient, SPAN cols 3-4 for donor.
# HLA rows: separate allele per column (p_a1 | p_a2 | d_a1 | d_a2).
# All cells WHITE with black 0.5pt grid.  Header row: black bg, white text.
# Column widths derived from fitz measurements of Mrs.Hemalatha RPL PDF.

def _rpl_couple_table(patient: dict, donor: dict, S: dict, comment_text: str = "") -> Table:
    p_name = patient.get("name", "\u2014")
    d_name = donor.get("name",   "\u2014")
    cw = CONTENT_W

    # Col widths: label 24.6%, remaining 75.4% split equally across 4 data columns
    # so patient pair and donor pair have identical horizontal width.
    _label_w = cw * 0.246
    _data_w  = (cw - _label_w) / 4
    col_w = [_label_w, _data_w, _data_w, _data_w, _data_w]

    def RL(t): return Paragraph(f"<b>{t}</b>", S["rpl_lbl"])
    def RV(t, is_name=False): return Paragraph(_title_case(_clean_display(t), is_name=is_name), S["rpl_val"])
    # Fix 4: ID/code fields (PIN, Sample Number) must NOT be title-cased.
    def RR(t): return Paragraph(_clean_display(t), S["rpl_val"])
    _RAW_LABELS = {"PIN", "Sample Number"}
    # Name/place fields (patient/donor name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    _NAME_LABELS = {"Name", "Hospital/Clinic"}
    def RVC(label, val):
        if label in _RAW_LABELS:
            return RR(val)
        return RV(val, is_name=label in _NAME_LABELS)
    def HL(t): return Paragraph(f"<b>{t}</b>", S["rpl_hla_lbl"])
    def HV(t): return Paragraph(_clean_display(t), S["rpl_hla_val"])
    def HDR(t): return Paragraph(f"<b>{t}</b>", S["rpl_hdr_name"])

    data = []
    spans = []

    # No header row â reference PDF starts directly with demographic rows (confirmed by fitz audit)

    # Demographic rows - patient has diagnosis, donor does not
    # Patient labels (13 rows with diagnosis + hospital_mr_no)
    p_labels = [
        "Name", "Relationship stated/\nClaimed", "Age/Gender",
        "Hospital MR No",
        "Diagnosis", "Referred By", "Hospital/Clinic",
        "PIN", "Sample Number", "Specimen",
        "Collection Date", "Sample receipt date", "Report date",
    ]
    p_vals = [
        patient.get("name", ""), patient.get("relationship", "") or "NA",
        _normalize_age(patient.get("gender_age", "")),
        patient.get("hospital_mr_no", "") or "NA",
        patient.get("diagnosis") or "NA",
        patient.get("referred_by", ""), patient.get("hospital_clinic", ""),
        patient.get("pin", ""), patient.get("sample_number", ""),
        patient.get("specimen") or "Blood - EDTA",
        patient.get("collection_date", ""), patient.get("receipt_date", ""),
        patient.get("report_date", ""),
    ]

    # Donor labels (13 rows, matching patient)
    d_labels = [
        "Name", "Relationship stated/\nClaimed", "Age/Gender",
        "Hospital MR No",
        "Diagnosis", "Referred By", "Hospital/Clinic",
        "PIN", "Sample Number", "Specimen",
        "Collection Date", "Sample receipt date", "Report date",
    ]
    d_vals = [
        donor.get("name", ""), donor.get("relationship", "") or "NA",
        _normalize_age(donor.get("gender_age", "")),
        donor.get("hospital_mr_no", "") or "NA",
        donor.get("diagnosis") or "NA",
        donor.get("referred_by", ""), donor.get("hospital_clinic", ""),
        donor.get("pin", ""), donor.get("sample_number", ""),
        donor.get("specimen") or "Blood - EDTA",
        donor.get("collection_date", ""), donor.get("receipt_date", ""),
        donor.get("report_date", ""),
    ]
    demo_start = 0
    # Build rows - both patient and donor have 13 rows
    for i in range(len(p_labels)):
        r = demo_start + i
        p_lbl = p_labels[i]
        p_val = p_vals[i]
        d_val = d_vals[i]

        data.append([RL(p_lbl), RVC(p_lbl, p_val), Paragraph("", S["rpl_lbl"]),
                     RVC(p_lbl, d_val), Paragraph("", S["rpl_lbl"])])
        spans += [("SPAN", (1, r), (2, r)), ("SPAN", (3, r), (4, r))]

    hla_start = len(data)

    # HLA rows â 5-column, no SPAN
    LOCI = ["A", "B", "C", "DRB1", "DQB1", "DPB1"]
    p_hla = patient.get("hla", {})
    d_hla = donor.get("hla",   {})
    for i, locus in enumerate(LOCI):
        pa = p_hla.get(locus, [None, None])
        da = d_hla.get(locus, [None, None])
        pa1 = _strip_prefix(pa[0]) if pa and pa[0] else "\u2014"
        pa2 = _strip_prefix(pa[1]) if pa and len(pa) > 1 and pa[1] else "\u2014"
        da1 = _strip_prefix(da[0]) if da and da[0] else "\u2014"
        da2 = _strip_prefix(da[1]) if da and len(da) > 1 and da[1] else "\u2014"
        data.append([HL(f"HLA-{locus}*"), HV(pa1), HV(pa2), HV(da1), HV(da2)])

    if comment_text:
        data.append([Paragraph(comment_text, S["comment"]), "", "", "", ""])
        spans.append(("SPAN", (0, len(data) - 1), (4, len(data) - 1)))

    n_rows = len(data)
    hosp_row_rpl = next(
        (i for i, lbl in enumerate(p_labels) if "Hospital" in lbl), None)
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, -1),             WHITE),
        ("TEXTCOLOR",     (0, 0), (-1, 0),              BLACK),
        ("ALIGN",         (0, 0), (-1, 0),              "CENTER"),
        ("GRID",          (0, 0), (-1, -1),             0.5, C_RPL_BORDER),
        ("VALIGN",        (0, 0), (-1, -1),             "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1),             4),
        ("BOTTOMPADDING", (0, 0), (-1, -1),             4),
        ("LEFTPADDING",   (0, 0), (-1, -1),             4),
        ("RIGHTPADDING",  (0, 0), (-1, -1),             4),
        # HLA rows: allele cols centered, label col left
        ("ALIGN",         (1, hla_start), (-1, n_rows - 1), "CENTER"),
        # Demographic value cols centered
        ("ALIGN",         (1, 1), (-1, hla_start - 1), "CENTER"),
    ] + spans
    # Hospital/Clinic row: top-align so label anchors to first wrapped line
    if hosp_row_rpl is not None:
        style_cmds.append(("VALIGN", (0, hosp_row_rpl), (-1, hosp_row_rpl), "TOP"))

    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle(style_cmds))
    return t


# âââ RPL: reference table + HLA-C supertype table âââââââââââââââââââââââââââââ
def _rpl_reference_section(rpl_ref: dict, patient: dict, donor: dict, S: dict,
                            include_comment: bool = True) -> list:
    elems = []
    p_name    = patient.get("name", "")
    d_name    = donor.get("name",   "")
    match_str = rpl_ref.get("match_str", "")
    match_pct = rpl_ref.get("match_pct", "")

    # Comment block (can be suppressed when caller emits it separately)
    if include_comment and (match_str or match_pct):
        bold_match = f"<b>{match_str} ({match_pct})</b>" if match_str else f"<b>{match_pct}</b>"
        comment = (
            f"<b>COMMENT:</b> HLA-A, B, C, DRB1, DQB1 &amp; DPB1 locus typing patterns of the "
            f"above individuals indicate {bold_match} matches at High resolution."
        )
        elems.append(Paragraph(comment, S["comment"]))
        elems.append(Spacer(1, 2 * mm))

    # Reference heading + ref table kept together; HLA-C table separate so it
    # can flow to the previous page if space allows.
    ref_group = [Paragraph("<b>Reference:</b>", S["ref_hdr"])]

    # 3-column reference table â headers SegoeUI-Bold 10pt (confirmed by fitz audit)
    # Build the HLA matching cell content: vertical stacking "Overall â X%" and "Class-II â Y%"
    class2_pct = rpl_ref.get("class2_pct", "")
    if match_pct and class2_pct:
        hla_matching_text = f"Overall â {match_pct}<br/>Class-II â {class2_pct}"
    elif match_pct:
        hla_matching_text = f"Overall â {match_pct}"
    else:
        hla_matching_text = "\u2014"

    ref_data = [
        [
            Paragraph("<b>Names/Code</b>",                                    S["lbl_center"]),
            Paragraph("<b>HLA matching between couples</b>",                  S["lbl_center"]),
            Paragraph("<b>HLA sharing for Recurrent miscarriage/RIF</b>",     S["lbl_center"]),
        ],
        [
            Paragraph(_clean_display(f"{_title_case(_capitalize_initials(p_name), is_name=True)} / {_title_case(_capitalize_initials(d_name), is_name=True)}"), S["rpl_val"]),
            Paragraph(_clean_display(hla_matching_text),      S["rpl_val"]),
            Paragraph(_clean_display(rpl_ref.get("hla_sharing_rif", ">50%")), S["rpl_val"]),
        ],
    ]
    # Reference table header uses SegoeUI-Bold 10pt black on white (no colour fill â confirmed)
    ref_t = Table(ref_data,
                  colWidths=[CONTENT_W * 0.34, CONTENT_W * 0.30, CONTENT_W * 0.36])
    ref_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ("TEXTCOLOR",     (0, 0), (-1, -1), BLACK),
        ("GRID",          (0, 0), (-1, -1), 0.5, C_RPL_BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    ref_group.append(ref_t)

    # HLA-C supertype table â also plain white, no fills (confirmed)
    hla_c_p = rpl_ref.get("hla_c_patient", "")
    hla_c_d = rpl_ref.get("hla_c_donor",   "")
    if hla_c_p or hla_c_d:
        c_data = [
            [Paragraph("<b>Maternal HLA-C Type</b>", S["rpl_lbl_center"]),
             Paragraph("<b>Paternal HLA-C Type</b>",  S["rpl_lbl_center"])],
            [Paragraph(_clean_display(hla_c_p), S["rpl_val"]),
             Paragraph(_clean_display(hla_c_d), S["rpl_val"])],
        ]
        c_t = Table(c_data, colWidths=[CONTENT_W * 0.50, CONTENT_W * 0.50])
        c_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
            ("TEXTCOLOR",     (0, 0), (-1, -1), BLACK),
            ("GRID",          (0, 0), (-1, -1), 0.5, C_RPL_BORDER),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elems.append(KeepTogether(ref_group))
        elems.append(Spacer(1, 8 * mm))
        elems.append(KeepTogether([c_t]))
        return elems

    elems.append(KeepTogether(ref_group))
    return elems


# âââ Methodology block (shared) âââââââââââââââââââââââââââââââââââââââââââââââ
def _methodology_block(case: dict, S: dict, merge: bool = False) -> list:
    """
    IMGT â Remarks: â Coverage (: prefix lines) â Methodology â Typing Status
    Matches the exact format seen in all manual report PDFs.
    NO horizontal rules between sections - only one line before signatures.

    By default returns [KeepTogether(coverage_block), KeepTogether(method_block)]
    as two independent units. Pass merge=True to instead get the *raw*,
    unwrapped flowables (coverage_block + method_block) â callers that need to
    combine this with other content into a single KeepTogether (e.g. so
    Coverage is never orphaned from Methodology/Signatures) must wrap the
    *raw* flowables directly, never nest a KeepTogether inside another one:
    nested KeepTogethers' wrap() always reports a huge sentinel height, which
    makes the outer KeepTogether's fit-check wrongly conclude the content is
    far too big and push it to a fresh page even when it would have fit.
    """
    nabl   = case.get("nabl", True)
    imgt   = case.get("imgt_release", "") or "3.56.0"  # Default IMGT version if not specified
    method = case.get("methodology", "") or (METHODOLOGY_MINISEQ if nabl else METHODOLOGY_SURFSEQ)
    status = case.get("typing_status", "") or "Complete"

    # Split into two smaller KeepTogether groups so neither block forces a large
    # blank gap when the previous section ends near a page boundary.
    # Group 1: IMGT + Remarks: + Coverage label/lines (~85 pt)
    coverage_lines = COVERAGE_LINES
    if case.get("report_type") == "loci11":
        coverage_lines = COVERAGE_LINES + EXTRA_COVERAGE_LINES_11LOCI

    # "Coverage" sits as a label to the left of the colon-prefixed lines, which
    # are stacked as one paragraph so they all line up under the first line
    # rather than starting back at the page's left margin.
    cov_label = Paragraph("<b>Coverage</b>", S["body"])
    cov_lines = Paragraph("<br/>".join(coverage_lines), S["coverage"])
    cov_table = Table([[cov_label, cov_lines]], colWidths=[60, CONTENT_W - 60])
    cov_table.hAlign = "LEFT"
    cov_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # The personal remarks are rendered below each person's locus table in
    # _ngs_person_block, so this static "Remarks:" coverage label is only shown
    # when there's actual remarks content somewhere â otherwise it renders as a
    # blank, orphan label in the IMGT/Coverage section.
    def _has_real_remarks(p):
        v = str((p or {}).get("remarks", "") or "").strip()
        return bool(v) and v not in ("â", "-", "NA", "N/A", "None", "null")
    _patient_mb = case.get("patient", {})
    _donors_mb  = case.get("donors", []) or []
    _show_remarks_label = _has_real_remarks(_patient_mb) or any(_has_real_remarks(d) for d in _donors_mb)
    coverage_block = [Paragraph(f"<b>IMGT/HLA Release</b> {imgt}", S["body"])]
    if _show_remarks_label:
        coverage_block.append(Paragraph("<b>Remarks:</b>", S["body"]))
    coverage_block.append(cov_table)

    # Group 2: Methodology + HR + Typing Status (~40 pt)
    # 11-Loci's reference layout puts the "Methodology:" label on its own line,
    # with the method sentence on the line below â other report types keep the
    # label and sentence on one line (their reference layouts use that style).
    if case.get("report_type") == "loci11":
        methodology_para = Paragraph(f"<b>Methodology:</b><br/>{method}", S["body"])
    else:
        methodology_para = Paragraph(f"<b>Methodology:</b>  {method}", S["body"])
    method_block = [
        Spacer(1, 1 * mm),
        methodology_para,
        Spacer(1, 1 * mm),
        HRFlowable(width="100%", thickness=0.5, color=BLACK),
        Spacer(1, 1 * mm),
        Paragraph(f"<b>Typing Status:</b>  {status}", S["body"]),
    ]

    if merge:
        return coverage_block + method_block
    return [KeepTogether(coverage_block), KeepTogether(method_block)]


# âââ Signature block ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def _signature_block(signatories: list, S: dict) -> list:
    """
    HR line â 'This report has been reviewed and approved by:'  (SegoeUI-Bold 11.8pt #2C6BAA)
    â signature images + name + role side-by-side directly below (matching reference PDF layout).
    If signatory has seal_b64, the rubber stamp appears below the signature image.
    """
    if not signatories:
        return []

    n        = len(signatories)
    col_each = CONTENT_W / n

    cols = []
    for sig in signatories:
        sign_data = hla_assets.get_image_bytes(sig["sign_b64"])
        sign_img  = Image(io.BytesIO(sign_data), width=35 * mm, height=16 * mm)
        cell_rows = [
            [sign_img],
            [Paragraph(sig.get("name",  ""), S["sign_name"])],
            [Paragraph(sig.get("title", ""), S["sign_role"])],
        ]
        seal_b64 = sig.get("seal_b64")
        if seal_b64:
            seal_data = hla_assets.get_image_bytes(seal_b64)
            _seal_io  = io.BytesIO(seal_data)
            _seal_tmp = Image(_seal_io)
            _sw, _sh  = _seal_tmp.imageWidth, _seal_tmp.imageHeight
            _max      = 50 * mm
            # Preserve aspect ratio â scale so the longer dimension equals _max
            if _sw >= _sh:
                seal_img = Image(io.BytesIO(seal_data), width=_max, height=_max * _sh / _sw)
            else:
                seal_img = Image(io.BytesIO(seal_data), width=_max * _sw / _sh, height=_max)
            cell_rows.append([seal_img])

        inner = Table(cell_rows, colWidths=[col_each])
        inner.setStyle(TableStyle([
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ]))
        cols.append(inner)

    outer = Table([cols], colWidths=[col_each] * n)
    outer.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    return [
        Spacer(1, 1 * mm),
        Paragraph("<b>This report has been reviewed and approved by:</b>",
                  S["sign_approval"]),
        outer,
    ]


# âââ Report builders ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _build_ngs_single(case: dict, S: dict) -> list:
    """
    single_hla â title + patient block + methodology + signatures.

    Strategy:
    - Patient block: wrapped in KeepTogether to prevent splitting
    - Signatures: NOT wrapped in KeepTogether â single_hla must always be 1 page,
      and KeepTogether was pushing signatures to page 2 even when space was available.
      The signature outer table is a single row so it won't split mid-row.
    """
    patient     = case["patient"]
    signatories = case.get("signatories") or hla_assets.get_default_signatories(
        "single_hla", case.get("nabl", True))

    elems = []

    elems.extend(_ngs_person_block(patient, is_donor=False, match_str="", S=S,
                                   nabl=case.get("nabl", True), separate_drb=True))

    elems.extend(_methodology_block(case, S))
    sig_items = _signature_block(signatories, S)
    if sig_items:
        elems.extend(sig_items)

    return elems


def _build_ngs_transplant(case: dict, S: dict) -> list:
    """
    transplant_donor â title + patient + each donor + methodology + signatures.

    Strategy:
    - Patient block: wrapped in KeepTogether to prevent splitting
    - Each donor block: wrapped in KeepTogether to prevent splitting
    - Methodology flows naturally; signatures kept together as one unit.
    """
    patient     = case["patient"]
    donors      = case.get("donors", [])
    signatories = case.get("signatories") or hla_assets.get_default_signatories(
        "transplant_donor", case.get("nabl", True))

    # When any person has remarks or a match string, tighten inter-block spacing so
    # the remarks fit on the same page rather than spilling to the next one.
    def _person_has_content(p):
        return bool((p.get("remarks") or "").strip()) or bool((p.get("match") or "").strip())
    any_remarks = _person_has_content(patient) or any(_person_has_content(d) for d in donors)
    # The 2x/4mm "spread" spacing exists to fill the page nicely when there's a
    # donor block to space out from the patient block, using the standard 6-locus
    # table. The 11-Loci report's table is wider (DRB3/4/5 column), has a taller,
    # word-wrapped header, and renders Remarks 1pt larger (see _remarks_size
    # below), so the full standard spread risks pushing the patient+donor blocks
    # off page 1 when both remarks and a match score are present â 1.5x (with no
    # extra_inner_gap) is the most headroom loci11 can take and still keep that
    # combination on page 1, so loci11 always uses that (regardless of
    # remarks/donors) for visible space between the demography table and each
    # person's locus table. (IMGT/HLA Release still always lands on its own
    # fresh page regardless of this spacing choice â see PageBreakIfNotEmpty
    # below.)
    _is_loci11 = case.get("report_type") == "loci11"
    _post_extra, _inter_extra = 0.0, 0.0
    if _is_loci11:
        _scale, _extra = 1.5, 0.0
    # The 2x/4mm "spread" spacing below assumes a single patient+donor pair
    # (per-block extra space compounds with each additional person), so with
    # 2+ donors it eats up the room IMGT/Coverage+Methodology needs to fit on
    # the same page â use the tight spacing whenever there's more than one
    # donor, regardless of remarks/match.
    elif any_remarks or not donors or len(donors) >= 2:
        _scale, _extra = 1.0, 0.0
        # Transplant Donor (6-locus table, no DRB3/4/5 wrap) has much more page-1
        # headroom than 11-Loci even with remarks+match present, so it can afford
        # visible space between the locus table/Remarks and the next person's
        # block without risking a 3rd page.
        if donors:
            _post_extra, _inter_extra = 1.5, 1.5
    else:
        _scale, _extra = 2.0, 4.0

    _sep_drb = case.get("report_type") != "loci11"

    elems = []
    elems.extend(_ngs_person_block(patient, is_donor=False, match_str="", S=S,
                                   spacing_scale=_scale, extra_inner_gap=_extra,
                                   extra_post_hla_gap=_post_extra, extra_inter_block_gap=_inter_extra,
                                   no_compact=True,
                                   nabl=case.get("nabl", True), separate_drb=_sep_drb))

    _p_name = patient.get("name", "")
    for d in donors:
        elems.extend(_ngs_person_block(d, is_donor=True, match_str=d.get("match", ""), S=S,
                                       extra_post_hla_gap=_post_extra, extra_inter_block_gap=_inter_extra,
                                       patient_name=_p_name,
                                       spacing_scale=_scale, extra_inner_gap=_extra, no_compact=True,
                                       nabl=case.get("nabl", True), separate_drb=_sep_drb))

    # Drop the trailing inter-block Spacer left by the last person block so it
    # doesn't add unwanted gap before the IMGT/Coverage block that follows.
    while elems and isinstance(elems[-1], Spacer):
        elems.pop()

    # IMGT/Coverage and Methodology are kept as one block (raw flowables,
    # wrapped in a single non-nested KeepTogether â see _methodology_block's
    # merge=True docstring) so Coverage never gets orphaned alone on a page
    # with Methodology spilling to the next one. Signatures are a separate
    # block so they can flow onto whatever page has room on their own,
    # without dragging the (often larger) Coverage + Methodology block down
    # with them when only the signatures don't fit.
    elems.append(KeepTogether(_methodology_block(case, S, merge=True)))
    sig_items = _signature_block(signatories, S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


def _build_ngs_photo(case: dict, S: dict) -> list:
    """
    ngs_photo â "HLA (NGS with Photo)".

    Same data model as transplant_donor, but page 1 uses a combined side-by-side
    patient|donor demography table, a patient/donor photo + relation block, and a
    single combined typing-result table (one section per person). Page 2 carries
    an auto-generated Interpretation paragraph followed by the same methodology
    and signature blocks as the transplant report.
    """
    patient     = case.get("patient", {})
    donors      = case.get("donors", [])
    donor       = donors[0] if donors else {}
    nabl        = case.get("nabl", True)
    signatories = case.get("signatories") or hla_assets.get_default_signatories(
        "transplant_donor", nabl)

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")

    def _P(text, font=F_BOLD, size=10, color=BLACK, align=TA_LEFT, leading=None):
        return Paragraph(text, ParagraphStyle("_np", fontName=font, fontSize=size,
            textColor=color, alignment=align, leading=leading or size + 2))

    def _clean(val):
        s = str(val).strip() if val else ""
        return s if s and s.lower() not in ("nan", "none", "") else "NA"

    def _norm(val):
        return _title_case(_clean_display(val)) or "NA"

    # Name/place fields (patient/donor name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def _norm_name(val):
        return _title_case(_clean_display(val), is_name=True) or "NA"

    def _raw(val):
        return _clean_display(val) or "NA"

    elems = []

    # ââ Combined demography table (patient | donor) âââââââââââââââââââââââââââ
    info_lbl_style = ParagraphStyle("_np_lbl", fontName=F_BOLD, fontSize=10,
                                    textColor=BLACK, leading=12)
    info_val_style = ParagraphStyle("_np_val", fontName=F_BOLD, fontSize=10,
                                    textColor=BLACK, leading=12)

    def IL(t): return Paragraph(f"<b>{t}</b>", info_lbl_style)
    def IV(t): return Paragraph(_norm(t), info_val_style)
    def IR(t): return Paragraph(_raw(t),  info_val_style)
    def IC():  return Paragraph("<b>:</b>", info_lbl_style)
    def E():   return Paragraph("", info_lbl_style)

    info_col_w = _demography_col_widths(patient, donor, nabl=nabl)

    def IV_name(text, col_w_pts):
        return Paragraph(_norm_name(text), info_val_style)

    if nabl:
        _logo_w = 21 * mm
        _logo_h = _logo_w * (1265 / 1080)
        gap_cell = Image(io.BytesIO(_get_nabl_seal_bytes()), width=_logo_w, height=_logo_h)
    else:
        gap_cell = E()

    info_rows = [
        [IL("Patient name"),    IC(), IV_name(patient.get("name", ""), info_col_w[2]), gap_cell, IL("Donor name"),           IC(), IV_name(donor.get("name", ""), info_col_w[6])],
        [IL("Gender / Age"),    IC(), IR(_normalize_age(patient.get("gender_age", ""))), E(), IL("Gender / Age"),       IC(), IR(_normalize_age(donor.get("gender_age", "")))],
        [IL("PIN"),             IC(), IR(patient.get("pin", "")),            E(), IL("PIN"),                 IC(), IR(donor.get("pin", "NA"))],
        [IL("Sample Number"),   IC(), IR(patient.get("sample_number", "")),  E(), IL("Sample Number"),       IC(), IR(donor.get("sample_number", "NA"))],
        [IL("Specimen"),        IC(), IV(patient.get("specimen") or "Blood - EDTA"), E(), IL("Sample receipt date"), IC(), IR(donor.get("receipt_date", ""))],
        [IL("Hospital/Clinic"), IC(), _fit_one_line(_norm_name(patient.get("hospital_clinic", "")), info_col_w[2], info_val_style), E(), IL("Report date"), IC(), IR(donor.get("report_date", ""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    _gap_span_style = [
        ("SPAN",   (3, 0), (3, len(info_rows) - 1)),
        ("ALIGN",  (3, 0), (3, 0), "CENTER"),
        ("VALIGN", (3, 0), (3, 0), "MIDDLE"),
    ] if nabl else []
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_INFO_BG),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (1, 0), (1, -1), 0),
        ("RIGHTPADDING",  (1, 0), (1, -1), 2),
        ("LEFTPADDING",   (3, 0), (3, -1), 0),
        ("RIGHTPADDING",  (3, 0), (3, -1), 0),
        ("LEFTPADDING",   (5, 0), (5, -1), 0),
        ("RIGHTPADDING",  (5, 0), (5, -1), 2),
    ] + _gap_span_style))
    elems.append(info_t)
    elems.append(Spacer(1, 1 * mm))

    # ââ Photo / relation block (centred, patient | donor) âââââââââââââââââââââ
    _ph_w  = 28 * mm
    _ph_h  = 30 * mm
    _pc_w  = 54 * mm
    _lbl_w = 38 * mm
    col_w_photo = [_lbl_w, _pc_w, _pc_w]

    def _photo_cell(photo_bytes):
        if photo_bytes:
            try:
                return Image(io.BytesIO(photo_bytes), width=_ph_w, height=_ph_h)
            except Exception:
                pass
        return Spacer(1, _ph_h)

    pat_photo   = _photo_cell(patient.get("photo_bytes"))
    don_photo   = _photo_cell(donor.get("photo_bytes"))
    rel_display = _norm(donor.get("relationship", "")) if donor else "NA"
    p_collect   = _clean(patient.get("collection_date", ""))
    d_collect   = _clean(donor.get("collection_date", ""))
    _GREY = C_INFO_BG

    photo_rows = [
        [E(),
         _P(_norm_name(patient.get("name", "")), F_BOLD, 11, BLACK, TA_CENTER),
         _P(_norm_name(donor.get("name", "")),   F_BOLD, 11, BLACK, TA_CENTER)],
        [E(), pat_photo, don_photo],
        [_P("Relation:",          F_BOLD, 10, BLACK, TA_LEFT),
         _P("Patient",            F_REG, 10, BLACK, TA_CENTER),
         _P(rel_display,          F_REG, 10, BLACK, TA_CENTER)],
        [_P("Date of Collection:", F_BOLD, 10, BLACK, TA_LEFT),
         _P(p_collect,            F_REG, 10, BLACK, TA_CENTER),
         _P(d_collect,            F_REG, 10, BLACK, TA_CENTER)],
    ]
    photo_t = Table(photo_rows, colWidths=col_w_photo)
    photo_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _GREY),
        ("BOX",           (0, 0), (-1, -1), 1.0, colors.white),
        ("INNERGRID",     (0, 0), (-1, -1), 1.0, colors.white),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
        ("ALIGN",         (1, 0), (2, -1),  "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    photo_t.hAlign = "CENTER"
    elems.append(photo_t)
    elems.append(Spacer(1, 3 * mm))

    # ââ Combined typing-result table ââââââââââââââââââââââââââââââââââââââââââ
    elems.append(_P("Typing Result", F_BOLD, 13, C_TITLE, TA_LEFT))
    elems.append(Spacer(1, 1 * mm))

    LOCI       = ["A", "B", "C", "DRB1", "DQB1", "DPB1"]
    EXTRA_LOCI = ["DRB3", "DRB4", "DRB5", "DQA1", "DPA1"]

    # Pre-split DRB3/4/5 for each person so alleles appear under the correct header
    all_hla = [patient.get("hla", {})] + [d.get("hla", {}) for d in donors]
    all_drb = [_split_drb345(h) for h in all_hla]

    def _has(h, drb, l):
        if l in ("DRB3", "DRB4", "DRB5"):
            return any(drb.get(l, h.get(l, [None, None])))
        return any(h.get(l, [None, None]))
    loci = [l for l in LOCI if any(_has(h, drb, l) for h, drb in zip(all_hla, all_drb))]
    loci += [l for l in EXTRA_LOCI if any(_has(h, drb, l) for h, drb in zip(all_hla, all_drb))]
    if not loci:
        loci = LOCI

    n = len(loci)
    col_w = [CONTENT_W * 0.13] + [CONTENT_W * 0.87 / n] * n

    def HH(t): return Paragraph(t, S["hla_hdr"])
    def HV(t): return Paragraph(_clean_display(t), S["hla_val"])
    def _hdr(l): return f"HLA-{l}*"

    def _person_table(name_label, person, include_header):
        h   = person.get("hla", {})
        drb = _split_drb345(h)
        rows, extra = [], []
        r = 0
        if include_header:
            rows.append([HH("LOCUS")] + [HH(_hdr(l)) for l in loci])
            extra += [("BACKGROUND", (0, 0), (-1, 0), C_HLA_HDR),
                      ("TEXTCOLOR",  (0, 0), (-1, 0), BLACK)]
            r += 1
        sec_r = r
        rows.append([_P(name_label, F_BOLD, 10, BLACK, TA_CENTER)] + [""] * len(loci))
        extra += [("SPAN",       (0, sec_r), (-1, sec_r)),
                  ("BACKGROUND", (0, sec_r), (-1, sec_r), C_HLA_ROW)]
        r += 1
        a_r = r
        cls_label = Paragraph("HLA-CLASS<br/>I , II", S["hla_lbl"])
        row1, row2 = [cls_label], [HV("")]
        for l in loci:
            al = drb.get(l, h.get(l, [None, None])) if l in ("DRB3", "DRB4", "DRB5") else h.get(l, [None, None])
            row1.append(HV(_strip_prefix(al[0]) if al and al[0] else "â"))
            row2.append(HV(_strip_prefix(al[1]) if al and len(al) > 1 and al[1] else "â"))
        rows.append(row1); rows.append(row2)
        extra += [("SPAN",       (0, a_r), (0, a_r + 1)),
                  ("BACKGROUND", (0, a_r), (-1, a_r + 1), C_HLA_ROW),
                  ("VALIGN",     (0, a_r), (0, a_r + 1), "MIDDLE")]
        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle([
            ("GRID",          (0, 0), (-1, -1), 0.5, WHITE),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ] + extra))
        return t

    def _remarks_para(person):
        raw = person.get("remarks", "")
        disp = _normalize_hla_alleles(_clean_display(raw)) if raw else ""
        if not disp or disp == "â":
            return None
        para = Paragraph(f"<b>Remarks:</b> {disp}",
                         ParagraphStyle("_np_rmk", parent=S["body_small"],
                                        fontSize=10, leading=12, wordWrap="CJK",
                                        alignment=TA_LEFT, spaceBefore=0, spaceAfter=0))
        # Wrap in a full-width grey cell (matching the locus table's row fill and
        # white gridlines) so the remarks read as a row inside the table.
        rmk_t = Table([[para]], colWidths=[CONTENT_W])
        rmk_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_HLA_ROW),
            ("BOX",           (0, 0), (-1, -1), 0.5, WHITE),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return rmk_t

    # Keep the patient locus table, the patient remarks, and the donor locus
    # table(s) together as one unit so a multi-line patient remark can never push
    # the donor locus onto the next page â both tables always stay on the same
    # page with the patient remarks between them. Donor remarks are emitted
    # *after* this unit so they may overflow to the next page on their own without
    # splitting the two tables.
    combined = [_person_table(f"{_norm_name(patient.get('name', ''))} (Patient)", patient, True)]
    _rp = _remarks_para(patient)
    if _rp:
        combined.append(_rp)
    # Patient remarks (grey cell) and the donor table(s) follow flush â no spacers â
    # so the patient table, remarks and donor table read as one continuous table.
    for d in donors:
        combined.append(_person_table(f"{_norm_name(d.get('name', ''))} (Donor)", d, False))
    elems.append(KeepTogether(combined))

    for d in donors:
        _rd = _remarks_para(d)
        if _rd:
            elems.append(_rd)

    # ââ Interpretation ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.append(Spacer(1, 3 * mm))
    interp_block = [_P("Interpretation", F_BOLD, 13, C_TITLE, TA_LEFT),
                    Spacer(1, 1 * mm)]
    interp_override = (case.get("ngs_photo_interpretation") or "").strip()
    if interp_override:
        interp_block.append(Paragraph(interp_override, S["body"]))
    else:
        p_name = _norm_name(patient.get("name", ""))
        for d in donors:
            d_name = _norm_name(d.get("name", ""))
            match  = re.sub(r"\s*\(\d+%\)", "", _clean_display(d.get("match", "")).strip()).strip()
            if match and match != "â":
                sentence = (f"The Patient ({p_name}) had showed about {match} match "
                            f"with the Donor ({d_name}).")
            else:
                sentence = (f"The Patient ({p_name}) had showed about â match "
                            f"with the Donor ({d_name}).")
            interp_block.append(Paragraph(sentence, S["body"]))
    # Keep the Interpretation together with the methodology block so it never sits
    # orphaned at the foot of page 1 while the methodology spills onto page 2 â the
    # two move to the next page together when they don't both fit below the tables.
    # merge=True avoids nesting a KeepTogether inside this outer one (which would
    # make ReportLab's fit-check wrongly see a near-infinite height and always
    # defer to a fresh page â see _methodology_block's docstring).
    elems.append(KeepTogether(interp_block + _methodology_block(case, S, merge=True)))

    sig_items = _signature_block(signatories, S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


def _build_rpl_couple(case: dict, S: dict) -> list:
    """
    rpl_couple â multi-page layout with natural page breaks:
      Page 1: title + unified couple+HLA table + comment + reference tables
              (flows to Page 2 if needed)
      Page 2+: methodology + BACKGROUND + DISCLAIMERS + signatures
              (all kept together, flows naturally across pages)

    Single-person RPL (no donor): falls back to NGS-single layout + RPL background.

    Strategy:
    - Page 1 content (couple table + reference) wrapped in KeepTogether where possible
    - Methodology block + Background + Disclaimers + Signatures kept together
    - Natural page breaks between major sections instead of forced PageBreaks
    """
    patient     = case["patient"]
    donors      = case.get("donors", [])
    donor       = donors[0] if donors else None
    rpl_ref     = case.get("rpl_reference", {})
    signatories = case.get("signatories") or hla_assets.get_default_signatories(
        "rpl_couple", case.get("nabl", True))

    elems = []

    # Helper: return a person's remarks as a markup string for embedding in a table cell.
    def _remarks_markup(person: dict, label: str = "Remarks") -> str:
        raw = person.get("remarks", "")
        if not raw or not str(raw).strip():
            return ""
        disp = _clean_display(raw)
        # Normalize HLA allele nomenclature in remarks (capitalize and fix formatting)
        disp = _normalize_hla_alleles(disp)
        if not disp or disp == "\u2014":
            return ""
        if len(disp) > 600:
            disp = disp[:580] + "..."
        return f"<b>{label}:</b> {disp}"

    # Helper: emit a person's remarks as a standalone Paragraph (single-person case).
    def _emit_remarks(person: dict, label: str):
        markup = _remarks_markup(person, label)
        if markup:
            elems.append(Paragraph(markup,
                                   ParagraphStyle("remarks_j", parent=S["body_small"],
                                                  fontSize=12, leading=14,
                                                  alignment=TA_LEFT, spaceAfter=6)))

    # ââ Page 1 content ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if donor:
        # Build comment text and embed it as the last row of the couple table.
        match_str = rpl_ref.get("match_str", "")
        match_pct = rpl_ref.get("match_pct", "")
        _comment_text = ""
        if match_str or match_pct:
            bold_match = f"<b>{match_str} ({match_pct})</b>" if match_str else f"<b>{match_pct}</b>"
            _comment_text = (
                f"<b>COMMENT:</b> HLA-A, B, C, DRB1, DQB1 &amp; DPB1 locus typing patterns of the "
                f"above individuals indicate {bold_match} matches at High resolution."
            )

        # Append patient/donor remarks into the same table cell as the comment.
        # Both share a single "Remarks:" label â collect text-only parts, then prefix once.
        def _remarks_text(person: dict) -> str:
            raw = person.get("remarks", "")
            if not raw or not str(raw).strip():
                return ""
            disp = _normalize_hla_alleles(_clean_display(raw))
            if not disp or disp == "â":
                return ""
            if len(disp) > 600:
                disp = disp[:580] + "..."
            return disp

        remark_texts = [t for t in [_remarks_text(patient), _remarks_text(donor)] if t]
        if remark_texts:
            suffix = f"<b>Remarks:</b> " + "<br/>".join(remark_texts)
            _comment_text = (_comment_text + f"<br/>{suffix}") if _comment_text else suffix

        # Keep couple table (with embedded comment+remarks row) together.
        elems.append(KeepTogether([_rpl_couple_table(patient, donor, S, comment_text=_comment_text),
                                   Spacer(1, 3 * mm)]))

        # Reference + HLA-C tables (no separate comment needed).
        elems += _rpl_reference_section(rpl_ref, patient, donor, S, include_comment=False)
    else:
        # Single-person RPL: NGS-style patient block
        patient_block = _ngs_person_block(patient, is_donor=False, match_str="", S=S,
                                          nabl=case.get("nabl", True), separate_drb=True)
        elems.append(KeepTogether(patient_block))
        _emit_remarks(patient, "Remarks")

    # Add spacer to help with page flow
    elems.append(Spacer(1, 5 * mm))

    # ââ Methodology + Background + Disclaimers + Signatures âââââââââââââââââââ
    methodology_items = _methodology_block(case, S)
    elems.extend(methodology_items)

    # Fix 4: Do NOT wrap Background+Disclaimer in KeepTogether â that forces the
    # entire ~450pt block to the next page when only ~350pt remains, leaving a
    # large blank gap after Typing Status.  Natural flow fills the available space
    # on the current page and continues on the next page with zero gap.
    # (Fix 3 from previous session removed the 3mm spacer here; that stands.)
    elems.append(Paragraph("<b>BACKGROUND</b>",  S["section_hdr"]))
    elems.append(Paragraph(RPL_BACKGROUND,        S["justify"]))
    elems.append(Spacer(1, 2 * mm))
    # Keep the DISCLAIMERS heading paired with the first item so the heading
    # never orphans at the bottom of a page.
    disclaimers_items = [Paragraph("<b>DISCLAIMERS</b>", S["section_hdr"])]
    for i, disc in enumerate(RPL_DISCLAIMERS, 1):
        disclaimers_items.append(Paragraph(f"{i}.  {disc}", S["disc_item"]))
    elems.append(KeepTogether(disclaimers_items[:2]))  # heading + first item together
    elems.extend(disclaimers_items[2:])

    elems.append(Spacer(1, 4 * mm))
    sig_items = _signature_block(signatories, S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


# âââ Single-patient RPL layout ââââââââââââââââââââââââââââââââââââââââââââââââ

def _rpl_single_patient_table(patient: dict, S: dict) -> Table:
    """
    Unified 3-column patient + HLA table for the single RPL report.
    Mirrors the RPL couple table format (white background, black 0.5 pt grid)
    but contains only the patient â no donor columns.

    Column layout:
      col 0  label          24.6 % of CONTENT_W
      col 1  allele-1/val   37.7 %
      col 2  allele-2       37.7 %
    Demographic rows SPAN cols 1â2 so the value fills the whole right area.
    HLA rows use all three columns (label | allele1 | allele2).
    """
    cw = CONTENT_W
    _label_w = cw * 0.38                     # wider to fit "Relationship stated/ Claimed" on one line
    _data_w  = (cw * (1 - 0.246)) / 4       # same per-column width as the couple table
    col_w = [_label_w, _data_w, _data_w]    # total â 76 % of CONTENT_W

    def RL(t): return Paragraph(f"<b>{t}</b>", S["rpl_lbl"])
    def RV(t): return Paragraph(_title_case(_clean_display(t)), S["rpl_val"])
    def RR(t): return Paragraph(_clean_display(t), S["rpl_val"])
    _RAW_LABELS = {"PIN", "Sample Number"}
    def RVC(label, val): return RR(val) if label in _RAW_LABELS else RV(val)
    def HL(t): return Paragraph(f"<b>{t}</b>", S["rpl_hla_lbl"])
    def HV(t): return Paragraph(_clean_display(t), S["rpl_hla_val"])
    def E():   return Paragraph("", S["rpl_lbl"])

    data   = []
    spans  = []

    # ââ Demographic rows ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    demo_labels = [
        "Name", "Relationship stated/ Claimed", "Age/Gender",
        "Hospital MR No",
        "Diagnosis", "Referred By", "Hospital/Clinic",
        "PIN", "Sample Number", "Specimen",
        "Collection Date", "Sample receipt date", "Report date",
    ]
    demo_vals = [
        patient.get("name", ""),
        patient.get("relationship", "") or "NA",
        _normalize_age(patient.get("gender_age", "")),
        patient.get("hospital_mr_no", "") or "NA",
        patient.get("diagnosis") or "NA",
        patient.get("referred_by", ""),
        patient.get("hospital_clinic", ""),
        patient.get("pin", ""),
        patient.get("sample_number", ""),
        patient.get("specimen") or "Blood - EDTA",
        patient.get("collection_date", ""),
        patient.get("receipt_date", ""),
        patient.get("report_date", ""),
    ]

    for i, (lbl, val) in enumerate(zip(demo_labels, demo_vals)):
        data.append([RL(lbl), RVC(lbl, val), E()])
        spans.append(("SPAN", (1, i), (2, i)))

    hla_start = len(data)

    # ââ HLA rows ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    LOCI = ["A", "B", "C", "DRB1", "DQB1", "DPB1"]
    p_hla = patient.get("hla", {})
    for locus in LOCI:
        pa = p_hla.get(locus, [None, None])
        a1 = _strip_prefix(pa[0]) if pa and pa[0] else "â"
        a2 = _strip_prefix(pa[1]) if pa and len(pa) > 1 and pa[1] else "â"
        data.append([HL(f"HLA-{locus}*"), HV(a1), HV(a2)])

    t = Table(data, colWidths=col_w)
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, -1),              WHITE),
        ("TEXTCOLOR",     (0, 0), (-1, -1),  BLACK),
        ("GRID",          (0, 0), (-1, -1),  0.3, C_RPL_BORDER),
        ("ALIGN",         (0, 0), (-1, -1),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1),  4),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  4),
        # Left-align the label column
        ("ALIGN",         (0, 0), (0, -1),   "LEFT"),
        ("LEFTPADDING",   (0, 0), (0, -1),   6),
        # HLA allele columns centred (default)
        ("ALIGN",         (1, hla_start), (2, -1), "CENTER"),
    ]
    for sp in spans:
        style_cmds.append(sp)

    t.setStyle(TableStyle(style_cmds))
    return t


def _build_single_rpl(case: dict, S: dict) -> list:
    """
    single_rpl â Single RPL patient layout matching the reference PDF:
      Page 1: unified patient-info + HLA table (RPL style, no donor)
              + Reference section (Maternal HLA-C Type only)
      Page 1+: methodology + BACKGROUND + DISCLAIMERS + signatures
    """
    patient     = case["patient"]
    rpl_ref     = case.get("rpl_reference", {})
    signatories = case.get("signatories") or hla_assets.get_default_signatories(
        "single_rpl", case.get("nabl", True))

    elems = []

    # ââ Patient table â flows naturally (no KeepTogether so page 1 isn't forced off) ââ
    elems.append(_rpl_single_patient_table(patient, S))
    elems.append(Spacer(1, 3 * mm))

    # ââ Reference section â Maternal or Paternal HLA-C Type based on gender ââââ
    hla_c_p = rpl_ref.get("hla_c_patient", "")
    if not hla_c_p:
        pc = patient.get("hla", {}).get("C", [None, None])
        from hla_data_parser import c_supertype as _c_supertype
        ct1 = _c_supertype(pc[0]) if pc and pc[0] else None
        ct2 = _c_supertype(pc[1]) if pc and len(pc) > 1 and pc[1] else None
        hla_c_p = ", ".join(filter(None, [ct1, ct2]))

    _ga = (patient.get("gender_age", "") or "").lower()
    _is_male = "male" in _ga and "female" not in _ga
    _hla_c_lbl = "Paternal HLA-C Type" if _is_male else "Maternal HLA-C Type"

    if hla_c_p:
        c_data = [
            [Paragraph(f"<b>{_hla_c_lbl}</b>", S["rpl_lbl_center"])],
            [Paragraph(_clean_display(hla_c_p), S["rpl_val"])],
        ]
        c_t = Table(c_data, colWidths=[CONTENT_W * 0.40])
        c_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
            ("TEXTCOLOR",     (0, 0), (-1, -1), BLACK),
            ("GRID",          (0, 0), (-1, -1), 0.5, C_RPL_BORDER),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        # Keep the reference header and table together (won't split between them)
        elems.append(KeepTogether([
            Paragraph("<b>Reference:</b>", S["ref_hdr"]),
            c_t,
            Spacer(1, 3 * mm),
        ]))

    # ââ Page break: page 1 = patient table + reference only âââââââââââââââââ
    elems.append(PageBreak())

    # ââ Methodology + Background + Disclaimers + Signatures âââââââââââââââââââ
    methodology_items = _methodology_block(case, S)
    elems.extend(methodology_items)

    elems.append(Paragraph("<b>BACKGROUND</b>",      S["section_hdr"]))
    elems.append(Paragraph(SINGLE_RPL_BACKGROUND,    S["justify"]))
    elems.append(Spacer(1, 2 * mm))
    disclaimers_items = [Paragraph("<b>DISCLAIMERS</b>", S["section_hdr"])]
    for i, disc in enumerate(SINGLE_RPL_DISCLAIMERS, 1):
        disclaimers_items.append(Paragraph(f"{i}.  {disc}", S["disc_item"]))
    elems.append(KeepTogether(disclaimers_items[:2]))
    elems.extend(disclaimers_items[2:])

    elems.append(Spacer(1, 4 * mm))
    sig_items = _signature_block(signatories, S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


# âââ Single Locus (Luminex reverse SSO) report builder âââââââââââââââââââââââ

def _sl_info_table(patient: dict, S: dict) -> Table:
    """
    5-row, 6-column patient info table for Single Locus reports.
    Separates Gender and Age into distinct rows (unlike the combined NGS table).
    Column order: label | colon | value || label | colon | value
    """
    cw = CONTENT_W
    # Split combined gender_age â separate Gender / Age display
    _ga = _normalize_age(patient.get("gender_age", ""))
    if "/" in _ga:
        _parts = [p.strip() for p in _ga.split("/", 1)]
        _gender, _age = _parts[0], _parts[1]
    else:
        _gender, _age = _ga, ""

    # Wider right-label column to fit "Sample collection date"
    col_w = [cw * 0.190, cw * 0.025, cw * 0.285,
             cw * 0.260, cw * 0.025, cw * 0.215]

    def L(t): return Paragraph(f"<b>{t}</b>", S["lbl"])
    def C():  return Paragraph("<b>:</b>",     S["lbl"])
    def V(t): return Paragraph(_title_case(_clean_display(t)), S["val"])
    def R(t): return Paragraph(_clean_display(t), S["val"])

    rows = [
        [L("Patient name"),   C(), V(patient.get("name", "")),
         L("PIN"),                    C(), R(patient.get("pin", ""))],
        [L("Gender"),         C(), V(_gender),
         L("Sample Number"),          C(), R(patient.get("sample_number", ""))],
        [L("Age"),            C(), V(_age),
         L("Sample collection date"), C(), V(patient.get("collection_date", ""))],
        [L("Specimen"),       C(), R(patient.get("specimen") or "NA"),
         L("Sample receipt date"),    C(), V(patient.get("receipt_date", ""))],
        [L("Hospital/Clinic"), C(), V(patient.get("hospital_clinic", "")),
         L("Report date"),            C(), V(patient.get("report_date", ""))],
    ]

    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_INFO_BG),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (1, 0), (1, -1),  0),
        ("RIGHTPADDING",  (1, 0), (1, -1),  2),
        ("LEFTPADDING",   (4, 0), (4, -1),  0),
        ("RIGHTPADDING",  (4, 0), (4, -1),  2),
    ]))
    return t


def _build_single_locus(case: dict, S: dict) -> list:
    """
    Single-locus HLA typing report (Luminex reverse SSO method).
    Single-page layout:  Title â patient info â Method â Result table â Signatures.
    Result table has an orange header row (LOCUS | HLA-{locus}*), numbered allele
    rows, and an optional note row that spans both columns.
    """
    patient     = case.get("patient", {})
    nabl        = case.get("nabl", True)
    locus       = (case.get("locus", "") or "C").strip()
    allele1     = (case.get("sl_allele1", "") or "").strip()
    allele2     = (case.get("sl_allele2", "") or "").strip()
    sl_note     = (case.get("sl_note",    "") or "").strip()
    _rmk_display = _clean_display(patient.get("remarks", "")) or ""
    if _rmk_display == "â":
        _rmk_display = ""
    signatories = case.get("signatories") or hla_assets.get_default_signatories(
        "single_locus", nabl)

    F_BOLD = _f("Calibri-Bold", "Helvetica-Bold")
    F_REG  = _f("Calibri",      "Helvetica")

    C_SL_SEC  = colors.HexColor("#2C6BAA")   # blue section heading colour (matches approval line)

    _title_s = ParagraphStyle("_sl_title", fontName=F_BOLD, fontSize=20,
                               textColor=C_NGS_TITLE, alignment=TA_CENTER, leading=26)
    _hdr_s   = ParagraphStyle("_sl_hdr",   fontName=F_BOLD, fontSize=13,
                               textColor=C_SL_SEC, leading=16, spaceBefore=0, spaceAfter=0)
    _body_s  = ParagraphStyle("_sl_body",  fontName=F_REG,  fontSize=10,
                               textColor=BLACK, leading=13, alignment=TA_JUSTIFY, spaceAfter=1)
    _cell_s  = ParagraphStyle("_sl_cell",  fontName=F_BOLD, fontSize=11,
                               textColor=BLACK, leading=14, alignment=TA_CENTER)
    _val_s   = ParagraphStyle("_sl_val",   fontName=F_REG,  fontSize=11,
                               textColor=BLACK, leading=14, alignment=TA_CENTER)

    def _sec(text):
        return [
            Paragraph(f"<b>{text}</b>", _hdr_s),
            HRFlowable(width="100%", thickness=0.1, color=colors.grey),
            Spacer(1, 1 * mm),
        ]

    elems = []

    # ââ Title âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.append(Paragraph(f"<b>HLA-{locus}*</b>", _title_s))
    elems.append(Spacer(1, 1 * mm))

    # ââ Patient info â custom 5-row table with separate Gender / Age rows âââââ
    elems.append(_sl_info_table(patient, S))
    elems.append(Spacer(1, 1 * mm))

    # ââ Method ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.extend(_sec("Method"))
    for para_text in SINGLE_LOCUS_METHODOLOGY:
        elems.append(Paragraph(para_text, _body_s))
    elems.append(Spacer(1, 1 * mm))

    # ââ Result ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _result_heading = _sec("Result")

    _col_w = [CONTENT_W * 0.12, CONTENT_W * 0.25]   # total â 37 % of content, centred

    result_rows = [
        # Header row â orange background
        [Paragraph("<b>LOCUS</b>",          _cell_s),
         Paragraph(f"<b>HLA-{locus}*</b>", _cell_s)],
        # Allele rows
        [Paragraph("1", _val_s), Paragraph(_clean_display(allele1) or "â", _val_s)],
        [Paragraph("2", _val_s), Paragraph(_clean_display(allele2) or "â", _val_s)],
    ]
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0),   C_HLA_HDR),   # orange header
        ("BACKGROUND",    (0, 1), (-1, -1),  C_INFO_BG),
        ("TEXTCOLOR",     (0, 0), (-1, -1),  BLACK),
        ("INNERGRID",     (0, 0), (-1, -1),  0.25, WHITE),
        ("ALIGN",         (0, 0), (-1, -1),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1),  4),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  4),
    ]
    if sl_note:
        note_row_idx = len(result_rows)
        result_rows.append(
            [Paragraph(f"({_clean_display(sl_note)})", _val_s),
             Paragraph("", _val_s)]
        )
        style_cmds.append(("SPAN", (0, note_row_idx), (1, note_row_idx)))

    result_t = Table(result_rows, colWidths=_col_w)
    result_t.hAlign = "CENTER"
    result_t.setStyle(TableStyle(style_cmds))

    # ââ Remarks (optional) ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    remarks_items = []
    if _rmk_display:
        remarks_items = [
            Spacer(1, 2 * mm),
            Paragraph(f"<b>Remarks:</b> {_rmk_display}", _body_s),
        ]

    # ââ Result heading + table + remarks + signatures kept together as one unit
    # so the "Result" heading never gets orphaned on page 1 while the table and
    # signatures spill onto page 2 â they all move together if they don't fit.
    sig_items = _signature_block(signatories, S)
    elems.append(KeepTogether(
        _result_heading + [result_t] + remarks_items + [Spacer(1, 1 * mm)] + (sig_items or [])
    ))

    return elems


# âââ HLA-C (fixed-locus, two-page) report builder ââââââââââââââââââââââââââââ

def _build_hla_c(case: dict, S: dict) -> list:
    """
    HLA-C report â fixed-locus layout matching the reference PDF:
    Title â patient info â Test Details â Typing Result â Remarks â
    [page break] â Disclaimer â Reference â Signatures.
    """
    patient     = case.get("patient", {})
    nabl        = case.get("nabl", True)
    allele1     = (case.get("hlac_allele1", "") or "").strip()
    allele2     = (case.get("hlac_allele2", "") or "").strip()
    remark      = (case.get("hlac_remark",  "") or "").strip()
    signatories = case.get("signatories") or hla_assets.get_default_signatories(
        "hla_c", nabl)

    # POC (Products of Conception) samples use a simplified Result layout â
    # a single Name/Type table instead of the allele-typing + Remarks tables.
    is_poc = "poc" in (patient.get("specimen", "") or "").lower()

    # Remarks label follows the patient's sex â Paternal for male, Maternal otherwise.
    _gender_part = _normalize_age(patient.get("gender_age", "")).split("/", 1)[0].strip().lower()
    _parent_label = "Paternal" if _gender_part.startswith("m") else "Maternal"

    F_BOLD = _f("Calibri-Bold", "Helvetica-Bold")
    F_REG  = _f("Calibri",      "Helvetica")

    C_HC_SEC = colors.HexColor("#2C6BAA")   # blue section heading colour

    _title_s = ParagraphStyle("_hc_title", fontName=F_BOLD, fontSize=20,
                               textColor=C_NGS_TITLE, alignment=TA_CENTER, leading=26)
    _hdr_s   = ParagraphStyle("_hc_hdr",   fontName=F_BOLD, fontSize=13,
                               textColor=C_HC_SEC, leading=16, spaceBefore=2, spaceAfter=0)
    _body_s  = ParagraphStyle("_hc_body",  fontName=F_REG,  fontSize=11,
                               textColor=BLACK, leading=14, alignment=TA_JUSTIFY, spaceAfter=2)
    _lbl_l_s = ParagraphStyle("_hc_lbl_l", fontName=F_BOLD, fontSize=11,
                               textColor=BLACK, leading=14, alignment=TA_LEFT)
    _val_c_s = ParagraphStyle("_hc_val_c", fontName=F_REG,  fontSize=11,
                               textColor=BLACK, leading=14, alignment=TA_CENTER)
    _ref_s   = ParagraphStyle("_hc_ref",   fontName=F_REG,  fontSize=9.5,
                               textColor=BLACK, leading=12.5, alignment=TA_JUSTIFY, spaceAfter=2)

    def _sec(text):
        return [
            Paragraph(f"<b>{text}</b>", _hdr_s),
            HRFlowable(width="100%", thickness=0.1, color=colors.grey),
            Spacer(1, 1 * mm),
        ]

    elems = []

    # ââ Title âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.append(Paragraph("<b>HLA-C*</b>", _title_s))
    elems.append(Spacer(1, 2 * mm))

    # ââ Patient info â reuse the Single Locus 5-row demography table ââââââââââ
    elems.append(_sl_info_table(patient, S))
    elems.append(Spacer(1, 2 * mm))

    # ââ Test Details âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.extend(_sec("Test Details"))
    for para_text in HLA_C_METHODOLOGY:
        elems.append(Paragraph(para_text, _body_s))
    elems.append(Spacer(1, 2 * mm))

    if is_poc:
        # ââ Result (POC layout) â combined Name / POC HLA-C Type table âââââââââ
        elems.extend(_sec("Result"))
        elems.append(Spacer(1, 3 * mm))

        _poc_name = _clean_display(_title_case(patient.get("name", "")))
        _poc_name_val = f"POC of {_poc_name}" if _poc_name else "â"
        _col_w = [CONTENT_W * 0.20, CONTENT_W * 0.30]

        result_rows = [
            [Paragraph("<b>Name</b>", _val_c_s),
             Paragraph(_poc_name_val, _val_c_s)],
            [Paragraph("<b>POC HLA-C<br/>Type</b>", _val_c_s),
             Paragraph(_clean_display(remark) or "â", _val_c_s)],
        ]
        result_t = Table(result_rows, colWidths=_col_w)
        result_t.hAlign = "CENTER"
        result_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elems.append(result_t)
    else:
        # ââ Typing Result ââââââââââââââââââââââââââââââââââââââââââââââââââââ
        elems.extend(_sec("Typing Result"))
        elems.append(Spacer(1, 3 * mm))

        _col_w = [CONTENT_W * 0.18, CONTENT_W * 0.18, CONTENT_W * 0.18]

        result_rows = [
            [Paragraph("Name", _lbl_l_s),
             Paragraph(_clean_display(_title_case(patient.get("name", ""))) or "â", _val_c_s),
             ""],
            [Paragraph("<b>HLA-C*</b>", _lbl_l_s),
             Paragraph(_clean_display(allele1) or "â", _val_c_s),
             Paragraph(_clean_display(allele2) or "â", _val_c_s)],
        ]
        result_t = Table(result_rows, colWidths=_col_w)
        result_t.hAlign = "CENTER"
        result_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("SPAN",          (1, 0), (2, 0)),
        ]))
        elems.append(result_t)
        elems.append(Spacer(1, 2 * mm))

        # ââ Remarks ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
        # Structural field (Maternal/Paternal HLA-C Type), not free-text
        # commentary â always shown for the Peripheral Blood layout, with a
        # "â" placeholder when empty, matching the desktop app exactly.
        elems.extend(_sec("Remarks"))
        elems.append(Spacer(1, 3 * mm))

        _rem_w = [CONTENT_W * 0.40]
        rem_t = Table([
            [Paragraph(f"<b>{_parent_label} HLA-C Type</b>", _val_c_s)],
            [Paragraph(remark or "â", _val_c_s)],
        ], colWidths=_rem_w)
        rem_t.hAlign = "CENTER"
        rem_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elems.append(rem_t)

    # ââ Disclaimer + Reference + Signatures âââââââââââââââââââââââââââââââââ
    # Typing Result + Remarks is short enough to leave plenty of room on
    # page 1 â let Disclaimer flow naturally instead of forcing a page break;
    # it only spills to page 2 if content genuinely doesn't fit. Heading and
    # body are kept together so the heading never gets orphaned on page 1
    # while its (short) text gets pushed alone onto page 2.
    elems.append(Spacer(1, 4 * mm))
    elems.append(KeepTogether(
        _sec("Disclaimer") + [Paragraph(HLA_C_DISCLAIMER, _body_s)]
    ))
    elems.append(Spacer(1, 2 * mm))

    elems.extend(_sec("Reference"))
    for ref_text in HLA_C_REFERENCES:
        elems.append(Paragraph(ref_text, _ref_s))
    elems.append(Spacer(1, 4 * mm))

    sig_items = _signature_block(signatories, S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


# âââ Accurate page-count canvas (Fix 4) ââââââââââââââââââââââââââââââââââââââ

def _make_numbered_canvas_class(hf_instance):
    """
    Return a canvasmaker class that performs a single-pass two-phase render:
      Phase 1 (showPage calls): record each page's canvas state.
      Phase 2 (save):          replay each page, drawing header/footer with the
                               now-known total page count before writing to PDF.

    This eliminates the need for an upfront page-count estimate and ensures
    "Page X of N" always shows the real N (Fix 4).
    """
    from reportlab.pdfgen import canvas as _pdfcanvas

    class _NumberedCanvas(_pdfcanvas.Canvas):
        def __init__(self, filename, **kwargs):
            _pdfcanvas.Canvas.__init__(self, filename, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            # Snapshot current canvas state before advancing to next page
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total_pages = len(self._saved_page_states)
            hf_instance.total_pages = total_pages          # update to real count
            for state in self._saved_page_states:
                self.__dict__.update(state)                # restore page state
                page_num = self._pageNumber
                # Minimal stand-in for the doc object expected by _HFCanvas.__call__
                class _FakeDoc:
                    pass
                _FakeDoc.page = page_num
                hf_instance(self, _FakeDoc())              # draw header/footer
                _pdfcanvas.Canvas.showPage(self)           # finalise page
            _pdfcanvas.Canvas.save(self)

    return _NumberedCanvas


# âââ CDC Cross match report builder ââââââââââââââââââââââââââââââââââââââââââ

CDC_COMMENTS = [
    "Positive crossmatch is contraindicated in solid organ transplantation.",
    "The test should be performed within one week before transplantation.",
    "The test is AHG augmented, which increases the sensitivity of the test.",
    "Test performed with incubation of 37Â°C.",
    "The test is done with DTT and without DTT treatment of the recipient's serum. "
    "This step differentiates the presence of IgM antibody from IgG antibody.",
]


DSA_COMMENTS = [
    "DSA crossmatch is a lysate based crossmatch done by LuminexXmap technology.",
    "The assay detects only Anti HLA antibodies against HLA Class I and HLA Class II.",
    "The presence of DSA may lead to acute, hyperacute or chronic antibody mediated rejection of solid organs or bone marrow transplants.",
    "Results must be correlated clinically and with other antibody detection tests.",
    "PRA screening is another useful adjunct to detect reactivity against Anti DQB1 and Anti HLA C.",
    "Patients develop anti HLA antibodies by sensitization through prior transplant, blood transfusion(s), infections, and pregnancy.",
]
DSA_RECOMMENDATIONS = [
    "It is strongly recommended to correlate the result in the context of clinical findings, and other laboratory data to arrive at accurate diagnosis, prognosis or for therapeutic decision.",
    "The test results relate specifically to the sample received in the lab and are presumed to have been generated and transported per specific instructions given by the physicians/laboratory",
]

# âââ SAB static text âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
SAB_METHODOLOGY = (
    "The test is based on the Luminex technology. The Single Antigen Class I "
    "/Class II beads are designed to detect IgG antibodies to HLA Class I "
    "/Class II glycoproteins. The SAB Class I /Class II are composed of "
    "different Luminex Beads to which purified recombinant Class I /Class II "
    "HLA glycoproteins are conjugated. The presence or absence of antibodies "
    "in the sera depends on the antigen/antibody binding on these beads that "
    "is detected by the Luminex optic system."
)
SAB_INTERPRETATION = (
    "The level of antibody is measured as a Mean Fluorescent Intensity (MFI), "
    "and if MFI is >= 1000 is considered as significant."
)
SAB_COMMENTS_LIST = [
    "MFI for individual alleles are attached in the appendix section.",
    "This test detects anti-HLA IgG antibodies sensitization status & differentiates "
    "between Donor specific antibodies and non-donor specific antibodies.",
    "The test is important to detect anti HLA antibodies in potential recipients "
    "pre and post transplantation",
]
SAB_LIMITATIONS = [
    "The reported results are for information and are subject to confirmation and "
    "interpretation by the referring doctor.",
    "The tests results relate specifically to the sample received in the lab and are "
    "presumed to have been generated and transported per specific instructions given "
    "by the physicians/laboratory.",
    "The test results are not to be considered as diagnosis of any diseases. These "
    "findings are meant to aid the clinician in taking a vital healthcare decision "
    "and serve as a guide for providing the appropriate treatment.",
]

# ââ KIR Genotyping constants ââââââââââââââââââââââââââââââââââââââââââââââââââ
KIR_GENES = [
    "2DL1", "2DL2", "2DL3", "2DL4", "2DL5",
    "2DS1", "2DS2", "2DS3", "2DS4", "2DS5",
    "3DL1", "3DL2", "3DL3", "3DS1", "2DP1", "3DP1",
]
# Genes whose presence indicates a B haplotype
KIR_B_GENES = {"2DL2", "2DL5", "2DS1", "2DS2", "2DS3", "2DS5", "3DS1"}

KIR_METHOD = (
    "KIR genotyping is a genetic test that allows the <b>maternal killer immune-globulin-like "
    "receptor (KIR)</b> gene repertoire of a patient to be determined. Through a PCR-SSP analysis "
    "of 16 KIR genes (2DL1, 2DL2, 2DL3, 2DL4, 2DL5, 2DS1, 2DS2, 2DS3, 2DS4, 2DS5, 3DL1, 3DL2, "
    "3DL3, 3DS1, 2DP1 and 3DP1) it is possible to establish KIR genotype for a particular patient "
    "and hence the risks of an altered maternal immune response to the embryo."
)
KIR_TEST_DETAILS = (
    "KIR Typing by Luminex technology applies SSO DNA typing method. Target DNA is PCR-amplified "
    "using a group-specific primer and the PCR product is biotinylated, which allows it to be "
    "detected using R-Phycoerythrin conjugated Streptavidin (SAPE).\n"
    "The PCR product is denatured and allowed to rehybridize complementary DNA probes conjugated "
    "to fluorescently coded microspheres. A flow analyzer identifies the fluorescent intensity of "
    "PE (phycoerythrin) on each microsphere."
)
KIR_FOOTNOTE = (
    "*If any gene 2DL2, 2DL5, 2DS1, 2DS2, 2DS3, 2DS5, and 3DS1 is present, genotype is taken "
    "as having B."
)
C_KIR_HEADING = colors.HexColor("#1F3864")   # dark navy for KIR section headings


def _kir_calc_genotype(genes: dict) -> str:
    """Return 'AA' or 'AB' based on presence of B-specific KIR genes."""
    return "AB" if any(genes.get(g, "-") == "+" for g in KIR_B_GENES) else "AA"


# The closing disclaimer is constant for every KIR report; only the opening
# "KIR <genotype> was detected â¦" line varies with the genotype.
KIR_INTERP_DISCLAIMER = (
    "KIR AB or BB genotypes have not been associated with implantation failure or pregnancy "
    "complications due to an altered maternal immune response."
)


def _kir_interp_first_line(genotype: str) -> str:
    return f"KIR {genotype} was detected in the sample analysed."


def _kir_auto_interp(genotype: str) -> str:
    return f"{_kir_interp_first_line(genotype)}\n\n{KIR_INTERP_DISCLAIMER}"

SAB_NOTE = (
    "List of allele specificities included in the panel tested are given in the table attached."
)

# âââ Flow Cytometry static text ââââââââââââââââââââââââââââââââââââââââââââââ
FLOW_COMMENTS = [
    "The flow cytometry crossmatching is used for detection of even very low "
    "concentrations of preformed antibodies present in the patient serum to "
    "the donor lymphocytes.",
    "Flow Cytometry cross matching is more reliable than the CDC cross matching "
    "as it is not complement dependent like CDC testing and it specifically "
    "detects T and B cells binding with IgG alloantibodies, reducing the "
    "background binding with NK cells and Monocytes. The test detects both "
    "complement and non-complement binding anti HLA class I and II IgG antibodies.",
    "In patients undergoing dialysis the sample needs to be collected after three "
    "days of last dialysis. Crossmatching samples need to be collected after three "
    "weeks of any blood transfusion, in case of a recent blood transfusion history.",
    "The results are expressed as positive/negative based on the Median channel "
    "shift of the test serum with respect to the Negative control.",
    "A positive flow cross match suggests increased risk of allograft rejection "
    "but is not a Contraindication for transplantation.",
    "A negative crossmatch does not imply that the donor and the patient are related.",
]
FLOW_DISCLAIMER = [
    "The tests are carried out in the lab with the presumption that the specimen "
    "belongs to the patient named or identified in the bill/test request form.",
    "The results relate specificity to the sample received in the lab and a "
    "presumed to have been generated and transported per specific instructions "
    "given by the physicians/laboratory.",
]

# âââ Luminex SSO static text âââââââââââââââââââââââââââââââââââââââââââââââââ
LUMINEX_TEST_DETAILS = [
    "HLA Typing by Luminex technology applies SSO DNA typing method. Target DNA is "
    "PCR-amplified using a group-specific primer and the PCR product is biotinylated, "
    "which allows it to be detected using R-Phycoerythrin conjugated Streptavidin (SAPE).",
    "The PCR product is denatured and allowed to rehybridize complementary DNA probes "
    "conjugated to fluorescently coded microspheres. A flow analyzer identifies the "
    "fluorescent intensity of PE (phycoerythrin) on each microsphere. The assignment of "
    "the HLA typing is based on the reaction pattern compared to patterns associated with "
    "published HLA gene sequences.",
    "The number of nucleotide mismatches with each allele is determined, as well as the "
    "number of mismatches with the determined phasing data. Mismatches at exons are "
    "treated separately. A list of alleles is selected with a limited number of mismatches.",
]
LUMINEX_DISCLAIMER = (
    "The occurrence of HLA typing results and the number of different allele combinations "
    "by a SSO method for an individual may change according to the version of the IMGT/HLA "
    "database."
)
LUMINEX_REFERENCES = [
    "Terasaki, PI, Bernoco, F, Park MS, Ozturk G, Iwaki Y. Microdroplet testing for "
    "HLA-A, -B, -C, and âD antigens. American Journal of Clinical Pathology "
    "69:103-120, 1978.",
    "Slater RD, Parham P. Mutually exclusive public epitomes of HLA-A, B, C Molecules. "
    "Human Immunology 26: 85-89, 1989.",
    "The LuminexÂ® 100 User's Manual, Luminex Corporation, PN 89-00002-00-005 Rev. B.",
    "LuminexÂ® FLEXMAP 3DÂ® Hardware User Manual, Luminex Corporation "
    "PN 89-00002-00-187.",
    "Ng J, Hurley CK, Baxter-Lowe LA, et al. Large-scale oligonucleotide typing for "
    "HLA-DRB1/3/4 and HLA-DQB1 is highly accurate, specific, and reliable. Tissue "
    "Antigens. 1993; 42: 473-479.",
    "Bodmer JG, Marsh SGE, Albert E, Bodmer WF, Bontrop RE, Dupont B, Erlich HA, "
    "Hansen JA, Mach B, Mayr WR, Parham P, Petersdorf EW, Sasasuki T, Schreuder GMT, "
    "Strominger JL, Svejgaard A, Terasaki PI. Nomenclature for factors of the HLA system, "
    "1998. Tissue Antigens, 53, 407-446, 1999. Human Immunology, 60, 361-395, 1999. "
    "European Journal of Immunogenetics, 26, 81-116, 1999.",
    "Colinas RJ, Bellisario R et al. Multiplexed genotyping of beta-globin variants from "
    "PCR-amplified newborn blood spot DNA by hybridization with allele-specific oligo "
    "deoxynucleotides coupled to an array of fluorescent microspheres. Clinical Chemistry "
    "46: 996-998, 2000.",
]


# âââ PRA (Panel Reactive Antibodies) report content ââââââââââââââââââââââââââ
PRA_METHODOLOGY = "Luminex Xmap Technology"
PRA_INTERP_ROWS = [
    ("<4%",       "Negative"),
    ("4%-10%",    "Weak Positive"),
    ("11%-50%",   "Moderate Positive"),
    ("50% above", "Strong Positive"),
]
PRA_COMMENTS = [
    "The percentage positivity of this test reveals the sensitization of HLA antigen "
    "prevalent in the general population.",
    "PRA in excess of 15% indicates that a patient may have developed an anti-HLA "
    "antibody and is therefore considered sensitized [1].",
    "The test is of immense importance for monitoring immunosuppression and grading "
    "the antigens where sensitization has occurred.",
    "The results may be deceptive if the recipient has undergone multiple transplants, "
    "transfusions, and pregnancies/abortions.",
    "It has been observed that Anti Thymocyte Globulin treatment can lead to false "
    "positive result [2].",
]
PRA_RECOMMENDATIONS = [
    "It is strongly recommended to correlate the result in the context of clinical "
    "findings, and other laboratory data to arrive at accurate diagnosis, prognosis or "
    "for therapeutic decision.",
    "The test results relate specifically to the sample received in the lab and are "
    "presumed to have been generated and transported per specific instructions given by "
    "the physicians/laboratory",
]
PRA_REFERENCES = [
    "Michael D.Gautreaux; Chapter 17 - Histocompatibility Testing in the Transplant "
    "Setting; Kidney Transplantation, Bioengineering and Regeneration (2017):223-234",
    "Gloor JM, Moore SB, Schneider BA, Degoey SR, Stegall MD. The effect of "
    "antithymocyte globulin onanti-human leukocyte antigen antibody detection assays. "
    "Transplantation. 2007;84(2)",
]


def pra_result_for(pct) -> str:
    """Classify a PRA percentage into its qualitative band (per PRA_INTERP_ROWS)."""
    try:
        v = float(str(pct).replace("%", "").strip())
    except (ValueError, TypeError):
        return ""
    if v < 4:   return "Negative"
    if v <= 10: return "Weak Positive"
    if v <= 50: return "Moderate Positive"
    return "Strong Positive"


# âââ Flow Cytometry Cross match report builder ââââââââââââââââââââââââââââââââ

def _cdc_result_color(val: str):
    """Return the display color for a CDC/DSA result string."""
    v = val.strip().lower()
    if "negative" in v: return C_CDC_NEG
    return C_CDC_POS


def _build_cdc_report(case: dict, S: dict) -> list:
    """Return story flowables for CDC Cross match report (2 pages)."""

    patient = case.get("patient", {})
    donors  = case.get("donors", [])
    donor   = donors[0] if donors else {}
    cdc     = case.get("cdc_results", {})

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")

    def _P(text, font=F_BOLD, size=10, color=BLACK, align=TA_LEFT, leading=None):
        return Paragraph(text, ParagraphStyle("_cdc", fontName=font, fontSize=size,
            textColor=color, alignment=align, leading=leading or size + 2))

    def _clean(val):
        s = str(val).strip() if val else ""
        return s if s and s.lower() not in ("nan", "none", "") else "NA"

    def _norm(val):
        """Title-case for names/text; 'NA' fallback for empty."""
        return _title_case(_clean_display(val)) or "NA"

    # Name/place fields (patient/donor name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def _norm_name(val):
        return _title_case(_clean_display(val), is_name=True) or "NA"

    def _raw(val):
        """No case change Ã¢â¬" for PIN, sample numbers, dates."""
        return _clean_display(val) or "NA"

    def _color_hex(c):
        """Return 6-char hex string for a reportlab color."""
        try:
            return "%02x%02x%02x" % (
                int(round(c.red * 255)),
                int(round(c.green * 255)),
                int(round(c.blue * 255)),
            )
        except Exception:
            return "000000"

    elems = []

    # Ã¢"â¬Ã¢"â¬ Info table Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    info_lbl_style = ParagraphStyle("_cdc_lbl", fontName=F_BOLD, fontSize=10,
                                    textColor=BLACK, leading=12)
    info_val_style = ParagraphStyle("_cdc_val", fontName=F_BOLD, fontSize=10,
                                    textColor=BLACK, leading=12)

    def IL(t): return Paragraph(f"<b>{t}</b>", info_lbl_style)
    def IV(t): return Paragraph(_norm(t),  info_val_style)   # title-case text fields
    def IR(t): return Paragraph(_raw(t),   info_val_style)   # raw: PIN / dates / sample no
    def IC():  return Paragraph("<b>:</b>", info_lbl_style)

    # 7-col layout: [lbl_L, colon_L, val_L, GAP, lbl_R, colon_R, val_R]
    # Column widths are computed per-report: the donor value column is sized to
    # just fit its (usually short) values and all leftover width goes to the
    # patient value column, so a long Hospital/Clinic name renders at full font.
    cw = CONTENT_W
    info_col_w = _demography_col_widths(patient, donor)

    def E(): return Paragraph("", info_lbl_style)

    def IV_name(text, col_w_pts):
        return Paragraph(_norm_name(text), info_val_style)

    info_rows = [
        [IL("Patient name"),    IC(), IV_name(patient.get("name",""), info_col_w[2]), E(), IL("Donor name"),          IC(), IV_name(donor.get("name",""), info_col_w[6])],
        [IL("Gender/ Age"),     IC(), IR(_normalize_age(patient.get("gender_age",""))),      E(), IL("Gender/ Age"),         IC(), IR(_normalize_age(donor.get("gender_age","")))],
        [IL("PIN"),             IC(), IR(patient.get("pin","")),             E(), IL("PIN"),                 IC(), IR(donor.get("pin","NA"))],
        [IL("Sample Number"),   IC(), IR(patient.get("sample_number","")),   E(), IL("Sample Number"),       IC(), IR(donor.get("sample_number","NA"))],
        [IL("Diagnosis"),       IC(), IV(patient.get("diagnosis","")),       E(), IL("Sample receipt date"), IC(), IR(donor.get("receipt_date",""))],
        # Hospital/Clinic value renders at full font; a long name wraps onto an
        # extra line (see _fit_one_line) and the row grows taller rather than the
        # text being shrunk to fit a single line.
        [IL("Hospital/Clinic"), IC(), _fit_one_line(_norm_name(patient.get("hospital_clinic","")), info_col_w[2], info_val_style), E(), IL("Report date"), IC(), IR(donor.get("report_date",""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_INFO_BG),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (1, 0), (1, -1), 0),
        ("RIGHTPADDING",  (1, 0), (1, -1), 2),
        ("LEFTPADDING",   (3, 0), (3, -1), 0),
        ("RIGHTPADDING",  (3, 0), (3, -1), 0),
        ("LEFTPADDING",   (5, 0), (5, -1), 0),
        ("RIGHTPADDING",  (5, 0), (5, -1), 2),
        # no bottom border â demography table sits flush above the photo table
    ]))
    elems.append(info_t)
    elems.append(Spacer(1, 1 * mm))

    # Ã¢"â¬Ã¢"â¬ Photo / sample-type table Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    # Sized to fit "Sodium Heparin Whole Blood" (131pt) on one line so the
    # Sample type row stays single-line Ã¢â ' less vertical height.
    # Photo height reduced to 30mm to keep the table compact.
    _ph_w   = 28 * mm   # passport photo display width
    _ph_h   = 30 * mm   # reduced height Ã¢â¬" keeps table short
    _pc_w   = 54 * mm   # avail Ã¢â°Ë 141pt Ã¢â¬" fits "Sodium Heparin Whole Blood" (131pt)
    _lbl_w  = 38 * mm   # label column Ã¢â¬" fits "Date of Collection"
    col_w_photo = [_lbl_w, _pc_w, _pc_w]

    def _photo_cell(photo_bytes):
        if photo_bytes:
            try:
                return Image(io.BytesIO(photo_bytes), width=_ph_w, height=_ph_h)
            except Exception:
                pass
        return Spacer(1, _ph_h)

    pat_photo = _photo_cell(patient.get("photo_bytes"))
    don_photo = _photo_cell(donor.get("photo_bytes"))

    p_sample_type = _clean(patient.get("sample_type", "Serum"))
    d_sample_type = _clean(donor.get("sample_type", "Sodium Heparin Whole Blood"))
    p_collect     = _clean(patient.get("collection_date", ""))
    d_collect     = _clean(donor.get("collection_date", ""))

    _GREY = C_INFO_BG

    photo_rows = [
        # Row 1: header Ã¢â¬" empty | PATIENT DETAILS | DONOR DETAILS
        [Paragraph("", info_lbl_style),
         _P("PATIENT DETAILS", F_BOLD, 11, BLACK, TA_CENTER),
         _P("DONOR DETAILS",   F_BOLD, 11, BLACK, TA_CENTER)],
        # Row 2: Photo (bold, left+middle) | passport photo | passport photo
        [_P("Photo", F_BOLD, 10, BLACK, TA_LEFT), pat_photo, don_photo],
        # Row 3: Sample type (regular weight)
        [_P("Sample type",        F_REG, 10, BLACK, TA_LEFT),
         _P(p_sample_type,        F_REG, 10, BLACK, TA_CENTER),
         _P(d_sample_type,        F_REG, 10, BLACK, TA_CENTER)],
        # Row 4: Date of Collection (regular weight)
        [_P("Date of Collection", F_REG, 10, BLACK, TA_LEFT),
         _P(p_collect,            F_REG, 10, BLACK, TA_CENTER),
         _P(d_collect,            F_REG, 10, BLACK, TA_CENTER)],
    ]
    photo_t = Table(photo_rows, colWidths=col_w_photo)
    photo_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _GREY),          # light grey Ã¢â¬" whole table
        ("BOX",           (0, 0), (-1, -1), 1.0, colors.white),   # thin white outer border
        ("INNERGRID",     (0, 0), (-1, -1), 1.0, colors.white),   # thin white inner grid
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (0, -1),  "LEFT"),          # label column: left
        ("ALIGN",         (1, 0), (2, -1),  "CENTER"),        # photo columns: centered
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        # Photo row height
        ("MINROWHEIGHT",  (0, 1), (-1, 1),  _ph_h + 4 * mm),
    ]))
    photo_t.hAlign = 'CENTER'
    elems.append(photo_t)
    elems.append(Spacer(1, 1 * mm))

    # Ã¢"â¬Ã¢"â¬ Relationship box Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    rel_text = _clean(donor.get("relationship", ""))
    rel_para = Paragraph(
        f"<b>Relationship Of The Donor With Recipient:</b> {rel_text}",
        ParagraphStyle("_rel", fontName=F_BOLD, fontSize=10, textColor=BLACK,
                        alignment=TA_CENTER, leading=14)
    )
    rel_t = Table([[rel_para]], colWidths=[CONTENT_W])
    rel_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_CDC_REL_BG),
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#F0AD4E")),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    elems.append(rel_t)
    elems.append(Spacer(1, 2 * mm))

    # Ã¢"â¬Ã¢"â¬ Result section Ã¢â¬" kept together so DTT table never splits from its header Ã¢"â¬
    _C_RES_HDR = C_NGS_TITLE
    t_result = cdc.get("t_cell", "Negative")
    b_result = cdc.get("b_cell", "Negative")
    t_color_hex = _color_hex(_cdc_result_color(t_result))
    b_color_hex = _color_hex(_cdc_result_color(b_result))

    def _dtt_label(key, default="<10% Dead"):
        v = cdc.get(key, "").strip()
        v = re.sub(r"\s*cells\s*$", "", v, flags=re.IGNORECASE).strip()
        return v or default

    t_dtt_label = _dtt_label("t_with_dtt")
    b_dtt_label = _dtt_label("b_with_dtt")

    _res_style = ParagraphStyle("_rline", fontName=F_BOLD, fontSize=10, leading=14)

    _dtt_total  = CONTENT_W * 0.70
    _dtt_col_w  = [_dtt_total * 0.26, _dtt_total * 0.37, _dtt_total * 0.37]
    _dtt_hdr_bg = colors.HexColor("#FABF8F")

    dtt_hdr_s = ParagraphStyle("_dtt_h", fontName=F_BOLD, fontSize=10,
                                textColor=BLACK, alignment=TA_CENTER, leading=13)
    dtt_val_s = ParagraphStyle("_dtt_v", fontName=F_REG,  fontSize=10,
                                textColor=BLACK, alignment=TA_CENTER, leading=13)
    dtt_lbl_s = ParagraphStyle("_dtt_l", fontName=F_BOLD, fontSize=10,
                                textColor=BLACK, alignment=TA_CENTER, leading=13)

    _cdc_rmk = patient.get("remarks", "").strip()
    _cdc_donor_rmk = (donor.get("remarks", "") or "").strip()
    _row_pad  = 4 if (_cdc_rmk or _cdc_donor_rmk) else 3

    dtt_t = Table([
        [Paragraph("<b>Cells</b>",                dtt_hdr_s),
         Paragraph("<b>With DTT Treatment</b>",    dtt_hdr_s),
         Paragraph("<b>Without DTT Treatment</b>", dtt_hdr_s)],
        [Paragraph("T Cells", dtt_lbl_s),
         Paragraph(cdc.get("t_with_dtt",    "<10% Dead cells"), dtt_val_s),
         Paragraph(cdc.get("t_without_dtt", "<10% Dead cells"), dtt_val_s)],
        [Paragraph("B Cells", dtt_lbl_s),
         Paragraph(cdc.get("b_with_dtt",    "<10% Dead cells"), dtt_val_s),
         Paragraph(cdc.get("b_without_dtt", "<10% Dead cells"), dtt_val_s)],
    ], colWidths=_dtt_col_w)
    dtt_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  _dtt_hdr_bg),
        ("BACKGROUND",    (0, 1), (-1, -1), colors.HexColor("#E8E8E8")),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, colors.white),
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.white),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), _row_pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), _row_pad),
    ]))
    dtt_t.hAlign = 'CENTER'

    _cdc_rmk_items = ([
        Paragraph(
            f"<b>Remarks : </b>{_clean_display(_cdc_rmk)}",
            ParagraphStyle("_cdc_rmk2", fontName=F_BOLD, fontSize=10,
                           leading=14, spaceBefore=4, spaceAfter=4)
        )
    ] if _cdc_rmk else [])
    if _cdc_donor_rmk:
        _cdc_rmk_items.append(Paragraph(
            f"<b>Donor Remarks : </b>{_clean_display(_cdc_donor_rmk)}",
            ParagraphStyle("_cdc_drmk", fontName=F_BOLD, fontSize=10,
                           leading=14, spaceBefore=4, spaceAfter=4)
        ))

    elems.append(KeepTogether([
        Paragraph("<b>Result</b>", ParagraphStyle("_cdc_sec",
            fontName=F_BOLD, fontSize=14, textColor=_C_RES_HDR, leading=18,
            spaceAfter=(2 if not _cdc_rmk else 2))),
        HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=3),
        Paragraph(
            f"<b>T cell crossmatch : </b><font color='#{t_color_hex}'><b>{t_result}</b></font>"
            f" <font color='#000000'>({t_dtt_label})</font>", _res_style),
        Paragraph(
            f"<b>B cell crossmatch : </b><font color='#{b_color_hex}'><b>{b_result}</b></font>"
            f" <font color='#000000'>({b_dtt_label})</font>", _res_style),
    ] + _cdc_rmk_items + [
        Spacer(1, 1 * mm),
        dtt_t,
    ]))

    # Ã¢"â¬Ã¢"â¬ Page break Ã¢â ' page 2 Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(PageBreak())

    # Ã¢"â¬Ã¢"â¬ Interpretation Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    _sec_style = ParagraphStyle("_cdc_sec_hdr", fontName=F_BOLD, fontSize=14,
                                 textColor=C_NGS_TITLE, leading=18, spaceAfter=2)

    elems.append(Paragraph("<b>Interpretation</b>", _sec_style))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey,
                             spaceAfter=8))

    _i_hdr = ParagraphStyle("_ih", fontName=F_BOLD, fontSize=10,
                              textColor=BLACK, alignment=TA_CENTER, leading=13)
    _i_val = ParagraphStyle("_iv", fontName=F_REG,  fontSize=10,
                              textColor=BLACK, alignment=TA_CENTER, leading=14)
    _i_cw  = [CONTENT_W * 0.30, CONTENT_W * 0.28]   # total Ã¢â°Ë 58%, centered

    interp_data = [
        [Paragraph("<b>Percentage of dead cells</b>", _i_hdr),
         Paragraph("<b>Results</b>",                  _i_hdr)],
        [Paragraph("0- 10 %",   _i_val), Paragraph("Negative",       _i_val)],
        [Paragraph("10%-20%",   _i_val), Paragraph("Doubtful",        _i_val)],
        [Paragraph("20%-50%",   _i_val), Paragraph("Weak Positive",   _i_val)],
        [Paragraph("50-80%",    _i_val), Paragraph("Positive",        _i_val)],
        [Paragraph(">80%",      _i_val), Paragraph("Strong Positive", _i_val)],
    ]
    interp_t = Table(interp_data, colWidths=_i_cw, hAlign="CENTER")
    interp_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#FABF8F")),  # orange header
        ("BACKGROUND",    (0, 1), (-1, -1), colors.HexColor("#E8E8E8")),  # grey all data rows
        ("BOX",           (0, 0), (-1, -1), 0.8, colors.white),
        ("INNERGRID",     (0, 0), (-1, -1), 0.8, colors.white),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    elems.append(interp_t)
    elems.append(Spacer(1, 4 * mm))

    # Ã¢"â¬Ã¢"â¬ Comments Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(Paragraph("<b>Comments</b>", _sec_style))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey,
                             spaceAfter=6))

    _bull_left = ParagraphStyle("_bull", fontName=F_REG, fontSize=10,
                                 leading=15, leftIndent=18, firstLineIndent=-10,
                                 spaceBefore=3, alignment=TA_LEFT)
    _bull_just = ParagraphStyle("_bull_j", fontName=F_REG, fontSize=10,
                                 leading=15, leftIndent=18, firstLineIndent=-10,
                                 spaceBefore=3, alignment=TA_JUSTIFY)
    for i, comment in enumerate(CDC_COMMENTS):
        style = _bull_just if i == len(CDC_COMMENTS) - 1 else _bull_left
        elems.append(Paragraph(f"&#x2022; {comment}", style))
    _cdc_user_comment = str(patient.get("comments", "") or "").strip()
    if _cdc_user_comment and _cdc_user_comment.lower() not in ("nan","none","na","-","--"):
        elems.append(Paragraph(f"&#x2022; {_cdc_user_comment}", _bull_just))
    elems.append(Spacer(1, 4 * mm))

    # Ã¢"â¬Ã¢"â¬ Signatures Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.extend(_signature_block(case.get("signatories", []), S))

    return elems


# Ã¢"â¬Ã¢"â¬Ã¢"â¬ DSA (Donor Specific Antibody) Cross match report builder Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬

def _build_dsa_report(case: dict, S: dict) -> list:
    """Return story flowables for DSA Cross match report (2 pages)."""

    patient = case.get("patient", {})
    donors  = case.get("donors", [])
    donor   = donors[0] if donors else {}
    dsa     = case.get("dsa_results", {})

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")

    def _P(text, font=F_BOLD, size=10, color=BLACK, align=TA_LEFT, leading=None):
        return Paragraph(text, ParagraphStyle("_dsa", fontName=font, fontSize=size,
            textColor=color, alignment=align, leading=leading or size + 2))

    def _clean(val):
        s = str(val).strip() if val else ""
        return s if s and s.lower() not in ("nan", "none", "") else "NA"

    def _norm(val):
        """Title-case for names/text; 'NA' fallback for empty."""
        return _title_case(_clean_display(val)) or "NA"

    # Name/place fields (patient/donor name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def _norm_name(val):
        return _title_case(_clean_display(val), is_name=True) or "NA"

    def _raw(val):
        """No case change Ã¢â¬" for PIN, sample numbers, dates."""
        return _clean_display(val) or "NA"

    def _color_hex(c):
        """Return 6-char hex string for a reportlab color."""
        try:
            return "%02x%02x%02x" % (
                int(round(c.red * 255)),
                int(round(c.green * 255)),
                int(round(c.blue * 255)),
            )
        except Exception:
            return "000000"

    def _photo_cell(photo_bytes):
        if photo_bytes:
            try:
                return Image(io.BytesIO(photo_bytes), width=_ph_w, height=_ph_h)
            except Exception:
                pass
        return Spacer(1, _ph_h)

    elems = []

    # Ã¢"â¬Ã¢"â¬ Info table Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    info_lbl_style = ParagraphStyle("_dsa_lbl", fontName=F_BOLD, fontSize=10,
                                    textColor=BLACK, leading=12)
    info_val_style = ParagraphStyle("_dsa_val", fontName=F_BOLD, fontSize=10,
                                    textColor=BLACK, leading=12)

    def IL(t): return Paragraph(f"<b>{t}</b>", info_lbl_style)
    def IV(t): return Paragraph(_norm(t),  info_val_style)
    def IR(t): return Paragraph(_raw(t),   info_val_style)
    def IC():  return Paragraph("<b>:</b>", info_lbl_style)

    cw = CONTENT_W
    # col: [lbl_L, colon_L, val_L, GAP, lbl_R, colon_R, val_R]
    # Column widths are computed per-report: the donor value column is sized to
    # just fit its (usually short) values and all leftover width goes to the
    # patient value column, so a long Hospital/Clinic name renders at full font.
    info_col_w = _demography_col_widths(patient, donor)

    def E(): return Paragraph("", info_lbl_style)

    def IV_name(text, col_w_pts):
        return Paragraph(_norm_name(text), info_val_style)

    info_rows = [
        [IL("Patient name"),    IC(), IV_name(patient.get("name",""), info_col_w[2]), E(), IL("Donor name"),          IC(), IV_name(donor.get("name",""), info_col_w[6])],
        [IL("Gender/ Age"),     IC(), IR(_normalize_age(patient.get("gender_age",""))),      E(), IL("Gender/ Age"),         IC(), IR(_normalize_age(donor.get("gender_age","")))],
        [IL("PIN"),             IC(), IR(patient.get("pin","")),             E(), IL("PIN"),                 IC(), IR(donor.get("pin","NA"))],
        [IL("Sample Number"),   IC(), IR(patient.get("sample_number","")),   E(), IL("Sample Number"),       IC(), IR(donor.get("sample_number","NA"))],
        [IL("Diagnosis"),       IC(), IV(patient.get("diagnosis","")),       E(), IL("Sample receipt date"), IC(), IR(donor.get("receipt_date",""))],
        # Hospital/Clinic value renders at full font; a long name wraps onto an
        # extra line (see _fit_one_line) and the row grows taller rather than the
        # text being shrunk to fit a single line.
        [IL("Hospital/Clinic"), IC(), _fit_one_line(_norm_name(patient.get("hospital_clinic","")), info_col_w[2], info_val_style), E(), IL("Report date"), IC(), IR(donor.get("report_date",""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_INFO_BG),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (1, 0), (1, -1), 0),
        ("RIGHTPADDING",  (1, 0), (1, -1), 2),
        ("LEFTPADDING",   (3, 0), (3, -1), 0),
        ("RIGHTPADDING",  (3, 0), (3, -1), 0),
        ("LEFTPADDING",   (5, 0), (5, -1), 0),
        ("RIGHTPADDING",  (5, 0), (5, -1), 2),
        # no bottom border â demography table sits flush above the photo table
    ]))
    elems.append(info_t)
    elems.append(Spacer(1, 2.5 * mm))

    # ââ Photo / sample-type table âââââââââââââââââââââââââââââââââââââââââââââ
    _ph_w   = 28 * mm
    _ph_h   = 30 * mm
    _pc_w   = 54 * mm
    _lbl_w  = 38 * mm
    col_w_photo = [_lbl_w, _pc_w, _pc_w]

    pat_photo = _photo_cell(patient.get("photo_bytes"))
    don_photo = _photo_cell(donor.get("photo_bytes"))

    p_sample_type = _clean(patient.get("sample_type", "Serum"))
    d_sample_type = _clean(donor.get("sample_type", "ACD Tube"))
    p_collect     = _clean(patient.get("collection_date", ""))
    d_collect     = _clean(donor.get("collection_date", ""))

    _GREY = C_INFO_BG

    photo_rows = [
        [Paragraph("", info_lbl_style),
         _P("PATIENT DETAILS", F_BOLD, 11, BLACK, TA_CENTER),
         _P("DONOR DETAILS",   F_BOLD, 11, BLACK, TA_CENTER)],
        [_P("Photo", F_BOLD, 10, BLACK, TA_LEFT), pat_photo, don_photo],
        [_P("Sample type",        F_REG, 10, BLACK, TA_LEFT),
         _P(p_sample_type,        F_REG, 10, BLACK, TA_CENTER),
         _P(d_sample_type,        F_REG, 10, BLACK, TA_CENTER)],
        [_P("Date of Collection", F_REG, 10, BLACK, TA_LEFT),
         _P(p_collect,            F_REG, 10, BLACK, TA_CENTER),
         _P(d_collect,            F_REG, 10, BLACK, TA_CENTER)],
    ]
    photo_t = Table(photo_rows, colWidths=col_w_photo)
    photo_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _GREY),
        ("BOX",           (0, 0), (-1, -1), 1.0, colors.white),
        ("INNERGRID",     (0, 0), (-1, -1), 1.0, colors.white),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
        ("ALIGN",         (1, 0), (2, -1),  "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("MINROWHEIGHT",  (0, 1), (-1, 1),  _ph_h + 4 * mm),
    ]))
    photo_t.hAlign = 'CENTER'
    elems.append(photo_t)
    elems.append(Spacer(1, 2 * mm))

    # Ã¢"â¬Ã¢"â¬ Relationship box Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    rel_text = _clean(donor.get("relationship", ""))
    rel_para = Paragraph(
        f"<b>Relationship Of The Donor With Recipient:</b> {rel_text}",
        ParagraphStyle("_dsa_rel", fontName=F_BOLD, fontSize=10, textColor=BLACK,
                        alignment=TA_CENTER, leading=14)
    )
    rel_t = Table([[rel_para]], colWidths=[CONTENT_W])
    rel_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_CDC_REL_BG),
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#F0AD4E")),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    elems.append(rel_t)
    elems.append(Spacer(1, 2.5 * mm))

    # Ã¢"â¬Ã¢"â¬ Detection section heading Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    # Compute remarks early so it can influence padding/spacing of elements below.
    _rmk = patient.get("remarks", "").strip()

    _det_heading = (
        "Detection of HLA Class I and Class II "
        "(Donor specific IgG Antibodies)"
    )
    # Reduce heading space when remarks is present to keep block compact
    _det_para = Paragraph(
        f"<u><b>{_det_heading}</b></u>",
        ParagraphStyle("_dsa_det", fontName=F_BOLD, fontSize=11,
                       textColor=C_NGS_TITLE, alignment=TA_CENTER, leading=15,
                       spaceAfter=4 if _rmk else 5)
    )

    # Ã¢"â¬Ã¢"â¬ DSA Results table Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    _dsa_col_w = [
        CONTENT_W * 0.30,   # Test
        CONTENT_W * 0.20,   # Result
        CONTENT_W * 0.25,   # MFI
        CONTENT_W * 0.25,   # MFI Positive cutoff
    ]
    # Styles matching reference: white bg header, black bold text, grey borders
    _dsa_hdr_s  = ParagraphStyle("_dsa_th", fontName=F_BOLD, fontSize=10,
                                  textColor=BLACK, alignment=TA_CENTER, leading=13)
    _dsa_hdr_lL = ParagraphStyle("_dsa_th_l", fontName=F_BOLD, fontSize=10,
                                  textColor=BLACK, alignment=TA_LEFT, leading=13)
    _dsa_lbl_s  = ParagraphStyle("_dsa_td_l", fontName=F_REG, fontSize=10,
                                  textColor=BLACK, alignment=TA_LEFT, leading=13)
    _dsa_cen_s  = ParagraphStyle("_dsa_td_c", fontName=F_REG, fontSize=10,
                                  textColor=BLACK, alignment=TA_CENTER, leading=13)

    c1_result  = dsa.get("class1_result", "Negative")
    c1_mfi     = dsa.get("class1_mfi", "")
    c1_cutoff  = dsa.get("class1_cutoff", ">1000")
    c2_result  = dsa.get("class2_result", "Negative")
    c2_mfi     = dsa.get("class2_mfi", "")
    c2_cutoff  = dsa.get("class2_cutoff", ">1000")

    c1_hex = _color_hex(_cdc_result_color(c1_result))
    c2_hex = _color_hex(_cdc_result_color(c2_result))

    dsa_data = [
        # Header row Ã¢â¬" white background, black bold text
        [Paragraph("<b>Test</b>",                                 _dsa_hdr_lL),
         Paragraph("<b>Result</b>",                               _dsa_hdr_s),
         Paragraph("<b>Mean Fluorescent\nIntensity</b>",          _dsa_hdr_s),
         Paragraph("<b>Mean Fluorescent\nIntensity Positive\ncutoff</b>", _dsa_hdr_s)],
        # Class I row
        [Paragraph("Anti HLA Class I\nantibodies",               _dsa_lbl_s),
         Paragraph(f"<font color='#{c1_hex}'><b>{c1_result}</b></font>", _dsa_cen_s),
         Paragraph(c1_mfi,    _dsa_cen_s),
         Paragraph(c1_cutoff, _dsa_cen_s)],
        # Class II row
        [Paragraph("Anti HLA Class II\nantibodies",              _dsa_lbl_s),
         Paragraph(f"<font color='#{c2_hex}'><b>{c2_result}</b></font>", _dsa_cen_s),
         Paragraph(c2_mfi,    _dsa_cen_s),
         Paragraph(c2_cutoff, _dsa_cen_s)],
        # Footer row
        [Paragraph("*To be correlated clinically",
                   ParagraphStyle("_dsa_ft", fontName=F_REG, fontSize=10,
                                  textColor=BLACK, alignment=TA_LEFT, leading=13)),
         "", "", ""],
    ]
    _rmk = patient.get("remarks", "").strip()
    _donor_rmk = (donor.get("remarks", "") or "").strip()
    # Use tighter row padding when remarks is present so the whole block fits on page 1
    _row_pad = 4 if (_rmk or _donor_rmk) else 5

    dsa_t = Table(dsa_data, colWidths=_dsa_col_w)
    dsa_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
        ("BOX",           (0, 0), (-1, -1), 0.8, colors.grey),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, colors.grey),
        ("SPAN",          (0, 3), (-1, 3)),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), _row_pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), _row_pad),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    # Wrap detection heading + results table + remarks in KeepTogether
    _rmk_para = ([Paragraph(
        f"<b>Remarks : </b>{_clean_display(_rmk)}",
        ParagraphStyle("_dsa_rmk", fontName=F_BOLD, fontSize=10,
                       leading=14, spaceBefore=6)
    )] if _rmk else [])
    if _donor_rmk:
        _rmk_para.append(Paragraph(
            f"<b>Donor Remarks : </b>{_clean_display(_donor_rmk)}",
            ParagraphStyle("_dsa_drmk", fontName=F_BOLD, fontSize=10,
                           leading=14, spaceBefore=6)
        ))

    elems.append(KeepTogether([_det_para, dsa_t] + _rmk_para))

    # Ã¢"â¬Ã¢"â¬ Page break Ã¢â ' page 2 Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(PageBreak())

    # Ã¢"â¬Ã¢"â¬ Section heading style Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    _sec_style = ParagraphStyle("_dsa_sec_hdr", fontName=F_BOLD, fontSize=14,
                                 textColor=C_NGS_TITLE, leading=18, spaceAfter=2)

    # Ã¢"â¬Ã¢"â¬ Comments Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(Paragraph("<b>Comments:</b>", _sec_style))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey,
                             spaceAfter=6))

    _bull_just = ParagraphStyle("_dsa_bull_j", fontName=F_REG, fontSize=10,
                                 leading=15, leftIndent=18, firstLineIndent=-10,
                                 spaceBefore=3, alignment=TA_JUSTIFY)
    for comment in DSA_COMMENTS:
        elems.append(Paragraph(f"&#x2022; {comment}", _bull_just))
    # User-supplied additional comment Ã¢â¬" appended as a new bullet, same style
    _dsa_user_comment = str(patient.get("comments", "") or "").strip()
    if _dsa_user_comment and _dsa_user_comment.lower() not in ("nan","none","na","-","--"):
        elems.append(Paragraph(f"&#x2022; {_dsa_user_comment}", _bull_just))
    elems.append(Spacer(1, 4 * mm))

    # Ã¢"â¬Ã¢"â¬ Recommendations Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(Paragraph("<b>Recommendations</b>", _sec_style))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey,
                             spaceAfter=6))
    for rec in DSA_RECOMMENDATIONS:
        elems.append(Paragraph(f"&#x2022; {rec}", _bull_just))
    elems.append(Spacer(1, 4 * mm))

    # Ã¢"â¬Ã¢"â¬ Signatures Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.extend(_signature_block(case.get("signatories", []), S))

    return elems


# âââ Luminex SSO HLA Typing report builder âââââââââââââââââââââââââââââââââââ

def _build_luminex_report(case: dict, S: dict) -> list:
    """Return story flowables for HLA Typing (Luminex/SSO) report."""
    patient  = case.get("patient", {})
    donors   = case.get("donors", [])
    donor    = donors[0] if donors else {}
    interp   = case.get("luminex_interpretation", "")

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")
    cw = CONTENT_W

    def _norm(v): return _title_case(_clean_display(v)) or "NA"
    # Name/place fields (patient/donor name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def _norm_name(v): return _title_case(_clean_display(v), is_name=True) or "NA"
    def _raw(v):  return _clean_display(v) or "NA"
    def _IL(t):   return Paragraph(f"<b>{t}</b>",
                    ParagraphStyle("_lil", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IV(t):   return Paragraph(_norm(t),
                    ParagraphStyle("_liv", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IVN(t):  return Paragraph(_norm_name(t),
                    ParagraphStyle("_livn", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IR(t):   return Paragraph(_raw(t),
                    ParagraphStyle("_lir", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IC():    return Paragraph("<b>:</b>",
                    ParagraphStyle("_lic", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _E():     return Paragraph("",
                    ParagraphStyle("_lie", fontName=F_REG,  fontSize=10, textColor=BLACK, leading=12))

    elems = []

    # ââ Title ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _ttl_s = ParagraphStyle("_lx_ttl", fontName=F_BOLD, fontSize=20,
                             textColor=C_NGS_TITLE, alignment=TA_CENTER, leading=26)
    elems.append(Paragraph("<b>HLA Typing</b>", _ttl_s))
    elems.append(Spacer(1, 3*mm))

    # ââ Info table (6-row, 7-col) ââââââââââââââââââââââââââââââââââââââââââââââ
    # col: [lbl_L, colon_L, val_L, GAP, lbl_R, colon_R, val_R]  (widths in points)
    # Defaults: wide left value column (long Hospital/Clinic names) and a generous
    # inter-column gap that shifts the donor block right.  When the donor name is
    # long, the donor value column grows leftward â first eating the gap (down to a
    # small minimum), then borrowing from the left value column â so the name stays
    # on one line at full font.  (A long Hospital/Clinic name may then wrap an extra
    # line, which is acceptable.)
    _lblL, _colL, _valL = cw*0.170, cw*0.016, cw*0.340
    _gap                = cw*0.075
    _lblR, _colR, _valR = cw*0.200, cw*0.016, cw*0.183
    _PAD, _MIN_GAP = 8, cw*0.024
    _dn_w = pdfmetrics.stringWidth(_norm_name(donor.get("name","")), F_BOLD, 10)
    _need = _dn_w + _PAD
    if _need > _valR:
        _deficit = _need - _valR
        _take = min(_deficit, _gap - _MIN_GAP)           # 1) shrink the gap
        _gap -= _take; _valR += _take; _deficit -= _take
        if _deficit > 0:                                 # 2) borrow from val_L
            _pn_w    = pdfmetrics.stringWidth(_norm_name(patient.get("name","")), F_BOLD, 10)
            _floor_L = max(_pn_w + _PAD, cw*0.22)         # keep patient name on one line
            _take = min(_deficit, max(0.0, _valL - _floor_L))
            _valL -= _take; _valR += _take
    info_col_w = [_lblL, _colL, _valL, _gap, _lblR, _colR, _valR]
    info_rows = [
        # Names render at full font size and wrap to a second line when long
        # (no auto-shrink) so a lengthy donor name stays legible.
        [_IL("Patient name"),    _IC(), _IVN(patient.get("name","")),
         _E(), _IL("Donor name"),            _IC(), _IVN(donor.get("name",""))],
        [_IL("Gender/ Age"),     _IC(), _IR(_normalize_age(patient.get("gender_age",""))),
         _E(), _IL("Gender/ Age"),           _IC(), _IR(_normalize_age(donor.get("gender_age","")))],
        [_IL("PIN"),             _IC(), _IR(patient.get("pin","")),
         _E(), _IL("PIN"),                   _IC(), _IR(donor.get("pin",""))],
        [_IL("Sample Number"),   _IC(), _IR(patient.get("sample_number","")),
         _E(), _IL("Sample Number"),         _IC(), _IR(donor.get("sample_number",""))],
        [_IL("Diagnosis"),       _IC(), _IV(patient.get("diagnosis","") or "NA"),
         _E(), _IL("Sample receipt date"),   _IC(), _IR(patient.get("receipt_date",""))],
        [_IL("Hospital/Clinic"), _IC(), _IVN(patient.get("hospital_clinic","")),
         _E(), _IL("Report date"),           _IC(), _IR(patient.get("report_date",""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_INFO_BG),
        # TOP-align so a long, wrapping value (e.g. a multi-line Hospital/Clinic
        # name) starts on the same line as its label instead of being centred â
        # otherwise the label sits beside the middle line of the wrapped value.
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 4), ("RIGHTPADDING",  (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (1,0), (1,-1), 0),  ("RIGHTPADDING",  (1,0), (1,-1), 2),
        ("LEFTPADDING",   (3,0), (3,-1), 0),  ("RIGHTPADDING",  (3,0), (3,-1), 0),
        ("LEFTPADDING",   (5,0), (5,-1), 0),  ("RIGHTPADDING",  (5,0), (5,-1), 2),
    ]))
    elems.append(info_t)
    elems.append(Spacer(1, 3*mm))

    # ââ Patient / Donor details block with photos ââââââââââââââââââââââââââââââ
    _hdr_s = ParagraphStyle("_lx_hdr", fontName=F_BOLD, fontSize=10,
                             textColor=BLACK, alignment=TA_CENTER, leading=14)
    _det_lbl_s = ParagraphStyle("_lx_dl", fontName=F_BOLD, fontSize=10,
                                 textColor=BLACK, leading=13)
    _det_val_s = ParagraphStyle("_lx_dv", fontName=F_REG, fontSize=10,
                                 textColor=BLACK, alignment=TA_CENTER, leading=13)

    _PH_H = 26*mm   # reserved photo height (used even when no photo is uploaded)

    def _photo_cell(img_bytes):
        if img_bytes:
            try:
                img = Image(io.BytesIO(img_bytes))
                tgt_w, tgt_h = 26*mm, _PH_H
                iw, ih = img.imageWidth, img.imageHeight
                scale = min(tgt_w / iw, tgt_h / ih)
                img.drawWidth  = iw * scale
                img.drawHeight = ih * scale
                return img
            except Exception:
                pass
        # Reserve the photo height so the row stays a proper size before upload.
        return Spacer(1, _PH_H)

    # Narrower than full width (centred below); keep the label column wide enough
    # for "Date of Collection:" on one line and shrink the two photo columns.
    det_col_w = [cw*0.22, cw*0.30, cw*0.30]
    det_data = [
        [Paragraph("", _hdr_s),
         Paragraph("<b>PATIENT DETAILS</b>", _hdr_s),
         Paragraph("<b>DONOR DETAILS</b>",   _hdr_s)],
        [Paragraph("<b>Photo</b>", _det_lbl_s),
         _photo_cell(case.get("luminex_pat_photo")),
         _photo_cell(case.get("luminex_don_photo"))],
        [Paragraph("<b>Relation:</b>",           _det_lbl_s),
         Paragraph(_norm(patient.get("relation","Patient")), _det_val_s),
         Paragraph(_norm(donor.get("relation","")),          _det_val_s)],
        [Paragraph("<b>Sample Type:</b>",        _det_lbl_s),
         Paragraph(_norm(patient.get("sample_type","EDTA Blood")), _det_val_s),
         Paragraph(_norm(donor.get("sample_type","EDTA Blood")),   _det_val_s)],
        [Paragraph("<b>Date of Collection:</b>", _det_lbl_s),
         Paragraph(_raw(patient.get("collection_date","")), _det_val_s),
         Paragraph(_raw(donor.get("collection_date","")),   _det_val_s)],
    ]
    det_t = Table(det_data, colWidths=det_col_w)
    det_t.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("TOPPADDING",    (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 4), ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        # Uniform light-grey fill with white gridlines (matches reference report).
        ("BACKGROUND",    (0,0), (-1,-1), C_INFO_BG),
        ("BOX",           (0,0), (-1,-1), 1.0, colors.white),
        ("INNERGRID",     (0,0), (-1,-1), 1.0, colors.white),
        # Keep the photo row a proper height even before photos are uploaded.
        ("MINROWHEIGHT",  (0,1), (-1,1), _PH_H + 4*mm),
    ]))
    det_t.hAlign = "CENTER"
    elems.append(det_t)
    elems.append(Spacer(1, 2*mm))

    # ââ Typing Result table ââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _rslt_hdr_s = ParagraphStyle("_lx_rh", fontName=F_BOLD, fontSize=13,
                                  textColor=C_NGS_TITLE, leading=16, spaceAfter=3)
    elems.append(Paragraph("<b>Typing Result</b>", _rslt_hdr_s))
    elems.append(Spacer(1, 1*mm))

    pat_hla = patient.get("hla", {})
    don_hla = donor.get("hla", {})

    def _locus_has_val(hla_dict, locus):
        # Test the RAW allele text â _clean_display() maps empty cells to an
        # em-dash, which would make every locus look "filled".
        a = _merged_drb345(hla_dict) if locus == "DRB345" else (hla_dict.get(locus, ["", ""]) or [])
        return any(str(x).strip() for x in a if x is not None)

    # Always show the standard Class I & II loci; append any extra locus
    # (DPB1, DRB3/4/5, â¦) only when the patient or donor has a value for it.
    _BASE_LOCI  = ["A", "B", "C", "DRB1", "DQB1"]
    _EXTRA_LOCI = ["DPB1", "DRB345", "DQA1", "DPA1"]
    LOCI = _BASE_LOCI + [l for l in _EXTRA_LOCI
                         if _locus_has_val(pat_hla, l) or _locus_has_val(don_hla, l)]
    _th_s  = ParagraphStyle("_lx_th", fontName=F_BOLD, fontSize=10,
                             textColor=BLACK, alignment=TA_CENTER, leading=13)
    _td_s  = ParagraphStyle("_lx_td", fontName=F_REG,  fontSize=10,
                             textColor=BLACK, alignment=TA_CENTER, leading=13)
    _tsp_s = ParagraphStyle("_lx_ts", fontName=F_BOLD, fontSize=10,
                             textColor=BLACK, alignment=TA_CENTER, leading=13)

    _label_w = 0.155
    _loc_w   = (1.0 - _label_w) / len(LOCI)
    tbl_col_w = [cw*_label_w] + [cw*_loc_w] * len(LOCI)
    def _lx_hdr(l): return "HLA DRB3/4/5*" if l == "DRB345" else f"HLA-{l}*"
    hdr_row = ([Paragraph("<b>LOCUS</b>", _th_s)]
               + [Paragraph(f"<b>{_lx_hdr(l)}</b>", _th_s) for l in LOCI])

    def _pair(hla_dict, locus):
        a = _merged_drb345(hla_dict) if locus == "DRB345" else hla_dict.get(locus, ["", ""])
        v1 = _clean_display(a[0]) if a else ""
        v2 = _clean_display(a[1]) if len(a) > 1 else ""
        return (v1 or "â", v2 or "â")

    pat_name_d = _title_case(_clean_display(patient.get("name", "")), is_name=True) or "Patient"
    don_name_d = _title_case(_clean_display(donor.get("name",  "")), is_name=True) or "Donor"
    pat_pairs  = [_pair(pat_hla, l) for l in LOCI]
    don_pairs  = [_pair(don_hla, l) for l in LOCI]

    pat_span_row = [Paragraph(f"<b>{pat_name_d} (Patient)</b>", _tsp_s)] + [""] * len(LOCI)
    don_span_row = [Paragraph(f"<b>{don_name_d} (Donor)</b>",   _tsp_s)] + [""] * len(LOCI)
    pat_row1 = ([Paragraph("<b>HLA-CLASS\nI &amp; II</b>", _th_s)]
                + [Paragraph(p[0], _td_s) for p in pat_pairs])
    pat_row2 = ([Paragraph("", _td_s)]
                + [Paragraph(p[1], _td_s) for p in pat_pairs])
    don_row1 = ([Paragraph("<b>HLA-CLASS\nI &amp; II</b>", _th_s)]
                + [Paragraph(p[0], _td_s) for p in don_pairs])
    don_row2 = ([Paragraph("", _td_s)]
                + [Paragraph(p[1], _td_s) for p in don_pairs])

    tbl_data = [hdr_row, pat_span_row, pat_row1, pat_row2, don_span_row, don_row1, don_row2]
    typing_t = Table(tbl_data, colWidths=tbl_col_w)
    typing_t.setStyle(TableStyle([
        # Only the column-header row is orange; the patient/donor name-span rows use
        # the same light grey as the allele data rows (matches reference report).
        ("BACKGROUND",    (0, 0), (-1,  0), C_HLA_HDR),
        ("BACKGROUND",    (0, 1), (-1,  1), C_HLA_ROW),
        ("SPAN",          (0, 1), (-1,  1)),
        ("BACKGROUND",    (0, 2), (-1,  3), C_HLA_ROW),
        ("SPAN",          (0, 2), (0,   3)),   # "HLA-CLASS I & II" merged across both patient allele rows
        ("BACKGROUND",    (0, 4), (-1,  4), C_HLA_ROW),
        ("SPAN",          (0, 4), (-1,  4)),
        ("BACKGROUND",    (0, 5), (-1,  6), C_HLA_ROW),
        ("SPAN",          (0, 5), (0,   6)),   # "HLA-CLASS I & II" merged across both donor allele rows
        ("INNERGRID",     (0, 0), (-1, -1), 1.0, colors.white),
        ("BOX",           (0, 0), (-1, -1), 1.0, colors.white),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    # Keep the whole result table on one page so the donor rows never split
    # away from their header onto the next page.
    elems.append(KeepTogether([typing_t]))

    # ââ Page 2: Interpretation Â· Test Details Â· Disclaimer Â· Sigs
    elems.append(PageBreak())

    # Page-2 styles: roomier text without risking the signature block or the
    # QR/footer reserve.  The document bottom margin already protects QR_ZONE,
    # so avoid negative spacers and keep the signature block together.
    _sec_s  = ParagraphStyle("_lx_sec", fontName=F_BOLD, fontSize=13,
                              textColor=C_NGS_TITLE, leading=17,
                              spaceBefore=3, spaceAfter=3)
    _body_s = ParagraphStyle("_lx_bdy", fontName=F_REG,  fontSize=10,
                              leading=14, spaceAfter=3, alignment=TA_JUSTIFY)
    _rule_gap = 4
    _section_gap = 2.5 * mm

    elems.append(Paragraph("<b>Interpretation</b>", _sec_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=_rule_gap))
    _interp_text = _clean_display(interp) or ""
    if _interp_text:
        elems.append(Paragraph(_interp_text, _body_s))
    elems.append(Spacer(1, _section_gap))

    _lx_remarks       = (patient.get("remarks", "") or "").strip()
    _lx_donor_remarks = (donor.get("remarks", "") or "").strip()
    _lx_comments      = (patient.get("comments", "") or "").strip()
    if _lx_remarks or _lx_donor_remarks:
        elems.append(Paragraph("<b>Remarks</b>", _sec_s))
        elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=_rule_gap))
        if _lx_remarks:
            elems.append(Paragraph(_lx_remarks, _body_s))
        if _lx_donor_remarks:
            elems.append(Paragraph(f"<b>Donor Remarks : </b>{_lx_donor_remarks}", _body_s))
        elems.append(Spacer(1, _section_gap))
    if _lx_comments:
        elems.append(Paragraph("<b>Comments</b>", _sec_s))
        elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=_rule_gap))
        elems.append(Paragraph(_lx_comments, _body_s))
        elems.append(Spacer(1, _section_gap))

    elems.append(Paragraph("<b>Test Details</b>", _sec_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=_rule_gap))
    for _para in LUMINEX_TEST_DETAILS:
        elems.append(Paragraph(_para, _body_s))
    elems.append(Spacer(1, _section_gap))

    elems.append(Paragraph("<b>Disclaimer</b>", _sec_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=_rule_gap))
    elems.append(Paragraph(LUMINEX_DISCLAIMER, _body_s))
    elems.append(Spacer(1, _section_gap))

    # Small gap then the signature block (kept together so it never splits across
    # pages; the page-2 spacing above is tuned so it still lands on this page).
    elems.append(Spacer(1, 1.5*mm))
    sig_items = _signature_block(case.get("signatories", []), S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


# âââ SAB (Single Antigen Bead) Assay report builder âââââââââââââââââââââââââââ

def _sab_info_table(case: dict) -> Table:
    """Patient demography table for SAB reports.

    Drawn once per page by _HFCanvas (repeat_info=True) so it appears at the
    top of every page, matching the reference report layout.
    """
    patient = case.get("patient", {})
    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")

    def _raw(v):  return _clean_display(v) or "NA"
    def _norm(v): return _title_case(_clean_display(v)) or "NA"
    # Name/place fields (patient name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def _norm_name(v): return _title_case(_clean_display(v), is_name=True) or "NA"
    def _IL(t):   return Paragraph(f"<b>{t}</b>",
                    ParagraphStyle("_sil", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IV(t):   return Paragraph(_norm(t),
                    ParagraphStyle("_siv", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IVN(t):  return Paragraph(_norm_name(t),
                    ParagraphStyle("_sivn", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IR(t):   return Paragraph(_raw(t),
                    ParagraphStyle("_sir", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IC():    return Paragraph("<b>:</b>",
                    ParagraphStyle("_sic", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _E():     return Paragraph("",
                    ParagraphStyle("_sie", fontName=F_REG,  fontSize=10, textColor=BLACK, leading=12))

    cw = CONTENT_W
    info_col_w = [cw*0.167, cw*0.016, cw*0.340, cw*0.020, cw*0.225, cw*0.016, cw*0.216]
    info_rows = [
        [_IL("Patient name"),    _IC(), _IVN(patient.get("name","")),
         _E(), _IL("PIN"),                    _IC(), _IR(patient.get("pin",""))],
        [_IL("Gender/ Age"),     _IC(), _IR(_normalize_age(patient.get("gender_age",""))),
         _E(), _IL("Sample Number"),          _IC(), _IR(patient.get("sample_number",""))],
        [_IL("Hospital MR No"),  _IC(), _IR(patient.get("hospital_mr_no","") or "NA"),
         _E(), _IL("Sample collection date"), _IC(), _IR(patient.get("collection_date",""))],
        [_IL("Specimen"),        _IC(), _IV(patient.get("specimen","") or "Serum"),
         _E(), _IL("Sample receipt date"),    _IC(), _IR(patient.get("receipt_date",""))],
        [_IL("Hospital/Clinic"), _IC(), _IVN(patient.get("hospital_clinic","")),
         _E(), _IL("Report date"),            _IC(), _IR(patient.get("report_date",""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_INFO_BG),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (1,0), (1,-1), 0), ("RIGHTPADDING", (1,0), (1,-1), 2),
        ("LEFTPADDING",   (3,0), (3,-1), 0), ("RIGHTPADDING", (3,0), (3,-1), 0),
        ("LEFTPADDING",   (5,0), (5,-1), 0), ("RIGHTPADDING", (5,0), (5,-1), 2),
    ]))
    return info_t


def _build_sab_report(case: dict, S: dict) -> list:
    """Return story flowables for SAB Class I (or II) report."""
    patient   = case.get("patient", {})
    alleles   = case.get("sab_alleles", [])   # [(allele_str, mfi_int), ...] sorted desc
    chart_b   = case.get("sab_chart_bytes")
    sab_class = case.get("sab_class", "I")

    # The "% PRA" sentence in Remarks/Comments is auto-filled from a separate
    # control, so it can carry a stale class token (e.g. "Class II") into a
    # Class I report. Force the class to match this report so the two never
    # disagree, regardless of how the case was entered (manual/bulk/draft/Excel).
    _pra_class_re = re.compile(r"(The SAB % PRA Class )(?:I{1,2})( is\b)", re.IGNORECASE)
    def _fix_pra_class(text):
        if not text:
            return text
        return _pra_class_re.sub(lambda m: f"{m.group(1)}{sab_class}{m.group(2)}", text)

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")

    def _raw(v):  return _clean_display(v) or "NA"
    def _norm(v): return _title_case(_clean_display(v)) or "NA"

    elems = []
    cw = CONTENT_W

    # Patient demography table is drawn on every page by _HFCanvas
    # (repeat_info=True); the top margin reserves space for it, so the story
    # starts directly with the "Test Report" title.

    # Ã¢"â¬Ã¢"â¬ "Test Report" title + bordered test name box Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    _title_s = ParagraphStyle("_sab_ttl", fontName=F_BOLD, fontSize=14,
                               textColor=C_NGS_TITLE, alignment=TA_CENTER, leading=18)
    elems.append(Paragraph("<b>Test Report</b>", _title_s))
    elems.append(Spacer(1, 3*mm))
    _test_name   = f"HLA SINGLE ANTIGEN BEAD ASSAY FOR CLASS {sab_class} IgG ANTIBODIES"
    _box_p_s     = ParagraphStyle("_sab_bn", fontName=F_BOLD, fontSize=10,
                                   textColor=BLACK, alignment=TA_CENTER, leading=11)
    _name_box    = Table([[Paragraph(_test_name, _box_p_s)]], colWidths=[cw * 0.88])
    _name_box.setStyle(TableStyle([
        ("BOX",           (0,0), (-1,-1), 0.8, BLACK),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
    ]))
    _name_box.hAlign = "CENTER"
    elems.append(_name_box)
    elems.append(Spacer(1, 5*mm))

    # Ã¢"â¬Ã¢"â¬ Section styles Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    _sec_s  = ParagraphStyle("_sab_sec",  fontName=F_BOLD, fontSize=13,
                              textColor=C_NGS_TITLE, leading=16, spaceAfter=2)
    _body_s = ParagraphStyle("_sab_bdy",  fontName=F_REG,  fontSize=10,
                              leading=14, alignment=TA_JUSTIFY)
    _bull_s = ParagraphStyle("_sab_bul",  fontName=F_REG,  fontSize=10,
                              leading=14, spaceBefore=2)

    # Ã¢"â¬Ã¢"â¬ Methodology Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(Paragraph("<b>Methodology</b>", _sec_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=4))
    elems.append(Paragraph(SAB_METHODOLOGY, _body_s))
    elems.append(Spacer(1, 4*mm))

    # Ã¢"â¬Ã¢"â¬ Interpretation Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(Paragraph("<b>Interpretation</b>", _sec_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=4))
    elems.append(Paragraph(SAB_INTERPRETATION, _body_s))
    elems.append(Spacer(1, 4*mm))

    # Ã¢"â¬Ã¢"â¬ Comments Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(Paragraph("<b>Comments</b>", _sec_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=4))
    for i, c in enumerate(SAB_COMMENTS_LIST, 1):
        elems.append(Paragraph(f"{i}. {c}", _bull_s))

    # Ã¢"â¬Ã¢"â¬ Remarks Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    _rmk = _fix_pra_class(_clean_display(patient.get("remarks", "")))
    if _rmk and _rmk != "â":
        elems.append(Spacer(1, 4*mm))
        _rmk_s = ParagraphStyle("_sab_rmk", fontName=F_BOLD, fontSize=10, leading=14)
        elems.append(Paragraph(f"<b>Remarks:</b> {_rmk}", _rmk_s))

    # Ã¢"â¬Ã¢"â¬ Page break -> allele result pages Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(PageBreak())

    # Ã¢"â¬Ã¢"â¬ Allele tables Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    high_alleles = [(a, m) for a, m in alleles if int(m) >= 1000]
    low_alleles  = [(a, m) for a, m in alleles if int(m) <  1000]

    _cls_hdr_s = ParagraphStyle("_sab_ch", fontName=F_BOLD, fontSize=11,
                                 textColor=C_NGS_TITLE, leading=14, spaceAfter=4)
    _sub_s     = ParagraphStyle("_sab_sb", fontName=F_REG,  fontSize=10,
                                 leading=13, spaceAfter=3)
    _th_s      = ParagraphStyle("_sab_th", fontName=F_BOLD, fontSize=11,
                                 textColor=BLACK, alignment=TA_CENTER, leading=14)
    _td_s      = ParagraphStyle("_sab_td", fontName=F_REG,  fontSize=10,
                                 textColor=BLACK, alignment=TA_CENTER, leading=13)

    elems.append(Paragraph(f"Class {sab_class} Single Antigen Bead (SAB) Result", _cls_hdr_s))
    elems.append(Spacer(1, 3*mm))

    def _allele_table(rows_data):
        _acw = [cw * 0.55, cw * 0.45]
        tdata = [[Paragraph("<b>Allele Specificity</b>", _th_s),
                  Paragraph("<b>MFI</b>", _th_s)]]
        for allele, mfi in rows_data:
            tdata.append([Paragraph(str(allele), _td_s), Paragraph(str(mfi), _td_s)])
        t = _BorderedTable(tdata, colWidths=_acw, repeatRows=1)
        style_cmds = [
            ("BACKGROUND",    (0,0), (-1, 0), C_SAB_TBL_HDR),
            ("BACKGROUND",    (0,1), (-1,-1), colors.white),
            # No per-row horizontal lines â keep only the column divider and the
            # header underline inside the table. The outer border is stroked by
            # _BorderedTable so it stays closed on every page, even when the
            # table spills across a page break.
            ("LINEAFTER",     (0,0), (0,-1), 0.5, colors.HexColor("#A0A0A0")),
            ("LINEBELOW",     (0,0), (-1,0), 0.5, colors.HexColor("#A0A0A0")),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]
        t.setStyle(TableStyle(style_cmds))
        return t

    if high_alleles:
        elems.append(Paragraph(
            f"Antibodies detected against HLA Class {sab_class} antigens tested with MFI &gt;1000",
            _sub_s))
        elems.append(_allele_table(high_alleles))
        if low_alleles:
            elems.append(Spacer(1, 6*mm))

    if low_alleles:
        elems.append(Paragraph(
            f"Antibodies detected against HLA Class {sab_class} antigens tested with MFI &lt;1000",
            _sub_s))
        elems.append(_allele_table(low_alleles))

    # Ã¢"â¬Ã¢"â¬ Chart page (optional) Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    if chart_b:
        elems.append(PageBreak())
        _ct_s = ParagraphStyle("_sab_ct", fontName=F_BOLD, fontSize=12,
                                textColor=C_NGS_TITLE, alignment=TA_CENTER, leading=16)
        try:
            img = Image(io.BytesIO(chart_b))
            # The source chart is landscape, so a true-aspect fit at full width
            # comes out short with whitespace below. Width is pinned to the
            # demography table width (CONTENT_W); height fills the whole available
            # block so the chart's bottom edge lands ~1 pt above the page number.
            _spacer_h = 3 * mm
            _title_h  = _ct_s.leading + 2
            _block_h  = case.get("_sab_chart_max_h") or 180 * mm
            _avail_h  = max(60.0, _block_h - _title_h - _spacer_h)
            # Width spans the full demography-table width (CONTENT_W), flush with
            # both edges of the table above; height fills the remaining frame so
            # the chart runs down to just above the page number.
            img.drawWidth  = CONTENT_W
            img.drawHeight = _avail_h
            img.hAlign = "LEFT"   # align with the demography table's left edge
            # Keep the title with its chart so the heading never orphans onto the
            # previous page when the image fills (almost) the whole frame.
            elems.append(KeepTogether([
                Paragraph("Bead Specificity Chart", _ct_s),
                Spacer(1, _spacer_h),
                img,
            ]))
        except Exception:
            elems.append(Paragraph("Bead Specificity Chart", _ct_s))

    # Ã¢"â¬Ã¢"â¬ Last page: comments box + limitations + signatures Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬Ã¢"â¬
    elems.append(PageBreak())

    _cb_lbl_s  = ParagraphStyle("_sab_cbl", fontName=F_BOLD, fontSize=10, leading=14)
    _cb_val_s  = ParagraphStyle("_sab_cbv", fontName=F_REG,  fontSize=10, leading=14, spaceBefore=3)
    _cb_note_s = ParagraphStyle("_sab_cbn", fontName=F_BOLD, fontSize=10, leading=14, spaceBefore=3)
    # Comments box: prefer the editable "comments" field, fall back to "remarks"
    # (keeps older cases/drafts that only set remarks rendering unchanged).
    _cmt_display = _fix_pra_class(
        _clean_display(patient.get("comments", ""))
        or _clean_display(patient.get("remarks", "")))
    _cmt_rows = [
        [Paragraph("<b>Comments:</b>", _cb_lbl_s)],
        [Paragraph(_cmt_display or "", _cb_val_s)],
        [Paragraph(f"<b>Note:</b> {SAB_NOTE}", _cb_note_s)],
    ]
    _cmt_t = Table(_cmt_rows, colWidths=[cw * 0.90])
    _cmt_t.setStyle(TableStyle([
        ("BOX",           (0,0), (-1,-1), 0.8, BLACK),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
    ]))
    _cmt_t.hAlign = "LEFT"
    elems.append(_cmt_t)
    elems.append(Spacer(1, 6*mm))

    _lim_sec_s = ParagraphStyle("_sab_ls", fontName=F_BOLD, fontSize=13,
                                 textColor=C_NGS_TITLE, leading=16, spaceAfter=2)
    _disc_s    = ParagraphStyle("_sab_ds", fontName=F_REG,  fontSize=10, leading=14,
                                 leftIndent=12, firstLineIndent=-10,
                                 alignment=TA_JUSTIFY, spaceBefore=3)
    elems.append(Paragraph("<b>Limitations &amp; Disclaimer</b>", _lim_sec_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=4))
    for lim in SAB_LIMITATIONS:
        elems.append(Paragraph(f"&#x2022; {lim}", _disc_s))
    elems.append(Spacer(1, 6*mm))

    sig_items = _signature_block(case.get("signatories", []), S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


# âââ PRA (Panel Reactive Antibodies) Quantitative report builder ââââââââââââââ

def _build_pra_report(case: dict, S: dict) -> list:
    """Return story flowables for a Panel Reactive Antibodies (PRA) Quantitative report."""
    patient = case.get("patient", {})
    cls     = case.get("pra_class") or ("II" if case.get("report_type") == "pra_class2" else "I")
    _pct    = str(case.get("pra_percentage", "") or "").strip()
    pct     = (_pct if _pct.endswith("%") else _pct + "%") if _pct else ""
    # Use the entered result if present; otherwise auto-classify from the percentage.
    result  = str(case.get("pra_result", "") or "").strip() or pra_result_for(_pct)

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")
    cw   = CONTENT_W
    BLUE = C_NGS_TITLE   # shared report blue for section headings

    def _raw(v):  return _clean_display(v) or "NA"
    def _norm(v): return _title_case(_clean_display(v)) or "NA"
    # Name/place fields (patient name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def _norm_name(v): return _title_case(_clean_display(v), is_name=True) or "NA"
    def _IL(t):   return Paragraph(f"<b>{t}</b>",
                    ParagraphStyle("_pil", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IV(t):   return Paragraph(_norm(t),
                    ParagraphStyle("_piv", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IVN(t):  return Paragraph(_norm_name(t),
                    ParagraphStyle("_pivn", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IR(t):   return Paragraph(_raw(t),
                    ParagraphStyle("_pir", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IC():    return Paragraph("<b>:</b>",
                    ParagraphStyle("_pic", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _E():     return Paragraph("",
                    ParagraphStyle("_pie", fontName=F_REG,  fontSize=10, textColor=BLACK, leading=12))

    elems = []

    # ââ Info table (5-row, 7-col) ââââââââââââââââââââââââââââââââââââââââââââââ
    # Patient value column (idx 2) is widened so a long Hospital/Clinic name fits
    # on one line; the slack comes from the right value column (idx 6), whose
    # entries (PIN, dates) are short â this shifts the right block rightward.
    info_col_w = [cw*0.150, cw*0.016, cw*0.380, cw*0.020, cw*0.232, cw*0.016, cw*0.186]
    info_rows = [
        [_IL("Patient name"),    _IC(), _IVN(patient.get("name","")),
         _E(), _IL("PIN"),                    _IC(), _IR(patient.get("pin",""))],
        [_IL("Gender"),          _IC(), _IV(patient.get("gender","")),
         _E(), _IL("Sample Number"),          _IC(), _IR(patient.get("sample_number",""))],
        [_IL("Age"),             _IC(), _IR(patient.get("age","")),
         _E(), _IL("Sample collection date"), _IC(), _IR(patient.get("collection_date",""))],
        [_IL("Specimen"),        _IC(), _IV(patient.get("specimen","") or "Serum"),
         _E(), _IL("Sample receipt date"),    _IC(), _IR(patient.get("receipt_date",""))],
        [_IL("Hospital/Clinic"), _IC(), _IVN(patient.get("hospital_clinic","")),
         _E(), _IL("Report date"),            _IC(), _IR(patient.get("report_date",""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_INFO_BG),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4), ("RIGHTPADDING",  (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (1,0), (1,-1), 0),  ("RIGHTPADDING",  (1,0), (1,-1), 2),
        ("LEFTPADDING",   (3,0), (3,-1), 0),  ("RIGHTPADDING",  (3,0), (3,-1), 0),
        ("LEFTPADDING",   (5,0), (5,-1), 0),  ("RIGHTPADDING",  (5,0), (5,-1), 2),
    ]))
    elems.append(info_t)
    elems.append(Spacer(1, 6*mm))

    # ââ Section helpers / styles âââââââââââââââââââââââââââââââââââââââââââââââ
    _sec_s  = ParagraphStyle("_pra_sec", fontName=F_BOLD, fontSize=13,
                              textColor=BLUE, leading=16, spaceAfter=3)
    _body_s = ParagraphStyle("_pra_bdy", fontName=F_REG, fontSize=10,
                              leading=14, alignment=TA_JUSTIFY)
    _num_s  = ParagraphStyle("_pra_num", fontName=F_REG, fontSize=10,
                              leading=14, leftIndent=16, firstLineIndent=-16, spaceBefore=3)
    _rec_s  = ParagraphStyle("_pra_rec", fontName=F_REG, fontSize=10,
                              leading=14, leftIndent=14, firstLineIndent=-14,
                              alignment=TA_JUSTIFY, spaceBefore=4)
    _th_s   = ParagraphStyle("_pra_th", fontName=F_BOLD, fontSize=10,
                              textColor=BLACK, alignment=TA_CENTER, leading=13)
    _td_s   = ParagraphStyle("_pra_td", fontName=F_REG,  fontSize=10,
                              textColor=BLACK, alignment=TA_CENTER, leading=13)

    def _section(title):
        elems.append(Paragraph(f"<b>{title}</b>", _sec_s))
        elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=4))

    # ââ Test indication ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _section("Test indication")
    _pname = _title_case(_clean_display(patient.get("name", "")), is_name=True) or "The patient"
    elems.append(Paragraph(
        f"{_pname} has been referred for Panel Reactive Antibodies Class {cls}", _body_s))
    elems.append(Spacer(1, 4*mm))

    # ââ Methodology ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _section("Methodology")
    elems.append(Paragraph(PRA_METHODOLOGY, _body_s))
    elems.append(Spacer(1, 4*mm))

    # ââ Result âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _section("Result")
    _res_data = [
        [Paragraph("<b>Panel Reactive Antibody</b>", _th_s),
         Paragraph("<b>Percentage</b>", _th_s),
         Paragraph("<b>Result</b>", _th_s)],
        [Paragraph(f"CLASS {cls} Antibodies", _td_s),
         Paragraph(pct, _td_s),
         Paragraph(result, _td_s)],
    ]
    # Narrower than full width and centred, to match the reference layout.
    _res_t = Table(_res_data, colWidths=[cw*0.28, cw*0.21, cw*0.21], hAlign="CENTER")
    _res_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), C_HLA_HDR),
        ("BACKGROUND",    (0,1), (-1,-1), C_HLA_ROW),
        ("INNERGRID",     (0,0), (-1,-1), 1.0, colors.white),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    elems.append(_res_t)
    elems.append(Spacer(1, 6*mm))

    _pra_rmk = (patient.get("remarks", "") or "").strip()

    # ââ Interpretation (reference bands) âââââââââââââââââââââââââââââââââââââââ
    _section("Interpretation")
    _int_data = [[Paragraph("<b>Panel Reactive Antibody (PRA) Percentage</b>", _th_s),
                  Paragraph("<b>Results</b>", _th_s)]]
    for _rng, _res in PRA_INTERP_ROWS:
        _int_data.append([Paragraph(_rng, _td_s), Paragraph(_res, _td_s)])
    _int_t = Table(_int_data, colWidths=[cw*0.46, cw*0.34], hAlign="CENTER")
    _int_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0), C_HLA_HDR),
        ("BACKGROUND",     (0,1), (-1,-1), C_HLA_ROW),
        ("INNERGRID",      (0,0), (-1,-1), 1.0, colors.white),
        ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",     (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    elems.append(_int_t)

    # ââ Page 2: Remarks (if any) Â· Comments Â· Recommendations Â· Reference Â· Signatures ââ
    elems.append(PageBreak())

    if _pra_rmk:
        _section("Remarks")
        elems.append(Paragraph(_pra_rmk, _body_s))
        elems.append(Spacer(1, 4*mm))

    _section("Comments")
    for _i, _c in enumerate(PRA_COMMENTS, 1):
        elems.append(Paragraph(f"{_i}. {_c}", _num_s))
    _pra_user_comment = (patient.get("comments", "") or "").strip()
    if _pra_user_comment:
        elems.append(Paragraph(f"{len(PRA_COMMENTS) + 1}. {_pra_user_comment}", _num_s))
    elems.append(Spacer(1, 5*mm))

    _section("Recommendations")
    for _r in PRA_RECOMMENDATIONS:
        elems.append(Paragraph(f"&#x25AA;&nbsp;&nbsp;{_r}", _rec_s))
    elems.append(Spacer(1, 5*mm))

    _section("Reference")
    for _i, _ref in enumerate(PRA_REFERENCES, 1):
        elems.append(Paragraph(f"{_i}. {_ref}", _num_s))
    elems.append(Spacer(1, 6*mm))

    sig_items = _signature_block(case.get("signatories", []), S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


# âââ Mixed PRA (Class I & II combined) report builder ââââââââââââââââââââââââ

def _build_mixed_pra_report(case: dict, S: dict) -> list:
    """Return story flowables for a Mixed PRA (Class I & II) Quantitative report."""
    patient = case.get("patient", {})

    def _fmt_pct(raw):
        s = str(raw or "").strip()
        if not s: return ""
        return s if s.endswith("%") else s + "%"

    pct1    = _fmt_pct(case.get("pra_percentage_1", ""))
    result1 = str(case.get("pra_result_1", "") or "").strip() or pra_result_for(str(case.get("pra_percentage_1", "") or "").strip())
    pct2    = _fmt_pct(case.get("pra_percentage_2", ""))
    result2 = str(case.get("pra_result_2", "") or "").strip() or pra_result_for(str(case.get("pra_percentage_2", "") or "").strip())

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")
    cw     = CONTENT_W
    BLUE   = C_NGS_TITLE

    def _raw(v):       return _clean_display(v) or "NA"
    def _norm(v):      return _title_case(_clean_display(v)) or "NA"
    def _norm_name(v): return _title_case(_clean_display(v), is_name=True) or "NA"
    def _IL(t):  return Paragraph(f"<b>{t}</b>",
                     ParagraphStyle("_mil", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IV(t):  return Paragraph(_norm(t),
                     ParagraphStyle("_miv", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IVN(t): return Paragraph(_norm_name(t),
                     ParagraphStyle("_mivn", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IR(t):  return Paragraph(_raw(t),
                     ParagraphStyle("_mir", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IC():   return Paragraph("<b>:</b>",
                     ParagraphStyle("_mic", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _E():    return Paragraph("",
                     ParagraphStyle("_mie", fontName=F_REG,  fontSize=10, textColor=BLACK, leading=12))

    elems = []

    # ââ Info table âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    info_col_w = [cw*0.150, cw*0.016, cw*0.380, cw*0.020, cw*0.232, cw*0.016, cw*0.186]
    info_rows = [
        [_IL("Patient name"),    _IC(), _IVN(patient.get("name","")),
         _E(), _IL("PIN"),                    _IC(), _IR(patient.get("pin",""))],
        [_IL("Gender"),          _IC(), _IV(patient.get("gender","")),
         _E(), _IL("Sample Number"),          _IC(), _IR(patient.get("sample_number",""))],
        [_IL("Age"),             _IC(), _IR(patient.get("age","")),
         _E(), _IL("Sample collection date"), _IC(), _IR(patient.get("collection_date",""))],
        [_IL("Specimen"),        _IC(), _IV(patient.get("specimen","") or "Serum"),
         _E(), _IL("Sample receipt date"),    _IC(), _IR(patient.get("receipt_date",""))],
        [_IL("Hospital/Clinic"), _IC(), _IVN(patient.get("hospital_clinic","")),
         _E(), _IL("Report date"),            _IC(), _IR(patient.get("report_date",""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_INFO_BG),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4), ("RIGHTPADDING",  (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (1,0), (1,-1), 0),  ("RIGHTPADDING",  (1,0), (1,-1), 2),
        ("LEFTPADDING",   (3,0), (3,-1), 0),  ("RIGHTPADDING",  (3,0), (3,-1), 0),
        ("LEFTPADDING",   (5,0), (5,-1), 0),  ("RIGHTPADDING",  (5,0), (5,-1), 2),
    ]))
    elems.append(info_t)
    elems.append(Spacer(1, 6*mm))

    # ââ Section helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _sec_s  = ParagraphStyle("_mpra_sec", fontName=F_BOLD, fontSize=13,
                              textColor=BLUE, leading=16, spaceAfter=3)
    _body_s = ParagraphStyle("_mpra_bdy", fontName=F_REG, fontSize=10,
                              leading=14, alignment=TA_JUSTIFY)
    _num_s  = ParagraphStyle("_mpra_num", fontName=F_REG, fontSize=10,
                              leading=14, leftIndent=16, firstLineIndent=-16, spaceBefore=3)
    _rec_s  = ParagraphStyle("_mpra_rec", fontName=F_REG, fontSize=10,
                              leading=14, leftIndent=14, firstLineIndent=-14,
                              alignment=TA_JUSTIFY, spaceBefore=4)
    _th_s   = ParagraphStyle("_mpra_th", fontName=F_BOLD, fontSize=10,
                              textColor=BLACK, alignment=TA_CENTER, leading=13)
    _td_s   = ParagraphStyle("_mpra_td", fontName=F_REG,  fontSize=10,
                              textColor=BLACK, alignment=TA_CENTER, leading=13)

    def _section(title):
        elems.append(Paragraph(f"<b>{title}</b>", _sec_s))
        elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=4))

    # ââ Test indication ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _section("Test indication")
    _pname = _title_case(_clean_display(patient.get("name", "")), is_name=True) or "The patient"
    elems.append(Paragraph(
        f"{_pname} has been referred for Panel Reactive Antibodies Class I &amp; II", _body_s))
    elems.append(Spacer(1, 4*mm))

    # ââ Methodology âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _section("Methodology")
    elems.append(Paragraph(PRA_METHODOLOGY, _body_s))
    elems.append(Spacer(1, 4*mm))

    # ââ Result (Class I row + Class II row) âââââââââââââââââââââââââââââââââââ
    _section("Result")
    _res_data = [
        [Paragraph("<b>Panel Reactive Antibody</b>", _th_s),
         Paragraph("<b>Percentage</b>", _th_s),
         Paragraph("<b>Result</b>", _th_s)],
        [Paragraph("CLASS I Antibodies",  _td_s), Paragraph(pct1, _td_s), Paragraph(result1, _td_s)],
        [Paragraph("CLASS II Antibodies", _td_s), Paragraph(pct2, _td_s), Paragraph(result2, _td_s)],
    ]
    _res_t = Table(_res_data, colWidths=[cw*0.28, cw*0.21, cw*0.21], hAlign="CENTER")
    _res_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), C_HLA_HDR),
        ("BACKGROUND",    (0,1), (-1,-1), C_HLA_ROW),
        ("INNERGRID",     (0,0), (-1,-1), 1.0, colors.white),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    elems.append(_res_t)
    elems.append(Spacer(1, 6*mm))

    # ââ Interpretation (reference bands) ââââââââââââââââââââââââââââââââââââââ
    _section("Interpretation")
    _int_data = [[Paragraph("<b>Panel Reactive Antibody (PRA) Percentage</b>", _th_s),
                  Paragraph("<b>Results</b>", _th_s)]]
    for _rng, _res in PRA_INTERP_ROWS:
        _int_data.append([Paragraph(_rng, _td_s), Paragraph(_res, _td_s)])
    _int_t = Table(_int_data, colWidths=[cw*0.46, cw*0.34], hAlign="CENTER")
    _int_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0), C_HLA_HDR),
        ("BACKGROUND",     (0,1), (-1,-1), C_HLA_ROW),
        ("INNERGRID",      (0,0), (-1,-1), 1.0, colors.white),
        ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",     (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    elems.append(_int_t)

    # ââ Page 2: Comments Â· Recommendations Â· Reference Â· Signatures âââââââââââ
    elems.append(PageBreak())

    _section("Comments")
    for _i, _c in enumerate(PRA_COMMENTS, 1):
        elems.append(Paragraph(f"{_i}. {_c}", _num_s))
    _mpra_user_comment = str(patient.get("comments", "") or "").strip()
    if _mpra_user_comment:
        elems.append(Paragraph(f"{len(PRA_COMMENTS) + 1}. {_mpra_user_comment}", _num_s))
    elems.append(Spacer(1, 5*mm))

    _section("Recommendations")
    for _r in PRA_RECOMMENDATIONS:
        elems.append(Paragraph(f"&#x25AA;&nbsp;&nbsp;{_r}", _rec_s))
    elems.append(Spacer(1, 5*mm))

    _section("Reference")
    for _i, _ref in enumerate(PRA_REFERENCES, 1):
        elems.append(Paragraph(f"{_i}. {_ref}", _num_s))
    elems.append(Spacer(1, 6*mm))

    sig_items = _signature_block(case.get("signatories", []), S)
    if sig_items:
        elems.append(KeepTogether(sig_items))

    return elems


# âââ Flow Cytometry Cross match report builder ââââââââââââââââââââââââââââââââ

def _build_flow_report(case: dict, S: dict) -> list:
    """Return story flowables for Flow Cytometry Crossmatch report (2 pages)."""
    patient = case.get("patient", {})
    donors  = case.get("donors", [])
    donor   = donors[0] if donors else {}
    flow    = case.get("flow_results", {})

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")

    def _P(text, font=F_BOLD, size=10, color=BLACK, align=TA_LEFT, leading=None):
        return Paragraph(text, ParagraphStyle("_fp", fontName=font, fontSize=size,
            textColor=color, alignment=align, leading=leading or size + 2))

    def _norm(val): return _title_case(_clean_display(val)) or "NA"
    # Name/place fields (patient/donor name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def _norm_name(val): return _title_case(_clean_display(val), is_name=True) or "NA"
    def _raw(val):  return _clean_display(val) or "NA"

    def _color_hex(c):
        try: return "%02x%02x%02x" % (int(round(c.red*255)), int(round(c.green*255)), int(round(c.blue*255)))
        except Exception: return "000000"

    _FLOW_BORDERLINE = colors.HexColor("#2980B9")   # blue for borderline result
    def _flow_color(val):
        v = val.strip().lower()
        if "negative"   in v: return C_CDC_NEG
        if "borderline" in v: return _FLOW_BORDERLINE
        return C_CDC_POS

    elems = []

    # ââ Info table (same layout as CDC) âââââââââââââââââââââââââââââââââââââââ
    lbl_s = ParagraphStyle("_fi_lbl", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12)
    val_s = ParagraphStyle("_fi_val", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12)
    def IL(t): return Paragraph(f"<b>{t}</b>", lbl_s)
    def IV(t): return Paragraph(_norm(t), val_s)
    def IR(t): return Paragraph(_raw(t),  val_s)
    def IC():  return Paragraph("<b>:</b>", lbl_s)
    def E():   return Paragraph("", lbl_s)

    # Column widths are computed per-report: the donor value column is sized to
    # just fit its (usually short) values and all leftover width goes to the
    # patient value column, so a long Hospital/Clinic name renders at full font.
    cw = CONTENT_W
    info_col_w = _demography_col_widths(patient, donor)

    def IV_name(text, col_w_pts):
        return Paragraph(_norm_name(text), val_s)

    info_rows = [
        [IL("Patient name"),    IC(), IV_name(patient.get("name",""), info_col_w[2]), E(), IL("Donor name"),          IC(), IV_name(donor.get("name",""), info_col_w[6])],
        [IL("Gender/ Age"),     IC(), IR(_normalize_age(patient.get("gender_age",""))),  E(), IL("Gender/ Age"),         IC(), IR(_normalize_age(donor.get("gender_age","")))],
        [IL("PIN"),             IC(), IR(patient.get("pin","")),             E(), IL("PIN"),                 IC(), IR(donor.get("pin","NA"))],
        [IL("Sample Number"),   IC(), IR(patient.get("sample_number","")),   E(), IL("Sample Number"),       IC(), IR(donor.get("sample_number","NA"))],
        [IL("Diagnosis"),       IC(), IV(patient.get("diagnosis","")),       E(), IL("Sample receipt date"), IC(), IR(donor.get("receipt_date",""))],
        # Hospital/Clinic value renders at full font; a long name wraps onto an
        # extra line (see _fit_one_line) and the row grows taller rather than the
        # text being shrunk to fit a single line.
        [IL("Hospital/Clinic"), IC(), _fit_one_line(_norm_name(patient.get("hospital_clinic","")), info_col_w[2], val_s), E(), IL("Report date"), IC(), IR(donor.get("report_date",""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_INFO_BG),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4), ("RIGHTPADDING",  (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (1,0), (1,-1), 0), ("RIGHTPADDING",  (1,0), (1,-1), 2),
        ("LEFTPADDING",   (3,0), (3,-1), 0), ("RIGHTPADDING",  (3,0), (3,-1), 0),
        ("LEFTPADDING",   (5,0), (5,-1), 0), ("RIGHTPADDING",  (5,0), (5,-1), 2),
    ]))
    elems.append(info_t)
    elems.append(Spacer(1, 4*mm))

    # ââ Photo / sample-type table âââââââââââââââââââââââââââââââââââââââââââââ
    # ââ Photo / sample-type table âââââââââââââââââââââââââââââââââââââââââ
    _ph_w = 30*mm; _ph_h = 36*mm; _pc_w = 54*mm; _lbl_w = 38*mm
    _GREY = C_INFO_BG

    def _photo_cell(pb):
        if pb:
            try:
                img = Image(io.BytesIO(pb), width=_ph_w, height=_ph_h)
                img.hAlign = "CENTER"
                return img
            except Exception: pass
        _emp = Table([[""]], colWidths=[_ph_w], rowHeights=[_ph_h])
        _emp.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#D0D0D0"))]))
        _emp.hAlign = "CENTER"
        return _emp

    photo_rows = [
        [Paragraph("", lbl_s),
         _P("PATIENT DETAILS", F_BOLD, 11, BLACK, TA_CENTER),
         _P("DONOR DETAILS",   F_BOLD, 11, BLACK, TA_CENTER)],
        [_P("Photo",            F_BOLD, 10, BLACK, TA_LEFT),
         _photo_cell(patient.get("photo_bytes")),
         _photo_cell(donor.get("photo_bytes"))],
        [_P("Sample type",      F_REG, 10, BLACK, TA_LEFT),
         _P(_raw(patient.get("sample_type","Serum")),                        F_REG, 10, BLACK, TA_CENTER),
         _P(_raw(donor.get("sample_type","Sodium Heparin Whole Blood")),     F_REG, 10, BLACK, TA_CENTER)],
        [_P("Date of Collection", F_REG, 10, BLACK, TA_LEFT),
         _P(_raw(patient.get("collection_date","")), F_REG, 10, BLACK, TA_CENTER),
         _P(_raw(donor.get("collection_date","")),   F_REG, 10, BLACK, TA_CENTER)],
    ]
    photo_t = Table(photo_rows, colWidths=[_lbl_w, _pc_w, _pc_w],
                    rowHeights=[None, _ph_h + 8, None, None])
    photo_t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), _GREY),
        ("BACKGROUND",  (0,0), (-1, 0), colors.white),
        ("ALIGN",       (1,1), (2, 1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 4), ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("INNERGRID",   (0,0), (-1,-1), 0.5, colors.white),
        ("BOX",         (0,0), (-1,-1), 0.5, colors.white),
    ]))
    photo_t.hAlign = "CENTER"
    elems.append(photo_t)
    elems.append(Spacer(1, 2*mm))

    # ââ Relationship box ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _rel = _norm(donor.get("relationship", ""))
    if _rel and _rel != "NA":
        _rel_s = ParagraphStyle("_frel", fontName=F_BOLD, fontSize=10, textColor=BLACK,
                                 alignment=TA_CENTER, leading=14)
        _rel_t = Table([[Paragraph(f"<b>Relationship Of The Donor With Recipient:</b>  {_rel}", _rel_s)]],
                       colWidths=[CONTENT_W])
        _rel_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), C_CDC_REL_BG),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        elems.append(_rel_t)
        elems.append(Spacer(1, 2*mm))

    # ââ "Flowcytometry Cross match for T & B Lymphocytes" section title âââââââ
    _section_title_s = ParagraphStyle("_fst", fontName=F_BOLD, fontSize=16,
                                       textColor=C_NGS_TITLE, alignment=TA_CENTER, leading=20)

    # ââ 4-column results table ââââââââââââââââââââââââââââââââââââââââââââââââ
    t_antibody    = flow.get("t_antibody", "T-CELLS (CD3)")
    t_mcs         = flow.get("t_mcs", "<45")
    t_interp      = flow.get("t_interpretation", "Negative")
    b_antibody    = flow.get("b_antibody", "B-CELLS (CD19)")
    b_mcs         = flow.get("b_mcs", "<86")
    b_interp      = flow.get("b_interpretation", "Negative")

    _tbl_col_w    = [cw*0.22, cw*0.10, cw*0.19, cw*0.49]
    _HDR_BG       = colors.HexColor("#1F3864")
    _hdr_s  = ParagraphStyle("_fth", fontName=F_BOLD, fontSize=10,
                               textColor=colors.white, alignment=TA_CENTER, leading=13)
    _ab_s   = ParagraphStyle("_fab", fontName=F_BOLD, fontSize=10,
                               textColor=BLACK, alignment=TA_CENTER, leading=13)
    _mcs_s  = ParagraphStyle("_fmc", fontName=F_BOLD, fontSize=10,
                               alignment=TA_CENTER, leading=13)
    _int_s  = ParagraphStyle("_fin", fontName=F_BOLD, fontSize=10,
                               alignment=TA_CENTER, leading=13)
    _ref_s  = ParagraphStyle("_frf", fontName=F_BOLD, fontSize=9,
                               alignment=TA_LEFT, leading=13, leftIndent=4)

    def _mcs_para(val, interp_val):
        """Render MCS value colored to match the interpretation result."""
        col = _color_hex(_flow_color(interp_val))
        return Paragraph(f"<font color='#{col}'><b>{val}</b></font>", _mcs_s)

    def _interp_para(val):
        col = _color_hex(_flow_color(val))
        return Paragraph(f"<font color='#{col}'><b>{val.upper()}</b></font>", _int_s)

    def _ref_para(lines):
        """Build multi-colored reference lines for the REFERENCES cell."""
        parts = []
        for line in lines:
            v = line.strip().lower()
            if "negative"   in v: col = _color_hex(C_CDC_NEG)
            elif "borderline" in v: col = _color_hex(_FLOW_BORDERLINE)
            else:                   col = _color_hex(C_CDC_POS)
            parts.append(f"<font color='#{col}'><b>{line.strip()}</b></font>")
        return Paragraph("<br/>".join(parts), _ref_s)

    t_ref_lines = ["T-CELLS MCS<45 NEGATIVE", "T-CELLS MCS 45-60 BORDERLINE", "T-CELLS MCS>60 POSITIVE"]
    b_ref_lines = ["B-CELLS MCS<86 NEGATIVE", "B-CELLS MCS 86-116 BORDERLINE", "B-CELLS MCS>116 POSITIVE"]

    res_data = [
        [Paragraph("<b>ANTIBODY AGAINST</b>", _hdr_s),
         Paragraph("<b>MCS</b>", _hdr_s),
         Paragraph("<b>INTERPRETATION</b>", _hdr_s),
         Paragraph("<b>REFERENCES</b>", _hdr_s)],
        [Paragraph(f"<b>{t_antibody}</b>", _ab_s),
         _mcs_para(t_mcs, t_interp),
         _interp_para(t_interp),
         _ref_para(t_ref_lines)],
        [Paragraph(f"<b>{b_antibody}</b>", _ab_s),
         _mcs_para(b_mcs, b_interp),
         _interp_para(b_interp),
         _ref_para(b_ref_lines)],
    ]
    res_t = Table(res_data, colWidths=_tbl_col_w)
    res_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1, 0), _HDR_BG),
        ("BACKGROUND",    (0,1), (-1,-1), colors.white),
        ("INNERGRID",     (0,0), (-1,-1), 0.5, colors.HexColor("#808080")),
        ("BOX",           (0,0), (-1,-1), 0.5, colors.HexColor("#808080")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
    ]))
    # Title + table kept as one unit so a tall info table above (e.g. a
    # Hospital/Clinic name that wraps to a 2nd line) can never push a page
    # break between the title and the table, or split the table mid-row
    # (which would strand the B-CELLS row alone on the next page).
    elems.append(KeepTogether([
        Paragraph("<b>Flowcytometry Cross match for T &amp; B Lymphocytes</b>", _section_title_s),
        Spacer(1, 2*mm),
        res_t,
    ]))

    # ââ Page break â page 2 (Interpretation / Comments / Disclaimer / Signatures)
    # Without this the signature block overflows to a third page.
    elems.append(PageBreak())

    _sec_s    = ParagraphStyle("_fsh", fontName=F_BOLD, fontSize=14,
                                textColor=C_NGS_TITLE, leading=18, spaceAfter=2)
    _body_s   = ParagraphStyle("_fbdy", fontName=F_REG,  fontSize=10,
                                leading=14, alignment=TA_JUSTIFY)
    _num_s    = ParagraphStyle("_fnum", fontName=F_REG,  fontSize=10,
                                leading=14, leftIndent=18, firstLineIndent=-10,
                                alignment=TA_JUSTIFY, spaceBefore=3)
    _head_l_s = ParagraphStyle("_fhl", fontName=F_BOLD, fontSize=20,
                                textColor=C_NGS_TITLE, leading=24, spaceAfter=2)

    elems.append(Paragraph("<b>Interpretation</b>", _sec_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=6))

    # Overall result: worst of T and B
    def _overall(t, b):
        for v in (t, b):
            if "positive" in v.strip().lower(): return "Positive"
        for v in (t, b):
            if "borderline" in v.strip().lower(): return "Borderline"
        return "Negative"

    _manual_interp = flow.get("interpretation", "").strip()
    if _manual_interp:
        elems.append(Paragraph(_manual_interp, _body_s))
    else:
        t_col = _color_hex(_flow_color(t_interp))
        b_col = _color_hex(_flow_color(b_interp))
        elems.append(Paragraph(
            f"Flow Cytometry Cross match is "
            f"<font color='#{t_col}'>{t_interp}</font> for T cells and "
            f"<font color='#{b_col}'>{b_interp}</font> for B cells.",
            _body_s))
    elems.append(Spacer(1, 3*mm))

    # ââ Remarks (patient + donor, only if present) ââââââââââââââââââââââââââââââ
    _flow_pat_rmk   = (patient.get("remarks", "") or "").strip()
    _flow_donor_rmk = (donor.get("remarks", "") or "").strip()
    if _flow_pat_rmk or _flow_donor_rmk:
        elems.append(Paragraph("<b>Remarks</b>", _head_l_s))
        elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=6))
        if _flow_pat_rmk:
            elems.append(Paragraph(f"<b>Remarks : </b>{_flow_pat_rmk}", _body_s))
        if _flow_donor_rmk:
            elems.append(Paragraph(f"<b>Donor Remarks : </b>{_flow_donor_rmk}", _body_s))
        elems.append(Spacer(1, 3*mm))

    # ââ Comments ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.append(Paragraph("<b>Comments</b>", _head_l_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=6))
    for c in FLOW_COMMENTS:
        elems.append(Paragraph(f"&#x2022; {c}", _num_s))
        _flow_user_comment = str(patient.get("comments", "") or "").strip()
    if _flow_user_comment and _flow_user_comment.lower() not in ("nan","none","na","-","--"):
        elems.append(Paragraph(f"\u2022 {_flow_user_comment}",
            ParagraphStyle("_fuc", fontName=F_REG, fontSize=10, leading=14, spaceBefore=3,
                           leftIndent=18, firstLineIndent=-10, alignment=TA_JUSTIFY)))
    elems.append(Spacer(1, 3*mm))

    # ââ Disclaimer ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.append(Paragraph("<b>Disclaimer</b>", _head_l_s))
    elems.append(HRFlowable(width=CONTENT_W, thickness=0.8, color=colors.grey, spaceAfter=6))
    for d in FLOW_DISCLAIMER:
        elems.append(Paragraph(f"&#x2022; {d}", _num_s))
    elems.append(Spacer(1, 4*mm))

    # ââ Signatures â wrapped in KeepTogether so they never split across pages â
    sig_items = _signature_block(case.get("signatories", []), S)
    if sig_items:
        elems.append(KeepTogether(sig_items))
    return elems


# âââ KIR Genotyping report ââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _build_kir_report(case: dict, S: dict) -> list:
    """Return story flowables for KIR Genotyping report."""
    patient = case.get("patient", {})

    F_BOLD = _f("SegoeUI-Bold", "Helvetica-Bold")
    F_REG  = _f("SegoeUI",      "Helvetica")
    cw = CONTENT_W

    def _raw(v):  return _clean_display(v) or "NA"
    def _norm(v): return _title_case(_clean_display(v)) or "NA"
    # Name/place fields (patient name, hospital/clinic) are always re-cased
    # even when typed in ALL CAPS â see _title_case(is_name=True).
    def _norm_name(v): return _title_case(_clean_display(v), is_name=True) or "NA"
    def _IL(t):   return Paragraph(f"<b>{t}</b>",
                    ParagraphStyle("_kil", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IV(t):   return Paragraph(_norm(t),
                    ParagraphStyle("_kiv", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IVN(t):  return Paragraph(_norm_name(t),
                    ParagraphStyle("_kivn", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IR(t):   return Paragraph(_raw(t),
                    ParagraphStyle("_kir", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _IC():    return Paragraph("<b>:</b>",
                    ParagraphStyle("_kic", fontName=F_BOLD, fontSize=10, textColor=BLACK, leading=12))
    def _E():     return Paragraph("",
                    ParagraphStyle("_kie", fontName=F_REG,  fontSize=10, textColor=BLACK, leading=12))

    elems = []

    # ââ Info table âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    info_col_w = [cw*0.167, cw*0.016, cw*0.340, cw*0.020, cw*0.225, cw*0.016, cw*0.216]
    info_rows = [
        [_IL("Patient name"),    _IC(), _IVN(patient.get("name","")),
         _E(), _IL("PIN"),                    _IC(), _IR(patient.get("pin",""))],
        [_IL("Gender/ Age"),     _IC(), _IR(_normalize_age(patient.get("gender_age",""))),
         _E(), _IL("Sample Number"),          _IC(), _IR(patient.get("sample_number",""))],
        [_IL("Hospital MR No"),  _IC(), _IR(patient.get("hospital_mr_no","") or "NA"),
         _E(), _IL("Sample collection date"), _IC(), _IR(patient.get("collection_date",""))],
        [_IL("Specimen"),        _IC(), _IV(patient.get("specimen","") or "Blood EDTA"),
         _E(), _IL("Sample receipt date"),    _IC(), _IR(patient.get("receipt_date",""))],
        [_IL("Hospital/Clinic"), _IC(), _IVN(patient.get("hospital_clinic","")),
         _E(), _IL("Report date"),            _IC(), _IR(patient.get("report_date",""))],
    ]
    info_t = Table(info_rows, colWidths=info_col_w)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_INFO_BG),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4), ("RIGHTPADDING",  (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (1,0), (1,-1), 0),  ("RIGHTPADDING",  (1,0), (1,-1), 2),
        ("LEFTPADDING",   (3,0), (3,-1), 0),  ("RIGHTPADDING",  (3,0), (3,-1), 0),
        ("LEFTPADDING",   (5,0), (5,-1), 0),  ("RIGHTPADDING",  (5,0), (5,-1), 2),
    ]))
    elems.append(info_t)
    elems.append(Spacer(1, 5*mm))

    # ââ Section styles âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    _sec_s  = ParagraphStyle("_kir_sec",  fontName=F_BOLD, fontSize=13,
                              textColor=C_NGS_TITLE, leading=16, spaceAfter=2)
    _body_s = ParagraphStyle("_kir_bdy",  fontName=F_REG,  fontSize=10,
                              leading=14, alignment=TA_JUSTIFY)
    _note_s = ParagraphStyle("_kir_note", fontName=F_REG,  fontSize=9,
                              leading=12, fontStyle="italic" if False else "normal")

    # ââ Method âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.append(Paragraph("<b>Method</b>", _sec_s))
    elems.append(HRFlowable(width=cw, thickness=0.8, color=colors.grey, spaceAfter=4))
    elems.append(Paragraph(KIR_METHOD, _body_s))
    elems.append(Spacer(1, 5*mm))

    # ââ Result âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.append(Paragraph("<b>Result</b>", _sec_s))
    elems.append(HRFlowable(width=cw, thickness=0.8, color=colors.grey, spaceAfter=4))

    # Determine genotype
    genes = case.get("kir_genes", {})
    override = case.get("kir_genotype_override", "Auto")
    genotype = override if override and override != "Auto" else _kir_calc_genotype(genes)

    _genotype_s = ParagraphStyle("_kir_gt", fontName=F_REG, fontSize=10, leading=14)
    elems.append(Paragraph(f"The KIR genotype of the Sample - <b>{genotype}</b>", _genotype_s))
    elems.append(Spacer(1, 3*mm))

    # Gene results table â 17 columns: Gene | 16 gene names
    _th_s = ParagraphStyle("_kir_th", fontName=F_BOLD, fontSize=8.5,
                            textColor=BLACK, alignment=TA_CENTER, leading=11)
    _td_s = ParagraphStyle("_kir_td", fontName=F_BOLD, fontSize=10,
                            textColor=BLACK, alignment=TA_CENTER, leading=13)

    gene_col_w = [cw * 0.072] + [cw * (0.928 / 16)] * 16
    hdr_row  = [Paragraph("<b>Gene</b>", _th_s)] + [Paragraph(f"<b>{g}</b>", _th_s) for g in KIR_GENES]
    val_row  = [Paragraph("<b>Result</b>", _th_s)] + [
        Paragraph(f"<b>{genes.get(g, 'â')}</b>", _td_s) for g in KIR_GENES
    ]
    gene_tbl = Table([hdr_row, val_row], colWidths=gene_col_w)
    gene_tbl.setStyle(TableStyle([
        # White cells with black text and thin black gridlines (matches reference).
        ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
        ("TEXTCOLOR",     (0, 0), (-1, -1), BLACK),
        ("BOX",           (0, 0), (-1, -1), 0.25, BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.13, BLACK),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        # Tight side padding so each 4-char gene name (e.g. "2DL1") fits on one
        # line within its narrow column instead of wrapping to "2DL" + "1".
        ("LEFTPADDING",   (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    elems.append(gene_tbl)
    elems.append(Spacer(1, 2*mm))
    elems.append(Paragraph(KIR_FOOTNOTE, _note_s))
    elems.append(Spacer(1, 5*mm))

    # ââ Interpretation âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    elems.append(Paragraph("<b>Interpretation of the result</b>", _sec_s))
    elems.append(HRFlowable(width=cw, thickness=0.8, color=colors.grey, spaceAfter=4))
    # Opening line follows the genotype (or a custom override); the closing
    # disclaimer is always the same constant, appended once below.
    custom_interp = case.get("kir_interpretation", "").strip()
    if custom_interp:
        # Drop a trailing copy of the disclaimer so it is never duplicated.
        if custom_interp.endswith(KIR_INTERP_DISCLAIMER):
            custom_interp = custom_interp[:-len(KIR_INTERP_DISCLAIMER)].strip()
        interp_paras = [p.strip() for p in custom_interp.split("\n\n") if p.strip()]
    else:
        interp_paras = [_kir_interp_first_line(genotype)]
    interp_paras.append(KIR_INTERP_DISCLAIMER)
    for para in interp_paras:
        elems.append(Paragraph(para, _body_s))
        elems.append(Spacer(1, 3*mm))

    _kir_remarks  = (patient.get("remarks", "") or "").strip()
    _kir_comments = (patient.get("comments", "") or "").strip()
    if _kir_remarks:
        elems.append(Paragraph("<b>Remarks</b>", _sec_s))
        elems.append(HRFlowable(width=cw, thickness=0.8, color=colors.grey, spaceAfter=4))
        elems.append(Paragraph(_kir_remarks, _body_s))
        elems.append(Spacer(1, 4*mm))
    if _kir_comments:
        elems.append(Paragraph("<b>Comments</b>", _sec_s))
        elems.append(HRFlowable(width=cw, thickness=0.8, color=colors.grey, spaceAfter=4))
        elems.append(Paragraph(_kir_comments, _body_s))
        elems.append(Spacer(1, 4*mm))

    # ââ Page 2: Test Details + Signatures ââââââââââââââââââââââââââââââââââââââ
    elems.append(PageBreak())
    elems.append(Paragraph("<b>Test details</b>", _sec_s))
    elems.append(HRFlowable(width=cw, thickness=0.8, color=colors.grey, spaceAfter=4))
    for para in KIR_TEST_DETAILS.split("\n"):
        para = para.strip()
        if para:
            elems.append(Paragraph(para, _body_s))
            elems.append(Spacer(1, 3*mm))
    elems.append(Spacer(1, 6*mm))

    sig_items = _signature_block(case.get("signatories", []), S)
    if sig_items:
        elems.append(KeepTogether(sig_items))
    return elems


# âââ Top-level entry point ââââââââââââââââââââââââââââââââââââââââââââââââââââ

def generate_pdf(case: dict, output_path: str) -> str:
    """
    Generate a PDF for the given case dict and save to output_path.
    The report type (single_hla / transplant_donor / rpl_couple) is read directly
    from case["report_type"] â set automatically by hla_data_parser.py.
    Returns output_path.
    """
    _register_fonts()
    S = _styles()

    report_type = case.get("report_type", "single_hla")
    nabl        = case.get("nabl", True)
    with_logo   = case.get("with_logo", True)

    # Title strings per report type
    TITLES = {
        "single_hla":       "HLA Typing High Resolution",
        "transplant_donor": "HLA Typing High Resolution",
        "ngs_photo":        "HLA Typing High Resolution",
        "loci11":           "HLA Typing High Resolution",
        "rpl_couple":       "HLA Typing \u2013 NGS High Resolution Typing",
        "single_rpl":       "HLA Typing \u2013 NGS High Resolution Typing",
        "cdc_crossmatch":   "Complement Dependent Cytotoxicity (CDC) Cross match",
        "dsa_crossmatch":   "Donor Specific Antibody Crossmatch",
        "sab_class1":       "",
        "sab_class2":       "",
        "flow_crossmatch":  "Flow Cytometry Cross match",
        "luminex_typing":   "",
        "kir_genotyping":   "KIR Genotyping",
        "pra_class1":       "Panel Reactive Antibodies (PRA) Class I Quantitative",
        "pra_class2":       "Panel Reactive Antibodies (PRA) Class II Quantitative",
        "single_locus":     "",    # builder draws its own locus-specific title
        "hla_c":            "",    # builder draws its own title
        "mixed_pra":        "Panel Reactive Antibodies (PRA) Class I & II  Quantitative",
    }
    title = TITLES.get(report_type, "HLA Typing Report")

    # Title paragraph (font differs between NGS and RPL)
    title_style = S["title_rpl"] if report_type in ("rpl_couple", "single_rpl") else S["title_ngs"]
    title_para  = Paragraph(title, title_style)

    # Compute header/footer heights â always use real image dimensions so the
    # content area position is identical whether or not logos are shown.
    from PIL import Image as PILImage

    raw  = hla_assets.get_image_bytes(hla_assets.HEADER_NONNABL_B64)
    pil  = PILImage.open(io.BytesIO(raw))
    ow, oh   = pil.size
    banner_h = (oh / ow) * CONTENT_W

    raw_f    = hla_assets.get_image_bytes(hla_assets.FOOTER_BAR_B64)
    pil_f    = PILImage.open(io.BytesIO(raw_f))
    fw, fh   = pil_f.size
    footer_h = (fh / fw) * CONTENT_W

    # Luminex and Single Locus draw their own titles right at the frame top â
    # use a tighter banner clearance so the title sits closer to the header.
    _top_gap      = 1.5 * mm if report_type in ("luminex_typing", "single_locus", "hla_c") else 4 * mm
    top_margin    = MARGIN_T + banner_h + _top_gap

    # SAB reports repeat the patient demography table on every page (drawn by
    # _HFCanvas). Reserve top-margin space for it: table height + a gap below.
    _is_sab = report_type in ("sab_class1", "sab_class2")
    _sab_info_offset = 0
    if _is_sab:
        _sab_info_h = _sab_info_table(case).wrap(CONTENT_W, PAGE_H)[1]
        _sab_info_offset = top_margin          # table top edge from page top
        top_margin += _sab_info_h + 5 * mm     # push content below the table
    _PAGE_NUM_AREA = 4 * mm
    # CDC/DSA result tables sit at the very bottom of page 1; add extra clearance so
    # the last table row doesn't land inside the ITdose QR overlay zone.
    # Paired with -6 mm spacer trims inside the builders so the page still fits.
    _cdc_dsa_extra = 6 * mm if report_type in ("cdc_crossmatch", "dsa_crossmatch") else 0
    # QR_ZONE: blank strip above footer+page-number reserved for external QR-code
    # overlay. NGS-with-Photo reclaims half of it (see _qr_reserve) so long remarks
    # don't push the donor locus table onto the next page.
    bottom_margin = (MARGIN_B + footer_h + _PAGE_NUM_AREA + 2 * mm
                     + _qr_reserve(report_type) + _cdc_dsa_extra)

    # SAB: let the content frame run down to ~1 pt above the "Page X of N" line so
    # the bead-specificity chart can fill the page vertically. The page number sits
    # at the top of the reserved bottom strip (see _HFCanvas) and the external QR
    # overlay sits *below* it, so reclaiming the strip above the page number is safe.
    _FRAME_PAD = 6   # SimpleDocTemplate's default Frame inset (top & bottom)
    if _is_sab:
        # Page number's visual top above the page bottom (9 pt font â 9 pt ascent).
        _pageno_top   = MARGIN_B + footer_h + QR_ZONE - 3 * mm + 9
        # Flowables stop at bottom_margin + _FRAME_PAD, so set the margin a frame
        # pad lower than the target (1 pt above the page number) â content then
        # bottoms out ~1 pt above the "Page X of N" line.
        bottom_margin = _pageno_top + 1 - _FRAME_PAD

    # Tell the SAB builder how tall the chart block (title + chart) may be on one
    # page. The builder reserves ~2 pt more for the title than it actually renders,
    # so pass the frame's usable height (less both 6 pt pads) plus that 2 pt back,
    # making the rendered title + chart fill the frame exactly and the chart bottom
    # land ~1 pt above the page number without splitting across pages.
    if _is_sab:
        case["_sab_chart_max_h"] = (PAGE_H - top_margin - bottom_margin) - 2 * _FRAME_PAD + 2

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
    )

    # Build story
    if report_type == "single_hla":
        body = _build_ngs_single(case, S)
    elif report_type == "transplant_donor":
        body = _build_ngs_transplant(case, S)
    elif report_type == "ngs_photo":
        body = _build_ngs_photo(case, S)
    elif report_type == "loci11":
        body = _build_ngs_transplant(case, S)
    elif report_type == "rpl_couple":
        body = _build_rpl_couple(case, S)
    elif report_type == "single_rpl":
        body = _build_single_rpl(case, S)
    elif report_type == "cdc_crossmatch":
        body = _build_cdc_report(case, S)
    elif report_type == "dsa_crossmatch":
        body = _build_dsa_report(case, S)
    elif report_type in ("sab_class1", "sab_class2"):
        body = _build_sab_report(case, S)
    elif report_type == "flow_crossmatch":
        body = _build_flow_report(case, S)
    elif report_type == "luminex_typing":
        body = _build_luminex_report(case, S)
    elif report_type == "kir_genotyping":
        body = _build_kir_report(case, S)
    elif report_type in ("pra_class1", "pra_class2"):
        body = _build_pra_report(case, S)
    elif report_type == "single_locus":
        body = _build_single_locus(case, S)
    elif report_type == "hla_c":
        body = _build_hla_c(case, S)
    elif report_type == "mixed_pra":
        body = _build_mixed_pra_report(case, S)
    else:
        body = _build_ngs_single(case, S)

    # Reports whose builder draws its own title leave TITLES empty â skip the
    # (empty) title paragraph + spacer so they don't reserve a dead line of height
    # between the header banner and the in-body title.
    if title.strip():
        story = [title_para, Spacer(1, 1 * mm)] + body
    else:
        story = body

    # Fix 4: use the numbered-canvas approach for accurate page counting.
    # total_pages starts at 1 (dummy); _NumberedCanvas updates it in save() before
    # drawing header/footer, so every page shows the real "Page X of N".
    cb = _HFCanvas(case, title, banner_h, footer_h, total_pages=1,
                   repeat_info=_is_sab, repeat_top_offset=_sab_info_offset)
    numbered_canvas_class = _make_numbered_canvas_class(cb)
    doc.build(story, canvasmaker=numbered_canvas_class)
    return output_path


# âââ Filename helper ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def make_filename(case: dict) -> str:
    def safe(s):
        return re.sub(r"[^\w.\-]", "_", str(s).strip()).strip("_") or "Unknown"

    def safe_readable(s):
        # Keep a human-readable name (spaces, dots) and only strip characters
        # that are illegal in Windows/macOS filenames.
        s = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", str(s))
        return re.sub(r"\s+", " ", s).strip(" .") or "Unknown"

    report_type = case.get("report_type", "")

    # SAB reports use a spaced, human-readable convention:
    #   "<Name>_SAB _Class <I|II>_<WITH|WITHOUT> LOGO.pdf"
    if report_type in ("sab_class1", "sab_class2"):
        name = safe_readable(case["patient"].get("name", ""))
        cls  = case.get("sab_class") or ("II" if report_type == "sab_class2" else "I")
        logo = "WITH LOGO" if case.get("with_logo", True) else "WITHOUT LOGO"
        return f"{name}_SAB _Class {cls}_{logo}.pdf"

    # PRA reports use a spaced, human-readable convention:
    #   "<Name>_PRA_Class <I|II>_<WITH|WITHOUT> LOGO.pdf"
    if report_type in ("pra_class1", "pra_class2"):
        name = safe_readable(case["patient"].get("name", ""))
        cls  = case.get("pra_class") or ("II" if report_type == "pra_class2" else "I")
        logo = "WITH LOGO" if case.get("with_logo", True) else "WITHOUT LOGO"
        return f"{name}_PRA_Class {cls}_{logo}.pdf"

    if report_type == "mixed_pra":
        name = safe_readable(case["patient"].get("name", ""))
        logo = "with logo" if case.get("with_logo", True) else "without logo"
        return f"{name}_MIXED PRA Quantitative _{logo}.pdf"

    p = safe(case["patient"].get("name", ""))
    donors = "_".join(
        safe(d.get("name", ""))
        for d in case.get("donors", [])
        if str(d.get("name", "")).strip()
    )
    rtype = {"single_hla": "HLA_NGS", "transplant_donor": "HLA_NGS",
             "ngs_photo": "HLA_NGS_PHOTO", "loci11": "HLA_NGS",
             "rpl_couple": "RPL", "single_rpl": "RPL_SINGLE", "cdc_crossmatch": "CDC",
             "dsa_crossmatch": "DSA", "sab_class1": "SAB_C1", "sab_class2": "SAB_C2",
             "flow_crossmatch": "FLOW", "luminex_typing": "HLA_LUMINEX",
             "kir_genotyping": "KIR", "pra_class1": "PRA_C1",
             "pra_class2": "PRA_C2", "single_locus": "SINGLE_LOCUS",
             "hla_c": "HLA_C", "mixed_pra": "PRA_MIXED"}.get(report_type, "HLA")
    logo  = "WITH_LOGO" if case.get("with_logo", True) else "WITHOUT_LOGO"
    parts = [p] + ([donors] if donors else []) + [rtype, logo]
    if report_type == "loci11":
        parts.append("11_loci")
    return "_".join(parts) + ".pdf"


def unique_output_path(out_dir: str, filename: str) -> str:
    """Return a collision-free path: if filename already exists in out_dir,
    append _(2), _(3), â¦ until a free slot is found."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(out_dir, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(out_dir, f"{base}_({counter}){ext}")
        counter += 1
    return candidate
