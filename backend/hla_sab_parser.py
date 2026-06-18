"""
hla_sab_parser.py
Parses single-patient SAB (Single Antigen Bead) Class I/II Excel workbooks and
free-text allele/MFI pastes into the case-shape consumed by hla_template.py.

Ported verbatim (logic-for-logic) from the desktop HLA Report Generator's
HLAReportGeneratorApp._parse_sab_excel_kit1 / _kit2 / _parse_sab_allele_text_static,
de-coupled from PyQt6 so it can run server-side.
"""

import os
import re
import io
import zipfile
from datetime import datetime, date


# ─── Kit identification ──────────────────────────────────────────────────────

def sab_kit_id(name: str) -> str:
    """Map a Kit label to the stable internal id 'kit1'/'kit2'."""
    s = str(name or "").strip().lower()
    if "lambda" in s or "kit 2" in s or "kit2" in s:
        return "kit2"
    return "kit1"


# ─── % PRA sentence helpers ───────────────────────────────────────────────────

_AUTO_PRA_RE = re.compile(r"^\s*The SAB % PRA Class (?:I|II) is \d+%\.?\s*$",
                           re.IGNORECASE)


def sab_pra_sentence(pct_text, sab_class) -> str:
    """Build 'The SAB % PRA Class {I|II} is {n}%.' from a raw % value, or '' if none."""
    m = re.search(r"\d+", str(pct_text or ""))
    if not m:
        return ""
    cls = "II" if str(sab_class or "").strip().upper().endswith("II") else "I"
    return f"The SAB % PRA Class {cls} is {int(m.group())}%."


def is_auto_pra_text(text) -> bool:
    """True if `text` is an auto-generated % PRA sentence (safe to overwrite)."""
    return bool(_AUTO_PRA_RE.match(str(text or "")))


# ─── Free-text allele/MFI paste parser ───────────────────────────────────────

def parse_sab_allele_text(text: str) -> list:
    """Parse allele text (allele,mfi per line) into [(allele, mfi_int), ...] desc.

    The MFI is the trailing number; everything before the last separator is
    the allele name. Splitting on the *last* comma/tab (not every comma) is
    essential because DQ/DP allele names contain commas themselves, e.g.
    'DQA1*01:01, DQB1*05:01,1755'.
    """
    result = []
    for line in (text or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.*)[,\t]\s*([0-9]+(?:\.[0-9]+)?)\s*$", line)
        if not m:
            continue
        allele = m.group(1).strip().rstrip(",").strip()
        if not allele:
            continue
        try:
            mfi = int(float(m.group(2)))
        except ValueError:
            continue
        result.append((allele, mfi))
    return sorted(result, key=lambda x: -x[1])


# ─── Excel parsing ────────────────────────────────────────────────────────────

def parse_sab_excel(path: str, kit: str = "kit1") -> dict:
    """Parse a single-patient SAB Class I/II Excel workbook.

    The HLA team runs two SAB softwares that export different layouts, so the
    caller passes the user-selected kit ('kit1' or 'kit2') and this dispatches
    to the matching parser. Both return the same shape:
        {patient, alleles, chart_bytes, pra_pct, sab_class}.
    """
    if sab_kit_id(kit) == "kit2":
        return _parse_sab_excel_kit2(path)
    return _parse_sab_excel_kit1(path)


def _parse_sab_excel_kit1(path: str) -> dict:
    """Parse a Kit 1 (Immucor) single-patient SAB Class I/II Excel workbook.

    Sheets are matched loosely by name:
      • 'patient details'   — header row + one value row.
      • '... REPORT ...'    — holds the 'Bead Detail' table
        (Antigens / Raw Value columns) and the '% PRA' figure.
      • '... CHART/CHAT ...'— holds the Bead Specificity Chart image.

    Returns {patient, alleles, chart_bytes, pra_pct, sab_class}.
    """
    def _fmt(v):
        if v is None:
            return ""
        if isinstance(v, (datetime, date)):
            return v.strftime("%d-%m-%Y")
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()

    if os.path.splitext(path)[1].lower() == ".xls":
        import xlrd

        class _XlrdCell:
            def __init__(self, value):
                self.value = value

        class _XlrdSheet:
            """Thin openpyxl-compatible wrapper around an xlrd sheet."""
            def __init__(self, sh, datemode):
                self._sh = sh
                self._dm = datemode
                self.title = sh.name
                self.max_row = sh.nrows
                self.max_column = sh.ncols
                self._images = []

            def cell(self, row, col):  # openpyxl uses 1-based indexing
                r, c = row - 1, col - 1
                if r < 0 or r >= self._sh.nrows or c < 0 or c >= self._sh.ncols:
                    return _XlrdCell(None)
                ct = self._sh.cell_type(r, c)
                val = self._sh.cell_value(r, c)
                if ct == xlrd.XL_CELL_DATE:
                    t = xlrd.xldate_as_tuple(val, self._dm)
                    val = date(*t[:3]) if t[3:] == (0, 0, 0) else datetime(*t)
                elif ct == xlrd.XL_CELL_EMPTY:
                    val = None
                return _XlrdCell(val)

        xlrd_wb = xlrd.open_workbook(path)

        class _FakeWb:
            def __init__(self, sheets):
                self.worksheets = sheets

        wb = _FakeWb([_XlrdSheet(xlrd_wb.sheet_by_index(i), xlrd_wb.datemode)
                      for i in range(xlrd_wb.nsheets)])
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)

    # ── locate sheets ───────────────────────────────────────────────────────
    pat_ws = rep_ws = chart_ws = None
    for ws in wb.worksheets:
        t = (ws.title or "").lower()
        if pat_ws is None and "patient" in t:
            pat_ws = ws
        elif rep_ws is None and "report" in t:
            rep_ws = ws
        elif chart_ws is None and ("chart" in t or "chat" in t or "bead" in t):
            chart_ws = ws
    if rep_ws is None:  # fall back to the busiest non-patient/chart sheet
        cand = [w for w in wb.worksheets if w not in (pat_ws, chart_ws)]
        rep_ws = max(cand, key=lambda w: w.max_row * w.max_column) if cand else None

    # ── patient details (header row + value row beneath) ────────────────────
    HEADER_MAP = {
        "patient name":           "patient_name",
        "gender/ age":            "gender_age",
        "gender / age":           "gender_age",
        "gender/age":             "gender_age",
        "hospital mr no":         "hospital_mr_no",
        "specimen":               "specimen",
        "hospital/clinic":        "hospital_clinic",
        "hospital / clinic":      "hospital_clinic",
        "pin":                    "pin",
        "sample number":          "sample_number",
        "sample collection date": "collection_date",
        "sample receipt date":    "receipt_date",
        "report date":            "report_date",
    }
    patient = {}
    if pat_ws is not None:
        hdr_row = None
        for r in range(1, min(pat_ws.max_row, 15) + 1):
            for c in range(1, pat_ws.max_column + 1):
                v = pat_ws.cell(r, c).value
                if isinstance(v, str) and v.strip().lower() == "patient name":
                    hdr_row = r
                    break
            if hdr_row:
                break
        if hdr_row:
            for c in range(1, pat_ws.max_column + 1):
                hv = pat_ws.cell(hdr_row, c).value
                if not isinstance(hv, str):
                    continue
                key = HEADER_MAP.get(hv.strip().lower())
                if key:
                    patient[key] = _fmt(pat_ws.cell(hdr_row + 1, c).value)

    # ── allele bead-detail table + % PRA + class ─────────────────────────────
    alleles, pra_pct, sab_class = [], None, None
    if rep_ws is not None:
        title = f" {(rep_ws.title or '').upper()} "
        if "SAB II" in title or "CLASS II" in title or " II " in title:
            sab_class = "II"
        elif "SAB I" in title or "CLASS I" in title or " I " in title:
            sab_class = "I"

        ant_col = raw_col = hdr_row = None
        for r in range(1, rep_ws.max_row + 1):
            labels = {}
            for c in range(1, rep_ws.max_column + 1):
                v = rep_ws.cell(r, c).value
                if isinstance(v, str):
                    labels[v.strip().lower()] = c
            if "antigens" in labels and "raw value" in labels:
                ant_col, raw_col, hdr_row = labels["antigens"], labels["raw value"], r
                break
        if hdr_row:
            for r in range(hdr_row + 1, rep_ws.max_row + 1):
                ant = rep_ws.cell(r, ant_col).value
                raw = rep_ws.cell(r, raw_col).value
                if raw is None:
                    continue
                allele = str(ant).strip() if ant is not None else ""
                if not allele:
                    continue
                try:
                    alleles.append((allele, int(round(float(raw)))))
                except (TypeError, ValueError):
                    continue
            alleles.sort(key=lambda x: -x[1])

        for r in range(1, rep_ws.max_row + 1):
            for c in range(1, rep_ws.max_column + 1):
                v = rep_ws.cell(r, c).value
                if isinstance(v, str) and "% pra" in v.strip().lower():
                    for c2 in range(c + 1, rep_ws.max_column + 1):
                        nv = rep_ws.cell(r, c2).value
                        if isinstance(nv, (int, float)):
                            pra_pct = float(nv)
                            break
                    break
            if pra_pct is not None:
                break

    # ── chart image (largest embedded image) + its Excel rotation ───────────
    # openpyxl drops the picture rotation, so read the workbook zip directly:
    # the largest media file is the chart, and the drawing XML that embeds it
    # carries the rotation Excel displays it with (OOXML rot = 1/60000 deg).
    chart_bytes, chart_rot = None, 0
    try:
        zf = zipfile.ZipFile(path)
        media = [n for n in zf.namelist() if n.startswith("xl/media/")]
        if media:
            chart_name = max(media, key=lambda n: zf.getinfo(n).file_size)
            chart_bytes = zf.read(chart_name)
            chart_base = os.path.basename(chart_name)
            for n in zf.namelist():
                if not re.match(r"xl/drawings/drawing\d+\.xml$", n):
                    continue
                rels = f"xl/drawings/_rels/{os.path.basename(n)}.rels"
                if rels not in zf.namelist():
                    continue
                rels_xml = zf.read(rels).decode("utf-8", "ignore")
                targets = re.findall(r'Target="([^"]+)"', rels_xml)
                if not any(os.path.basename(t) == chart_base for t in targets):
                    continue
                draw_xml = zf.read(n).decode("utf-8", "ignore")
                rots = re.findall(r'<a:xfrm[^>]*\brot="(-?\d+)"', draw_xml)
                if rots:
                    chart_rot = int(rots[0])
                break
        zf.close()
    except Exception:
        chart_bytes, chart_rot = chart_bytes, 0
    if chart_bytes is None:   # fall back to openpyxl's in-memory images
        best = 0
        for ws in wb.worksheets:
            for im in getattr(ws, "_images", []):
                try:
                    blob = im._data()
                except Exception:
                    continue
                if blob and len(blob) > best:
                    best, chart_bytes = len(blob), blob

    # Bake the Excel rotation into the bytes so the report pastes the chart
    # exactly as it appears in Excel (no rotation needed downstream).
    if chart_bytes and chart_rot:
        try:
            from PIL import Image as PILImage
            deg = (chart_rot / 60000.0) % 360      # OOXML hundred-thousandths
            if deg:
                pi = PILImage.open(io.BytesIO(chart_bytes))
                # OOXML rot is clockwise; PIL.rotate is counter-clockwise.
                pi = pi.rotate(-deg, expand=True)
                buf = io.BytesIO()
                pi.save(buf, format="PNG")
                chart_bytes = buf.getvalue()
        except Exception:
            pass

    return {
        "patient":     patient,
        "alleles":     alleles,
        "chart_bytes": chart_bytes,
        "pra_pct":     pra_pct,
        "sab_class":   sab_class,
    }


def _parse_sab_excel_kit2(path: str) -> dict:
    """Parse a Kit 2 (One Lambda LABScreen / Fusion) SAB Class I/II export.

    Kit 2 is the second SAB software's "LABScreen Report", a single-sheet
    Crystal Reports export (.xls). Cells are positioned by pixel so columns
    are not fixed; the parser locates landmarks by their text instead:

      • Allele table — a header row containing 'Allele Equiv' and 'Raw'; each
        following row gives the allele (Allele Equiv column) and its MFI (Raw
        column).
      • '%PRA' figure — first numeric cell to the right of the '%PRA' label.
      • Class — from the Catalog (LS1A…=I, LS2A…=II) or the 'SAB I/II' Session
        ID (checked II-before-I since 'SAB I' is a prefix of 'SAB II').
      • Sample ID — the value beside the 'Sample ID:' label.

    The Crystal export embeds no extractable Bead Specificity Chart image, so
    chart_bytes is None (upload the chart manually if one is needed).

    Returns {patient, alleles, chart_bytes, pra_pct, sab_class}.
    """
    def _s(v):
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()

    def _num(v):
        """Return float for a numeric cell or numeric-looking text, else None."""
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = _s(v)
        return float(s) if re.fullmatch(r"-?\d+(?:\.\d+)?", s) else None

    # ── load the single worksheet into a value grid (xls → xlrd, else openpyxl)
    rows = []
    if os.path.splitext(path)[1].lower() == ".xls":
        import xlrd
        sh = xlrd.open_workbook(path).sheet_by_index(0)
        rows = [[sh.cell_value(r, c) for c in range(sh.ncols)]
                for r in range(sh.nrows)]
    else:
        import openpyxl
        sh = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        rows = [list(r) for r in sh.iter_rows(values_only=True)]

    # ── allele table: header with 'allele equiv' + 'raw' ─────────────────────
    allele_col = raw_col = hdr = None
    for ri, row in enumerate(rows):
        labels = {}
        for ci, v in enumerate(row):
            s = _s(v).lower()
            if s and s not in labels:
                labels[s] = ci
        if "allele equiv" in labels and "raw" in labels:
            allele_col, raw_col, hdr = labels["allele equiv"], labels["raw"], ri
            break

    alleles = []
    if hdr is not None:
        for row in rows[hdr + 1:]:
            allele = _s(row[allele_col]) if allele_col < len(row) else ""
            mfi = _num(row[raw_col]) if raw_col < len(row) else None
            if not allele or mfi is None:
                continue
            alleles.append((allele, int(round(mfi))))
        alleles.sort(key=lambda x: -x[1])

    # ── class (catalog LS1A/LS2A or 'SAB I/II'; check II before I) ───────────
    blob = " ".join(_s(v).upper() for row in rows for v in row if _s(v))
    if "LS2A" in blob or "SAB II" in blob:
        sab_class = "II"
    elif "LS1A" in blob or "SAB I" in blob:
        sab_class = "I"
    else:
        sab_class = None

    # ── %PRA: first numeric cell to the right of the '%PRA' label ────────────
    pra_pct = None
    for row in rows:
        hit = next((ci for ci, v in enumerate(row) if "%pra" in _s(v).lower()),
                   None)
        if hit is None:
            continue
        for v2 in row[hit + 1:]:
            n = _num(v2)
            if n is not None:
                pra_pct = n
                break
        break

    # ── Sample ID → pin (the report's primary identifier) ────────────────────
    patient = {}
    for row in rows:
        hit = next((ci for ci, v in enumerate(row)
                    if _s(v).lower().startswith("sample id")), None)
        if hit is None:
            continue
        val = next((_s(v2) for v2 in row[hit + 1:] if _s(v2)), "")
        if val:
            patient["pin"] = val
        break

    return {
        "patient":     patient,
        "alleles":     alleles,
        "chart_bytes": None,
        "pra_pct":     pra_pct,
        "sab_class":   sab_class,
    }
