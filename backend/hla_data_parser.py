
import os
import re
import pandas as pd
from datetime import datetime
from typing import Optional


HLA_C_C1 = {
    "C*01", "C*03", "C*07", "C*08", "C*12", "C*13", "C*14", "C*16",
}


def c_supertype(allele: Optional[str]) -> Optional[str]:
    if not allele or allele in ("-", "nan", ""):
        return None
    m = re.match(r"(C\*\d+)", allele)
    if not m:
        return None
    prefix = m.group(1)
    return "C1" if prefix in HLA_C_C1 else "C2"


def _fmt_date(val) -> str:
    if pd.isna(val) or str(val).strip() in ("", "nan", "NaT"):
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d-%m-%Y")
    s = str(val).strip()
    parts = re.split(r"[/\-]", s)
    if len(parts) == 3:
        dd, mm, yyyy = parts[0].strip(), parts[1].strip(), parts[2].strip()
        return f"{dd.zfill(2)}-{mm.zfill(2)}-{yyyy}"
    return s


def _clean_str(val) -> str:
    if pd.isna(val) or str(val).strip() in ("nan", "NaT", "None"):
        return ""
    return str(val).strip()


def _norm_col(s) -> str:
    return re.sub(r'\s+', ' ', str(s).strip().lower())


_PREFIX_MAP = {
    "mr":     "Mr",
    "mrs":    "Mrs",
    "ms":     "Ms",
    "master": "Master",
    "dr":     "Dr",
}


def _sentence_case(val) -> str:
    s = _clean_str(val)
    if not s:
        return s

    s = re.sub(r'^(mr|mrs|ms|master|dr)\.(\S)', r'\1 \2', s, flags=re.IGNORECASE)
    s = re.sub(r'^(mr|mrs|ms|master|dr)\.\s+', r'\1 ', s, flags=re.IGNORECASE)

    words = s.split()
    if not words:
        return s

    first_key = words[0].rstrip('.').lower()
    if first_key in _PREFIX_MAP:
        prefix    = _PREFIX_MAP[first_key]
        remaining = words[1:]
        if not remaining:
            return prefix
        fn = remaining[0].lower()
        fn = fn[0].upper() + fn[1:] if fn else fn
        rest = [w.lower() for w in remaining[1:]]
        return " ".join([prefix, fn] + rest)

    lowered = [w.lower() for w in words]
    lowered[0] = lowered[0][0].upper() + lowered[0][1:] if lowered[0] else lowered[0]
    result = " ".join(lowered)
    result = re.sub(r'\.([a-z])', lambda m: '.' + m.group(1).upper(), result)
    return result


def _clean_allele(val) -> Optional[str]:
    s = _clean_str(val)
    if s in ("-", "", "nan"):
        return None
    if re.sub(r"\s+", "", s).lower() == "insufficientdata":
        return None
    if "*" in s:
        prefix, fields_str = s.split("*", 1)
        fields = fields_str.split(":")
        s = prefix + "*" + ":".join(fields[:3])
    return s


def _split_alleles(raw: str):
    raw = raw.strip().strip('"').strip("'")
    raw = raw.split("|")[0].strip()
    parts = [p.strip() for p in re.split(r"[,;]", raw) if p.strip()]
    a1 = _clean_allele(parts[0]) if len(parts) > 0 else None
    a2 = _clean_allele(parts[1]) if len(parts) > 1 else None
    if a1 and a2 and a1 == a2:
        a2 = None
    return a1, a2



def _parse_miniseq_results(df_result: pd.DataFrame) -> dict:
    header_row = None
    for i, row in df_result.iterrows():
        if str(row.iloc[0]).strip() == "SampleName":
            header_row = i
            break
    if header_row is None:
        return {}

    df = df_result.iloc[header_row:].copy()
    df.columns = df.iloc[0]
    df = df.iloc[1:].reset_index(drop=True)

    locus_cols = {
        "A":    ("A/1",    "A/2"),
        "B":    ("B/1",    "B/2"),
        "C":    ("C/1",    "C/2"),
        "DPB1": ("DPB1/1", "DPB1/2"),
        "DQB1": ("DQB1/1", "DQB1/2"),
        "DRB1": ("DRB1/1", "DRB1/2"),
    }

    results = {}
    for _, row in df.iterrows():
        sample = _clean_str(row.get("SampleName", ""))
        if not sample or sample == "nan":
            continue
        hla = {}
        for locus, (c1, c2) in locus_cols.items():
            a1 = _clean_allele(str(row.get(c1, "-")))
            a2 = _clean_allele(str(row.get(c2, "-")))
            if a1 and not a2:
                a2 = a1
            hla[locus] = [a1, a2]
        remarks = _clean_str(row.get("Comments", ""))
        results[sample] = {"hla": hla, "remarks": remarks}

    return results



def _parse_surfseq_results(df_csv: pd.DataFrame) -> dict:
    LOCUS_MAP = {
        "HLA_A": "A", "HLA_B": "B", "HLA_C": "C",
        "DRB1": "DRB1", "DRB3": "DRB3", "DRB4": "DRB3", "DRB5": "DRB3",
        "DQB1": "DQB1", "DPB1": "DPB1",
    }

    raw_results = {}

    for _, row in df_csv.iterrows():
        col_a = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        col_b = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""

        if not col_a or col_a == "nan" or ";" not in col_a:
            continue

        raw_tokens = [t.strip().strip('"').strip("'") for t in col_a.split(";")]
        if col_b and col_b not in ("nan", ""):
            raw_tokens.append(col_b.strip().strip('"').strip("'"))

        barcode = raw_tokens[0] if raw_tokens else ""

        clean_tokens = []
        for t in raw_tokens[1:]:
            if not t:
                continue
            if re.search(r"_R[12]\b", t, re.I):
                continue
            if re.match(r"\d{6,}", t):
                continue
            clean_tokens.append(t)

        locus_raw = clean_tokens[0] if clean_tokens else ""
        locus = LOCUS_MAP.get(locus_raw)
        if not locus:
            continue

        raw_allele_tokens = [t for t in clean_tokens[1:] if t and t not in ("-", "nan")]
        if not raw_allele_tokens:
            continue

        allele_tokens = []
        for tok in raw_allele_tokens:
            sub = [s for s in tok.split() if s and "*" in s]
            if len(sub) > 1:
                allele_tokens.extend(sub)
            else:
                allele_tokens.append(tok)
        if not allele_tokens:
            continue

        m = re.search(r"HLA-(\d+)[A-Z]*[_\-]", barcode)
        if not m:
            m = re.search(r"[_\-](\d{4,9})[_\-]", barcode)
        if not m:
            continue
        sample_num = m.group(1)

        if sample_num not in raw_results:
            raw_results[sample_num] = {}
        if locus not in raw_results[sample_num]:
            raw_results[sample_num][locus] = []
        for allele_str in allele_tokens:
            raw_results[sample_num][locus].append(allele_str)

    results = {}
    for sample_num, loci in raw_results.items():
        hla = {}
        for locus, allele_list in loci.items():
            if len(allele_list) == 1:
                a1 = _clean_allele(allele_list[0])
                a2 = a1
            else:
                a1 = _clean_allele(allele_list[0])
                a2 = _clean_allele(allele_list[1]) if len(allele_list) > 1 else None
                if not a2 or a1 == a2:
                    a2 = a1
            hla[locus] = [a1, a2]
        results[sample_num] = {"hla": hla, "remarks": ""}

    return results



def _detect_report_type(patient_row: pd.Series, donor_rows: list) -> str:
    diag = _clean_str(patient_row.get("diagnosis", "")).upper()
    patient_rel = _clean_str(patient_row.get("relationship", "")).lower()

    if "RPL" in diag or "RECURRENT" in diag or "MISCARRIAGE" in diag or "RIF" in diag:
        return "rpl_couple"

    if donor_rows:
        donor_rels = [_clean_str(d.get("relationship", "")).lower() for d in donor_rows]
        is_couple = (
            patient_rel in ("wife", "husband")
            or any(r in ("wife", "husband") for r in donor_rels)
        )
        if is_couple:
            return "rpl_couple"
        return "transplant_donor"

    return "single_hla"



def _parse_match(val) -> str:
    s = _clean_str(val)
    if not s or s.lower() in ("nan", ""):
        return ""
    m = re.search(r"(\d+)\s+of\s+(\d+)", s, re.I)
    if m:
        matched, total = int(m.group(1)), int(m.group(2))
        pct = round(matched / total * 100) if total else 0
        qualifier = "at High Resolution" if "high resolution" in s.lower() else ""
        base = f"{matched} of {total} {qualifier}".strip()
        return f"{base} ({pct}%)"
    return s.strip()



def _build_gender_age(row) -> str:
    combined = _clean_str(row.get("gender / age", ""))
    if combined:
        return _sentence_case(combined)
    gender  = _sentence_case(row.get("gender", ""))
    raw_age = row.get("age", "")
    if isinstance(raw_age, (int, float)) and not pd.isna(raw_age):
        age = str(int(raw_age))
    else:
        age = _clean_str(raw_age)
    parts = [p for p in (gender, age) if p]
    return " / ".join(parts)



def _build_person(row: pd.Series, hla_lookup: dict, join_by: str) -> dict:
    if join_by == "pin":
        key = _clean_str(row.get("pin", ""))
    else:
        key = str(row.get("sample number", "")).strip().split(".")[0]

    hla_data = hla_lookup.get(key, {})
    hla = hla_data.get("hla", {locus: [None, None] for locus in ["A", "B", "C", "DRB1", "DQB1", "DPB1"]})
    remarks = hla_data.get("remarks", "")

    _insuff_re = re.compile(r"insufficient\s*data", re.IGNORECASE)
    _has_insufficient_hla = any(
        a and _insuff_re.search(str(a))
        for alleles in hla.values() for a in (alleles or [])
    )
    hla = {
        locus: [
            None if (a and _insuff_re.search(str(a))) else a
            for a in (alleles or [])
        ]
        for locus, alleles in hla.items()
    }

    c_alleles = hla.get("C", [None, None])
    ct1 = c_supertype(c_alleles[0]) if c_alleles[0] else None
    ct2 = c_supertype(c_alleles[1]) if c_alleles[1] else None
    hla_c_type = ",".join(filter(None, [ct1, ct2])) if (ct1 or ct2) else ""

    excel_remarks = _clean_str(row.get("remarks/comments", ""))
    combined_remarks = excel_remarks

    return {
        "name":           _sentence_case(row.get("name", "")),
        "gender_age":     _build_gender_age(row),
        "diagnosis":      _sentence_case(row.get("diagnosis", "")),
        "referred_by":    _sentence_case(row.get("referred by", "")),
        "hospital_clinic":_sentence_case(row.get("hospital/clinic", "")),
        "specimen":       _sentence_case(row.get("specimen", "")),
        "relationship":   _sentence_case(row.get("relationship", "")),
        "remarks":        _sentence_case(combined_remarks),
        "hospital_mr_no": _clean_str(row.get("hospital mr no", "")),
        "pin":            _clean_str(row.get("pin", "")),
        "sample_number":  str(row.get("sample number", "")).strip().split(".")[0],
        "collection_date":_fmt_date(row.get("collection date")),
        "receipt_date":   _fmt_date(row.get("sample receipt date")),
        "report_date":    _fmt_date(row.get("report date")),
        "match":          _parse_match(row.get("match", "")),
        "hla":                   hla,
        "hla_c_type":            hla_c_type,
        "_join_key":             key,
        "_has_insufficient_hla": _has_insufficient_hla,
    }



def compute_rpl_reference(patient: dict, donor: dict) -> dict:
    loci = ["A", "B", "C", "DRB1", "DQB1", "DPB1"]
    p_alleles = set()
    d_alleles = set()
    for locus in loci:
        for a in (patient["hla"].get(locus) or []):
            if a:
                p_alleles.add((locus, a))
        for a in (donor["hla"].get(locus) or []):
            if a:
                d_alleles.add((locus, a))

    match_str = donor.get("match", "")
    m = re.search(r"(\d+)\s+of\s+(\d+)", match_str or "", re.I)
    if m:
        matched = int(m.group(1))
        total = int(m.group(2))
    else:
        matched, total = 0, 12

    pct = round(matched / total * 100) if total else 0

    class2_p = set()
    class2_d = set()
    for locus in ["DRB1", "DQB1"]:
        for a in (patient["hla"].get(locus) or []):
            if a:
                class2_p.add((locus, a))
        for a in (donor["hla"].get(locus) or []):
            if a:
                class2_d.add((locus, a))
    class2_shared = len(class2_p & class2_d)
    class2_total = max(len(class2_p | class2_d), 1)
    class2_pct = round(class2_shared / 4 * 100)

    return {
        "match_str":    f"{matched} of {total}",
        "match_pct":    f"{pct}%",
        "class2_pct":   f"{class2_pct}%",
        "hla_sharing_rif": ">50%",
        "hla_c_patient": patient.get("hla_c_type", ""),
        "hla_c_donor":   donor.get("hla_c_type", ""),
    }



def _parse_cdc_result(val: str) -> str:
    s = _clean_str(val)
    if not s or s.lower() in ("nan", ""):
        return "Negative"
    m = re.match(r"([A-Za-z\s]+)", s.strip())
    return m.group(1).strip() if m else s


def _parse_dtt_val(val: str) -> str:
    s = _clean_str(val)
    m = re.search(r"\(([^)]+)\)", s)
    if m:
        inner = m.group(1).strip()
        return inner if inner.endswith("cells") else inner + " cells"
    return "<10% Dead cells"


def _iter_sheet_frames(filepath: str):
    if filepath.lower().endswith(".csv"):
        try:
            yield pd.read_csv(filepath, header=None)
        except Exception:
            pass
        return
    for sh in pd.ExcelFile(filepath).sheet_names:
        try:
            yield pd.read_excel(filepath, sheet_name=sh, header=None)
        except Exception:
            continue


def _read_crossmatch_sheet(filepath: str):
    for df in _iter_sheet_frames(filepath):
        if not df.empty and _lx_find_header(df, 2, "patient name") is not None:
            return df
    if not filepath.lower().endswith(".csv"):
        with pd.ExcelFile(filepath) as xls:
            if "Sheet2" in xls.sheet_names:
                return pd.read_excel(filepath, sheet_name="Sheet2", header=None)
    return None


def parse_cdc_excel(filepath: str, nabl: bool = True) -> list:
    df = _read_crossmatch_sheet(filepath)
    if df is None:
        return []

    header_row = None
    for i, row in df.iterrows():
        cell = str(row.iloc[2]).strip().lower()
        if "patient name" in cell:
            header_row = i
            break
    if header_row is None:
        return []

    def _rv(row, col):
        if row is None or col >= len(row):
            return ""
        return _clean_str(row.iloc[col])

    def _rd(row, col):
        if row is None or col >= len(row):
            return ""
        return _fmt_date(row.iloc[col])

    def _ga(row):
        gender = _sentence_case(_rv(row, 6))
        raw_age = row.iloc[5] if 5 < len(row) else ""
        if isinstance(raw_age, (int, float)) and not pd.isna(raw_age):
            age = str(int(raw_age))
        else:
            age = _clean_str(raw_age)
        return " / ".join(p for p in (gender, age) if p)

    cases = []
    current_patient = None
    current_donor   = None

    def _flush():
        nonlocal current_patient, current_donor
        if current_patient is None:
            return
        t_raw = _rv(current_patient, 17)
        b_raw = _rv(current_patient, 18)

        patient = {
            "name":            _sentence_case(_rv(current_patient, 2)),
            "gender_age":      _ga(current_patient),
            "pin":             _rv(current_patient, 7),
            "sample_number":   _rv(current_patient, 8),
            "diagnosis":       _sentence_case(_rv(current_patient, 9)) or "NA",
            "hospital_clinic": _sentence_case(_rv(current_patient, 11)),
            "sample_type":     _rv(current_patient, 10) or "Serum",
            "collection_date": _rd(current_patient, 12),
            "receipt_date":    _rd(current_patient, 13),
            "report_date":     _rd(current_patient, 14),
            "photo_bytes":     None,
            "hla": {}, "hla_c_type": "",
            "_join_key": _rv(current_patient, 8),
            "_has_insufficient_hla": False,
        }

        donor = {}
        if current_donor is not None:
            donor = {
                "name":            _sentence_case(_rv(current_donor, 2)),
                "gender_age":      _ga(current_donor),
                "pin":             _rv(current_donor, 7) or "NA",
                "sample_number":   _rv(current_donor, 8) or "NA",
                "relationship":    _sentence_case(_rv(current_donor, 4)),
                "sample_type":     _rv(current_donor, 10) or "Sodium Heparin Whole Blood",
                "collection_date": _rd(current_donor, 12),
                "receipt_date":    _rd(current_donor, 13),
                "report_date":     _rd(current_donor, 14),
                "photo_bytes":     None,
                "hla": {}, "hla_c_type": "",
                "_join_key": "", "_has_insufficient_hla": False,
            }

        dtt_t = _parse_dtt_val(t_raw)
        dtt_b = _parse_dtt_val(b_raw)

        cases.append({
            "report_type":     "cdc_crossmatch",
            "nabl":            nabl,
            "with_logo":       True,
            "signature_stamp": False,
            "methodology":     "", "imgt_release": "",
            "coverage":        "", "typing_status": "Complete",
            "reviewer":        "",
            "patient":         patient,
            "donors":          [donor] if donor else [],
            "rpl_reference":   {},
            "cdc_results": {
                "t_cell":        _parse_cdc_result(t_raw),
                "b_cell":        _parse_cdc_result(b_raw),
                "t_with_dtt":    dtt_t,
                "t_without_dtt": dtt_t,
                "b_with_dtt":    dtt_b,
                "b_without_dtt": dtt_b,
            },
        })
        current_patient = None
        current_donor   = None

    for i in range(header_row + 1, len(df)):
        row  = df.iloc[i]
        name = _clean_str(row.iloc[2])
        role = _clean_str(row.iloc[3]).lower().strip()
        if not name:
            continue
        if role.startswith("pati"):
            _flush()
            current_patient = row
            current_donor   = None
        elif "donor" in role and current_patient is not None:
            current_donor = row

    _flush()
    return cases



def parse_flow_excel(filepath: str, nabl: bool = True) -> list:
    df = _read_crossmatch_sheet(filepath)
    if df is None:
        return []

    header_row = None
    for i, row in df.iterrows():
        if "patient name" in str(row.iloc[2]).strip().lower():
            header_row = i
            break
    if header_row is None:
        return []

    def _rv(row, col):
        return _clean_str(row.iloc[col]) if col < len(row) else ""

    def _rd(row, col):
        return _fmt_date(row.iloc[col]) if col < len(row) else ""

    def _ga(row):
        gender = _sentence_case(_rv(row, 6))
        raw_age = row.iloc[5] if 5 < len(row) else ""
        age = str(int(raw_age)) if isinstance(raw_age, (int, float)) and not pd.isna(raw_age) \
              else _clean_str(raw_age)
        return " / ".join(p for p in (gender, age) if p)

    cases = []
    cur_pat = None
    cur_don = None

    def _flush():
        nonlocal cur_pat, cur_don
        if cur_pat is None:
            return
        patient = {
            "name":            _sentence_case(_rv(cur_pat, 2)),
            "gender_age":      _ga(cur_pat),
            "pin":             _rv(cur_pat, 7),
            "sample_number":   _rv(cur_pat, 8),
            "diagnosis":       _sentence_case(_rv(cur_pat, 9)) or "NA",
            "hospital_clinic": _sentence_case(_rv(cur_pat, 11)),
            "sample_type":     _rv(cur_pat, 10) or "Serum",
            "collection_date": _rd(cur_pat, 12),
            "receipt_date":    _rd(cur_pat, 13),
            "report_date":     _rd(cur_pat, 14),
            "remarks": "", "comments": "",
            "photo_bytes": None,
            "hla": {}, "hla_c_type": "",
            "_join_key": _rv(cur_pat, 8), "_has_insufficient_hla": False,
        }
        donor = {}
        if cur_don is not None:
            donor = {
                "name":            _sentence_case(_rv(cur_don, 2)),
                "gender_age":      _ga(cur_don),
                "pin":             _rv(cur_don, 7) or "NA",
                "sample_number":   _rv(cur_don, 8) or "NA",
                "relationship":    _sentence_case(_rv(cur_don, 4)),
                "sample_type":     _rv(cur_don, 10) or "Sodium Heparin Whole Blood",
                "collection_date": _rd(cur_don, 12),
                "receipt_date":    _rd(cur_don, 13),
                "report_date":     _rd(cur_don, 14),
                "photo_bytes": None,
                "hla": {}, "hla_c_type": "",
                "_join_key": "", "_has_insufficient_hla": False,
            }
        cases.append({
            "report_type":     "flow_crossmatch",
            "nabl":            nabl,
            "with_logo":       True,
            "signature_stamp": False,
            "methodology": "", "imgt_release": "",
            "coverage":    "", "typing_status": "Complete",
            "reviewer":    "",
            "patient":     patient,
            "donors":      [donor] if donor else [],
            "rpl_reference": {},
            "flow_results": {
                "t_antibody":       _rv(cur_pat, 17) or "T-CELLS (CD3)",
                "t_mcs":            _rv(cur_pat, 18) or "<45",
                "t_interpretation": _sentence_case(_rv(cur_pat, 19)) or "Negative",
                "b_antibody":       _rv(cur_don, 17) if cur_don is not None else "B-CELLS (CD19)",
                "b_mcs":            _rv(cur_don, 18) if cur_don is not None else "<86",
                "b_interpretation": _sentence_case(_rv(cur_don, 19)) if cur_don is not None else "Negative",
            },
        })
        cur_pat = None
        cur_don = None

    for i in range(header_row + 1, len(df)):
        row  = df.iloc[i]
        name = _clean_str(row.iloc[2])
        role = _clean_str(row.iloc[3]).lower().strip()
        if not name:
            continue
        if role.startswith("pati"):
            _flush()
            cur_pat = row
            cur_don = None
        elif "donor" in role and cur_pat is not None:
            cur_don = row

    _flush()
    return cases



def parse_dsa_excel(filepath: str, nabl: bool = True) -> list:
    df = _read_crossmatch_sheet(filepath)
    if df is None:
        return []

    header_row = None
    for i, row in df.iterrows():
        cell = str(row.iloc[2]).strip().lower()
        if "patient name" in cell:
            header_row = i
            break
    if header_row is None:
        return []

    def _rv(row, col):
        if row is None or col >= len(row): return ""
        return _clean_str(row.iloc[col])

    def _rd(row, col):
        if row is None or col >= len(row): return ""
        return _fmt_date(row.iloc[col])

    def _ga(row):
        gender = _sentence_case(_rv(row, 6))
        raw_age = row.iloc[5] if 5 < len(row) else ""
        if isinstance(raw_age, (int, float)) and not pd.isna(raw_age):
            age = str(int(raw_age))
        else:
            age = _clean_str(raw_age)
        return " / ".join(p for p in (gender, age) if p)

    cases = []
    current_patient = None
    current_donor   = None

    def _flush():
        nonlocal current_patient, current_donor
        if current_patient is None:
            return

        c1_result  = _rv(current_patient, 18).strip() or "Negative"
        c1_mfi     = _rv(current_patient, 19)
        c1_cutoff  = _rv(current_patient, 20) or ">1000"
        c2_result  = _rv(current_donor,   18).strip() or "Negative" if current_donor is not None else "Negative"
        c2_mfi     = _rv(current_donor,   19) if current_donor is not None else ""
        c2_cutoff  = _rv(current_donor,   20) or ">1000" if current_donor is not None else ">1000"

        patient = {
            "name":            _sentence_case(_rv(current_patient, 2)),
            "gender_age":      _ga(current_patient),
            "pin":             _rv(current_patient, 7),
            "sample_number":   _rv(current_patient, 8),
            "diagnosis":       _sentence_case(_rv(current_patient, 9)) or "NA",
            "hospital_clinic": _sentence_case(_rv(current_patient, 11)),
            "sample_type":     _rv(current_patient, 10) or "Serum",
            "collection_date": _rd(current_patient, 12),
            "receipt_date":    _rd(current_patient, 13),
            "report_date":     _rd(current_patient, 14),
            "photo_bytes":     None,
            "hla": {}, "hla_c_type": "",
            "_join_key": _rv(current_patient, 8),
            "_has_insufficient_hla": False,
        }

        donor = {}
        if current_donor is not None:
            donor = {
                "name":            _sentence_case(_rv(current_donor, 2)),
                "gender_age":      _ga(current_donor),
                "pin":             _rv(current_donor, 7) or "NA",
                "sample_number":   _rv(current_donor, 8) or "NA",
                "relationship":    _sentence_case(_rv(current_donor, 4)),
                "sample_type":     _rv(current_donor, 10) or "ACD Tube",
                "collection_date": _rd(current_donor, 12),
                "receipt_date":    _rd(current_donor, 13),
                "report_date":     _rd(current_donor, 14),
                "photo_bytes":     None,
                "hla": {}, "hla_c_type": "",
                "_join_key": "", "_has_insufficient_hla": False,
            }

        cases.append({
            "report_type":     "dsa_crossmatch",
            "nabl":            nabl,
            "with_logo":       True,
            "signature_stamp": False,
            "methodology":     "", "imgt_release": "",
            "coverage":        "", "typing_status": "Complete",
            "reviewer":        "",
            "patient":         patient,
            "donors":          [donor] if donor else [],
            "rpl_reference":   {},
            "dsa_results": {
                "class1_result":  c1_result,
                "class1_mfi":     c1_mfi,
                "class1_cutoff":  c1_cutoff,
                "class2_result":  c2_result,
                "class2_mfi":     c2_mfi,
                "class2_cutoff":  c2_cutoff,
            },
        })
        current_patient = None
        current_donor   = None

    for i in range(header_row + 1, len(df)):
        row  = df.iloc[i]
        name = _clean_str(row.iloc[2])
        role = _clean_str(row.iloc[3]).lower().strip()
        if not name:
            continue
        if role.startswith("pati"):
            _flush()
            current_patient = row
            current_donor   = None
        elif "donor" in role and current_patient is not None:
            current_donor = row

    _flush()
    return cases



def _lx_find_header(df, col, text):
    target = text.lower().replace(" ", "")
    for i in range(min(len(df), 30)):
        if col < df.shape[1]:
            cell = _clean_str(df.iloc[i, col]).lower().replace(" ", "")
            if cell == target:
                return i
    return None


def _lx_result_lookup(df) -> dict:
    hdr = _lx_find_header(df, 0, "samplename")
    if hdr is None:
        return {}
    headers = [_clean_str(df.iloc[hdr, c]) for c in range(df.shape[1])]

    is_format2 = any(re.match(r"^[A-Za-z0-9]+\s*/\s*[12]$", h) for h in headers)

    lookup: dict = {}
    if is_format2:
        col_map = {}
        for c, h in enumerate(headers):
            m = re.match(r"^([A-Za-z0-9]+)\s*/\s*([12])$", h)
            if m:
                col_map[c] = (m.group(1).upper(), int(m.group(2)) - 1)
        for i in range(hdr + 1, len(df)):
            sn = _clean_str(df.iloc[i, 0])
            if not sn:
                continue
            person = {}
            for c, (locus, slot) in col_map.items():
                person.setdefault(locus, ["", ""])[slot] = _clean_str(df.iloc[i, c])
            lookup[sn] = person
    else:
        loci_cols = {}
        for c in range(2, df.shape[1]):
            key = headers[c].upper().replace("HLA-", "").replace("*", "").strip()
            if key:
                loci_cols[c] = key
        cur = None
        for i in range(hdr + 1, len(df)):
            sn = _clean_str(df.iloc[i, 0])
            if sn:
                cur = sn
                lookup.setdefault(cur, {})
            if cur is None:
                continue
            for c, key in loci_cols.items():
                val = _clean_str(df.iloc[i, c])
                if val:
                    lookup[cur].setdefault(key, []).append(val)
    return lookup


def parse_luminex_excel(filepath: str, nabl: bool = True) -> list:
    demo_df    = None
    hla_lookup: dict = {}
    for df in _iter_sheet_frames(filepath):
        if df.empty:
            continue
        if demo_df is None and _lx_find_header(df, 2, "patient name") is not None:
            demo_df = df
        elif _lx_find_header(df, 0, "samplename") is not None:
            hla_lookup.update(_lx_result_lookup(df))

    if demo_df is None:
        return []

    df = demo_df
    header_row = _lx_find_header(df, 2, "patient name")

    def _rv(row, col):
        if row is None or col >= len(row): return ""
        return _clean_str(row.iloc[col])

    def _rd(row, col):
        if row is None or col >= len(row): return ""
        return _fmt_date(row.iloc[col])

    def _ga(row):
        gender = _sentence_case(_rv(row, 6))
        raw_age = row.iloc[5] if 5 < len(row) else ""
        if isinstance(raw_age, (int, float)) and not pd.isna(raw_age):
            age = str(int(raw_age))
        else:
            age = _clean_str(raw_age)
        return " / ".join(p for p in (gender, age) if p)

    def _person(row):
        pin = _rv(row, 7)
        return {
            "name":            _sentence_case(_rv(row, 2)),
            "gender_age":      _ga(row),
            "pin":             pin or "NA",
            "sample_number":   _rv(row, 8) or "NA",
            "relation":        _sentence_case(_rv(row, 4)),
            "diagnosis":       _sentence_case(_rv(row, 9)) or "NA",
            "hospital_clinic": _sentence_case(_rv(row, 11)),
            "sample_type":     _rv(row, 10) or "EDTA Blood",
            "collection_date": _rd(row, 12),
            "receipt_date":    _rd(row, 13),
            "report_date":     _rd(row, 14),
            "photo_bytes":     None,
            "hla":             hla_lookup.get(pin, {}),
            "hla_c_type":      "",
            "_join_key":       pin,
            "_has_insufficient_hla": False,
        }

    cases = []
    current_patient = None
    current_donors  = []

    def _flush():
        nonlocal current_patient, current_donors
        if current_patient is None:
            return
        cases.append({
            "report_type":     "luminex_typing",
            "nabl":            nabl,
            "with_logo":       True,
            "signature_stamp": False,
            "methodology":     "", "imgt_release": "",
            "coverage":        "", "typing_status": "Complete",
            "reviewer":        "",
            "patient":         _person(current_patient),
            "donors":          [_person(d) for d in current_donors],
            "rpl_reference":   {},
            "luminex_interpretation": "",
            "luminex_pat_photo": None,
            "luminex_don_photo": None,
        })
        current_patient = None
        current_donors  = []

    for i in range(header_row + 1, len(df)):
        row  = df.iloc[i]
        name = _clean_str(row.iloc[2]) if 2 < len(row) else ""
        role = (_clean_str(row.iloc[3]) if 3 < len(row) else "").lower().strip()
        if not name:
            continue
        if role.startswith("pati"):
            _flush()
            current_patient = row
            current_donors  = []
        elif "donor" in role and current_patient is not None:
            current_donors.append(row)

    _flush()
    return cases


def _normalize_age_token(age: str) -> str:
    s = _clean_str(age)
    if not s:
        return s
    m = re.search(r'(\d+)\s*y', s, re.I)
    if m:
        n = int(m.group(1))
        return f"{n} {'Year' if n == 1 else 'Years'}"
    m = re.search(r'(\d+)\s*m', s, re.I)
    if m:
        n = int(m.group(1))
        return f"{n} {'Month' if n == 1 else 'Months'}"
    m = re.search(r'\d+', s)
    if m:
        n = int(m.group())
        return f"{n} {'Year' if n == 1 else 'Years'}"
    return s


def parse_pra_excel(filepath: str, nabl: bool = True) -> list:
    fname_upper = os.path.basename(filepath).upper()
    is_class2 = any(tok in fname_upper for tok in ("PRA II", "PRA2", "PRA_2",
                                                   "CLASS II", "CLASS2", "CLASS_2"))
    rtype = "pra_class2" if is_class2 else "pra_class1"
    cls   = "II" if is_class2 else "I"

    df = header_row = None
    for cand in _iter_sheet_frames(filepath):
        for i, row in cand.iterrows():
            if any(isinstance(v, str) and v.strip().lower().startswith("patient")
                   for v in row):
                df, header_row = cand, i
                break
        if header_row is not None:
            break
    if df is None or header_row is None:
        return []

    col = {}
    for c, v in enumerate(df.iloc[header_row]):
        if isinstance(v, str):
            col[_norm_col(v)] = c

    def _ci(*names):
        for n in names:
            if n in col:
                return col[n]
        return None

    c_name   = _ci("patient", "patient name")
    c_ga     = _ci("gender/age", "gender / age", "gender age")
    c_pin    = _ci("pin")
    c_sample = _ci("sample number")
    c_spec   = _ci("specimen", "sample type")
    c_hosp   = _ci("hospital/clinic", "hospital / clinic")
    c_coll   = _ci("sample collection date", "date of collection", "collection date")
    c_recv   = _ci("sample receipt date", "receipt date")
    c_rep    = _ci("report date")
    c_pct    = _ci("percentage", "pra percentage", "pra %", "% pra", "pra")

    def _rv(row, c):
        return _clean_str(row.iloc[c]) if c is not None and c < len(row) else ""

    def _rd(row, c):
        return _fmt_date(row.iloc[c]) if c is not None and c < len(row) else ""

    def _rpct(row, c):
        if c is None or c >= len(row):
            return ""
        raw = row.iloc[c]
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return ""
        s = _clean_str(raw).replace("%", "").strip()
        if not s:
            return ""
        try:
            v = float(s)
        except ValueError:
            return s
        if 0 < v <= 1:
            v *= 100
        return str(int(round(v))) if abs(v - round(v)) < 1e-9 else f"{v:g}"

    cases = []
    for i in range(header_row + 1, len(df)):
        row  = df.iloc[i]
        name = _sentence_case(_rv(row, c_name))
        if not name:
            continue
        gender, age = "", ""
        ga = _rv(row, c_ga)
        if ga:
            parts = re.split(r"[/\\]", ga, maxsplit=1)
            gender = _sentence_case(parts[0])
            age    = _normalize_age_token(parts[1]) if len(parts) > 1 else ""
        patient = {
            "name":            name,
            "gender":          gender,
            "age":             age,
            "specimen":        _rv(row, c_spec) or "Serum",
            "hospital_clinic": _sentence_case(_rv(row, c_hosp)),
            "pin":             _rv(row, c_pin),
            "sample_number":   _rv(row, c_sample),
            "collection_date": _rd(row, c_coll),
            "receipt_date":    _rd(row, c_recv),
            "report_date":     _rd(row, c_rep),
            "hla": {}, "hla_c_type": "",
            "_join_key": _rv(row, c_pin),
            "_has_insufficient_hla": False,
        }
        cases.append({
            "report_type":     rtype,
            "nabl":            nabl,
            "with_logo":       True,
            "signature_stamp": False,
            "methodology":     "", "imgt_release": "",
            "coverage":        "", "typing_status": "Complete",
            "reviewer":        "",
            "patient":         patient,
            "donors":          [],
            "rpl_reference":   {},
            "pra_class":       cls,
            "pra_percentage":  _rpct(row, c_pct),
            "pra_result":      "",
        })
    return cases


def parse_kir_excel(filepath: str, nabl: bool = True) -> list:
    df = header_row = None
    for cand in _iter_sheet_frames(filepath):
        for i, row in cand.iterrows():
            if any(isinstance(v, str) and v.strip().lower().startswith("patient")
                   for v in row):
                df, header_row = cand, i
                break
        if header_row is not None:
            break
    if df is None or header_row is None:
        return []

    col = {}
    for c, v in enumerate(df.iloc[header_row]):
        if isinstance(v, str):
            col[_norm_col(v)] = c

    def _ci(*names):
        for n in names:
            if n in col:
                return col[n]
        return None

    c_name   = _ci("patient", "patient name")
    c_ga     = _ci("gender / age", "gender/age", "gender age")
    c_mr     = _ci("hospital mr no", "hospital mr no.", "mr no")
    c_spec   = _ci("specimen", "sample type")
    c_hosp   = _ci("hospital/clinic", "hospital / clinic")
    c_pin    = _ci("pin")
    c_sample = _ci("sample number")
    c_coll   = _ci("sample collection date", "date of collection", "collection date")
    c_recv   = _ci("sample receipt date", "receipt date")
    c_rep    = _ci("report date")

    def _rv(row, c):
        return _clean_str(row.iloc[c]) if c is not None and c < len(row) else ""

    def _rd(row, c):
        return _fmt_date(row.iloc[c]) if c is not None and c < len(row) else ""

    cases = []
    for i in range(header_row + 1, len(df)):
        row  = df.iloc[i]
        name = _sentence_case(_rv(row, c_name))
        if not name:
            continue
        patient = {
            "name":            name,
            "gender_age":      _rv(row, c_ga),
            "hospital_mr_no":  _rv(row, c_mr) or "NA",
            "specimen":        _rv(row, c_spec) or "Blood EDTA",
            "hospital_clinic": _sentence_case(_rv(row, c_hosp)),
            "pin":             _rv(row, c_pin),
            "sample_number":   _rv(row, c_sample),
            "collection_date": _rd(row, c_coll),
            "receipt_date":    _rd(row, c_recv),
            "report_date":     _rd(row, c_rep),
            "hla": {}, "hla_c_type": "",
            "_join_key": _rv(row, c_pin),
            "_has_insufficient_hla": False,
        }
        cases.append({
            "report_type":     "kir_genotyping",
            "nabl":            nabl,
            "with_logo":       True,
            "signature_stamp": False,
            "methodology":     "", "imgt_release": "",
            "coverage":        "", "typing_status": "Complete",
            "reviewer":        "",
            "patient":         patient,
            "donors":          [],
            "rpl_reference":   {},
            "kir_genes":             {},
            "kir_genotype_override": "Auto",
            "kir_interpretation":    "",
        })
    return cases



def _parse_patient_list_csv(filepath: str, nabl: bool = True) -> list:
    try:
        df = pd.read_csv(filepath)
    except Exception:
        return []
    df.columns = [_norm_col(c) for c in df.columns]
    if "patient name" not in df.columns or "patient no" not in df.columns:
        return []

    cases = []
    for _, row in df.iterrows():
        name = _clean_str(row.get("patient name", ""))
        if not name:
            continue
        patient_dict = {
            "name":            _sentence_case(name),
            "gender_age":      _build_gender_age(row),
            "diagnosis":       "",
            "referred_by":     "",
            "hospital_clinic": "",
            "specimen":        "",
            "relationship":    "",
            "remarks":         "",
            "hospital_mr_no":  "",
            "pin":             _clean_str(row.get("patient no", "")),
            "sample_number":   "",
            "collection_date": "",
            "receipt_date":    _fmt_date(row.get("sample receipt date", "")),
            "report_date":     "",
            "match":           "",
            "hla":                   {locus: [None, None] for locus in ["A", "B", "C", "DRB1", "DQB1", "DPB1"]},
            "hla_c_type":            "",
            "_join_key":             "",
            "_has_insufficient_hla": False,
        }
        cases.append({
            "report_type":     "single_hla",
            "nabl":            nabl,
            "with_logo":       True,
            "signature_stamp": False,
            "methodology":     "",
            "imgt_release":    "",
            "coverage":        "",
            "typing_status":   "",
            "reviewer":        "",
            "patient":         patient_dict,
            "donors":          [],
            "rpl_reference":   {},
        })
    return cases


def parse_excel(filepath: str, nabl: bool = True) -> list:
    is_csv = filepath.lower().endswith(".csv")
    if is_csv:
        patient_list_cases = _parse_patient_list_csv(filepath, nabl)
        if patient_list_cases:
            return patient_list_cases
    xl_sheets = [] if is_csv else pd.ExcelFile(filepath).sheet_names
    if "patient-donor detail" not in xl_sheets:
        fname_upper = os.path.basename(filepath).upper()

        if "LUMINEX" in fname_upper:
            return parse_luminex_excel(filepath, nabl)
        if "KIR" in fname_upper:
            return parse_kir_excel(filepath, nabl)
        if "PRA" in fname_upper:
            return parse_pra_excel(filepath, nabl)
        if "DSA" in fname_upper:
            return parse_dsa_excel(filepath, nabl)
        if "FLOW" in fname_upper and "CDC" not in fname_upper:
            return parse_flow_excel(filepath, nabl)
        if "CDC" in fname_upper:
            return parse_cdc_excel(filepath, nabl)

        for sh in xl_sheets:
            try:
                df_sh = pd.read_excel(filepath, sheet_name=sh, header=None, nrows=30)
            except Exception:
                continue
            if not df_sh.empty and _lx_find_header(df_sh, 0, "samplename") is not None:
                return parse_luminex_excel(filepath, nabl)

        demo_df = _read_crossmatch_sheet(filepath)
        sheet_text = ""
        if demo_df is not None:
            sheet_text = " ".join(
                str(v).lower()
                for v in demo_df.head(20).values.flatten()
                if v is not None and str(v) != "nan"
            )

        if "donor specific" in sheet_text or " dsa " in sheet_text:
            return parse_dsa_excel(filepath, nabl)
        if "flow cytometry" in sheet_text or "flow cross" in sheet_text:
            return parse_flow_excel(filepath, nabl)
        return parse_cdc_excel(filepath, nabl)
    fname_upper = filepath.upper()
    is_miniseq = "MINISEQ" in fname_upper
    join_by = "pin" if is_miniseq else "sample_number"

    df_pd = pd.read_excel(filepath, sheet_name="patient-donor detail", header=0)
    df_pd.columns = [_norm_col(c) for c in df_pd.columns]

    if is_miniseq:
        df_res = pd.read_excel(filepath, sheet_name="result data", header=None)
        hla_lookup = _parse_miniseq_results(df_res)
        if hla_lookup and all(k.isdigit() for k in hla_lookup.keys()):
            join_by = "sample_number"
    else:
        df_csv = pd.read_excel(filepath, sheet_name="complete csv data", header=None)
        hla_lookup = _parse_surfseq_results(df_csv)

    cases = []
    current_patient = None
    current_donors = []

    def _flush():
        nonlocal current_patient, current_donors
        if current_patient is None:
            return
        report_type = _detect_report_type(current_patient["_row"], current_donors)

        patient_dict = _build_person(current_patient["_row"], hla_lookup, join_by)

        donors = []
        for d_row in current_donors:
            donors.append(_build_person(d_row, hla_lookup, join_by))

        rpl_ref = {}
        if report_type == "rpl_couple" and donors:
            rpl_ref = compute_rpl_reference(patient_dict, donors[0])

        row0 = current_patient["_row"]
        methodology   = _clean_str(row0.get("methodology", ""))
        imgt_release  = _clean_str(row0.get("imgt/hla release", ""))
        coverage      = _clean_str(row0.get("coverage", ""))
        typing_status = _clean_str(row0.get("typing status complete/incomplete", ""))
        reviewer      = _clean_str(row0.get("this report has been reviewed and approved by", ""))

        cases.append({
            "report_type":    report_type,
            "nabl":           nabl,
            "with_logo":      True,
            "signature_stamp": False,
            "methodology":    methodology,
            "imgt_release":   imgt_release,
            "coverage":       coverage,
            "typing_status":  typing_status if typing_status else "Complete",
            "reviewer":       reviewer,
            "patient":        patient_dict,
            "donors":         donors,
            "rpl_reference":  rpl_ref,
        })

        current_patient = None
        current_donors = []

    for _, row in df_pd.iterrows():
        role = _clean_str(row.get("patient/donor", "")).lower()
        name = _clean_str(row.get("name", ""))
        if not name:
            continue

        if role.startswith("pati"):
            _flush()
            current_patient = {"_row": row}
        elif role == "donor" and current_patient is not None:
            current_donors.append(row)

    _flush()

    return cases


def get_case_summary(cases: list) -> list:
    summary = []
    for i, case in enumerate(cases):
        p = case["patient"]
        donor_names = [d["name"] for d in case["donors"]]
        summary.append({
            "index":       i,
            "patient":     p["name"],
            "donors":      ", ".join(donor_names) if donor_names else "—",
            "report_type": case["report_type"],
            "diagnosis":   p["diagnosis"],
            "report_date": p["report_date"],
            "nabl":        case["nabl"],
            "status":      case.get("typing_status", "Complete"),
        })
    return summary



if __name__ == "__main__":
    import json, sys

    files = [
        ("/data/Sethu/HLA-Typing-Report/TRANSPLANT MINISEQ SAMPLES DATA - SOFTWARE REPORT PREPARE.xlsx", True),
        ("/data/Sethu/HLA-Typing-Report/TRANSPLANT SURFSEQ SAMPLES DATA - SOFTWARE REPORT PREPARE.xlsx", False),
    ]

    for fpath, nabl in files:
        print(f"\n{'='*60}")
        print(f"Parsing: {fpath.split('/')[-1]}")
        cases = parse_excel(fpath, nabl=nabl)
        print(f"Found {len(cases)} cases:")
        for c in cases:
            p = c["patient"]
            donors = c["donors"]
            print(f"\n  Case: {p['name']} | type={c['report_type']} | nabl={c['nabl']}")
            print(f"    PIN={p['pin']}  SampleNo={p['sample_number']}")
            print(f"    Diagnosis: {p['diagnosis']}")
            print(f"    Report date: {p['report_date']}")
            for locus, alleles in p["hla"].items():
                a1, a2 = alleles
                print(f"    {locus:6s}: {a1 or '-':30s}  {a2 or '-'}")
            for d in donors:
                print(f"    DONOR: {d['name']} | rel={d['relationship']} | match={d['match']}")
                for locus, alleles in d["hla"].items():
                    a1, a2 = alleles
                    print(f"      {locus:6s}: {a1 or '-':30s}  {a2 or '-'}")
            if c["rpl_reference"]:
                print(f"    RPL ref: {c['rpl_reference']}")
