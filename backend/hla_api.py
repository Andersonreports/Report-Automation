
import os
import io
import re
import copy
import json
import uuid
import base64
import shutil
import traceback
from typing import Optional

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from hla_template import generate_pdf, make_filename, unique_output_path
from hla_data_parser import (
    parse_excel, get_case_summary,
    c_supertype, compute_rpl_reference,
    parse_patient_and_result_csv,
    parse_result_csv, _parse_patient_list_csv,
)
from hla_sab_parser import parse_sab_excel, parse_sab_allele_text, sab_pra_sentence
import hla_assets

_BASE       = os.path.dirname(os.path.abspath(__file__))
HLA_REPORT_DIR = os.path.join(_BASE, "reports-hla")
HLA_TEMP_DIR   = os.path.join(_BASE, "temp")
HLA_DRAFT_DIR  = os.path.join(_BASE, "drafts", "HLA")
HLA_UPLOAD_DIR = os.path.join(_BASE, "uploads", "hla_excel")
HLA_SAB_UPLOAD_DIR = os.path.join(_BASE, "uploads", "hla_sab_excel")
HLA_SETTINGS_FILE = os.path.join(_BASE, "drafts", "HLA", "hla_settings.json")

for d in (HLA_REPORT_DIR, HLA_TEMP_DIR, HLA_DRAFT_DIR, HLA_UPLOAD_DIR, HLA_SAB_UPLOAD_DIR):
    os.makedirs(d, exist_ok=True)

router = APIRouter(prefix="/hla", tags=["hla"])

REPORT_TEMPLATES = [
    {"name": "With CL",                                    "report_type": "single_hla"},
    {"name": "RPL",                                        "report_type": "rpl_couple"},
    {"name": "Single RPL",                                 "report_type": "single_rpl"},
    {"name": "Single Locus",                               "report_type": "single_locus"},
    {"name": "HLA-C",                                      "report_type": "hla_c"},
    {"name": "HLA Typing High Resolution (Transplant Donor)", "report_type": "transplant_donor"},
    {"name": "HLA (NGS with Photo)",                       "report_type": "ngs_photo"},
    {"name": "HLA Typing High Resolution (11 Loci)",       "report_type": "loci11"},
    {"name": "CDC",                                        "report_type": "cdc_crossmatch"},
    {"name": "DSA",                                        "report_type": "dsa_crossmatch"},
    {"name": "SAB Class I",                                "report_type": "sab_class1"},
    {"name": "SAB Class II",                               "report_type": "sab_class2"},
    {"name": "Flow",                                       "report_type": "flow_crossmatch"},
    {"name": "HLA Typing (Luminex)",                       "report_type": "luminex_typing"},
    {"name": "KIR Genotyping",                             "report_type": "kir_genotyping"},
    {"name": "PRA Class I",                                "report_type": "pra_class1"},
    {"name": "PRA Class II",                               "report_type": "pra_class2"},
    {"name": "Mixed PRA",                                  "report_type": "mixed_pra"},
]
TEMPLATE_NAMES    = [t["name"]        for t in REPORT_TEMPLATES]
TEMPLATE_TO_RTYPE = {t["name"]:        t["report_type"] for t in REPORT_TEMPLATES}
RTYPE_TO_TEMPLATE = {t["report_type"]: t["name"]        for t in REPORT_TEMPLATES}

DEFAULT_SIG_COUNTS = {
    "single_hla":       3,
    "rpl_couple":       2,
    "single_rpl":       2,
    "single_locus":     2,
    "hla_c":            2,
    "transplant_donor": 2,
    "ngs_photo":        2,
    "loci11":           3,
    "cdc_crossmatch":   2,
    "dsa_crossmatch":   2,
    "sab_class1":       2,
    "sab_class2":       2,
    "flow_crossmatch":  2,
    "luminex_typing":   2,
    "kir_genotyping":   2,
    "pra_class1":       2,
    "pra_class2":       2,
    "mixed_pra":        2,
}

DEFAULT_SIGNATORIES = [
    {"name": "Ms. S Aruna Devi",      "title": "Team Lead – Transplant Immunogenetics<br/>(Reviewed By)"},
    {"name": "Nikhala Shree S, Ph.D", "title": "Molecular Biologist"},
    {"name": "Dr. B. Rayvathy",       "title": "Consultant Microbiologist"},
]

HLA_LOCI = ["A", "B", "C", "DRB1", "DQB1", "DPB1", "DRB3", "DPA1", "DQA1"]



def _load_settings() -> dict:
    if os.path.exists(HLA_SETTINGS_FILE):
        try:
            with open(HLA_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_settings_file(data: dict):
    with open(HLA_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_signatories() -> list:
    s = _load_settings()
    return s.get("signatories", DEFAULT_SIGNATORIES)


def _get_sig_counts() -> dict:
    s = _load_settings()
    counts = dict(DEFAULT_SIG_COUNTS)
    counts.update(s.get("sig_counts", {}))
    return counts



def _decode_b64_field(obj: dict, key: str) -> None:
    val = obj.get(key)
    if isinstance(val, str) and val:
        try:
            obj[key] = base64.b64decode(val)
        except Exception:
            obj[key] = None


def _auto_compute_derived_fields(case: dict) -> None:
    rtype = case.get("report_type", "")
    if rtype == "rpl_couple":
        ref = case.get("rpl_reference") or {}
        if not (ref.get("match_str") or "").strip():
            patient = case.get("patient", {})
            donors  = case.get("donors", [])
            donor   = donors[0] if donors else {}
            try:
                computed = compute_rpl_reference(patient, donor)
            except Exception:
                computed = {}
            match_override  = (ref.get("match_pct_override") or "").strip()
            class2_override = (ref.get("class2_pct_override") or "").strip()
            if match_override:
                computed["match_pct"] = match_override if match_override.endswith("%") else f"{match_override}%"
            if class2_override:
                computed["class2_pct"] = class2_override if class2_override.endswith("%") else f"{class2_override}%"
            case["rpl_reference"] = computed
    elif rtype == "single_rpl":
        ref = case.get("rpl_reference") or {}
        if not (ref.get("hla_c_patient") or "").strip():
            patient = case.get("patient", {})
            pc = (patient.get("hla") or {}).get("HLA-C", ["", ""])
            try:
                ct1 = c_supertype(pc[0]) if pc and pc[0] else None
                ct2 = c_supertype(pc[1]) if pc and len(pc) > 1 and pc[1] else None
                parts = [s for s in [ct1, ct2] if s]
                case.setdefault("rpl_reference", {})["hla_c_patient"] = ", ".join(parts) if parts else ""
            except Exception:
                pass


def _decode_case_binary_fields(case: dict) -> None:
    _decode_b64_field(case, "sab_chart_bytes")
    if isinstance(case.get("patient"), dict):
        _decode_b64_field(case["patient"], "photo_bytes")
    for d in case.get("donors", []):
        if isinstance(d, dict):
            _decode_b64_field(d, "photo_bytes")
    _decode_b64_field(case, "luminex_pat_photo")
    _decode_b64_field(case, "luminex_don_photo")



def _build_signatories(report_type: str, nabl: bool, sig_counts: dict,
                       signatories: list, sig_name_overrides: dict = None) -> list:
    n = sig_counts.get(report_type, DEFAULT_SIG_COUNTS.get(report_type, 2))
    sig_source = (hla_assets.get_default_signatories(report_type, nabl)
                  if report_type == "loci11"
                  else signatories)
    out = []
    for sig in sig_source[:n]:
        sign_info = hla_assets.SIGN_BY_NAME.get(sig["name"])
        if sign_info is None:
            sign_info = next(iter(hla_assets.SIGN_BY_NAME.values()))
        entry = {
            "name":     sig["name"],
            "title":    sig["title"],
            "sign_b64": sign_info["sign_b64"],
            "is_png":   sign_info["is_png"],
        }
        out.append(entry)
    if sig_name_overrides:
        _title_lookup = {s["name"]: s["title"] for s in DEFAULT_SIGNATORIES}
        for slot_str, sig_name in sig_name_overrides.items():
            try:
                slot_i = int(slot_str)
                sign_info = hla_assets.SIGN_BY_NAME.get(sig_name)
                if sign_info and 0 <= slot_i < len(out):
                    out[slot_i]["sign_b64"] = sign_info["sign_b64"]
                    out[slot_i]["is_png"]   = sign_info["is_png"]
                    out[slot_i]["name"]     = sig_name
                    if sig_name in _title_lookup:
                        out[slot_i]["title"] = _title_lookup[sig_name]
            except Exception:
                pass
    return out



def _has_insufficient_data(person: dict) -> bool:
    if person.get("_has_insufficient_hla", False):
        return True
    import re
    hla = person.get("hla", {})
    for alleles in hla.values():
        for a in (alleles or []):
            if a and re.search(r"insufficient\s*data", str(a), re.IGNORECASE):
                return True
    return False



@router.get("/templates")
def get_templates():
    return {"templates": REPORT_TEMPLATES, "sig_names": list(hla_assets.SIGN_BY_NAME.keys())}


@router.get("/settings")
def get_settings():
    s = _load_settings()
    return {
        "signatories": s.get("signatories", DEFAULT_SIGNATORIES),
        "sig_counts":  {**DEFAULT_SIG_COUNTS, **s.get("sig_counts", {})},
        "with_logo":   s.get("with_logo", True),
        "nabl":        s.get("nabl", True),
        "signature_stamp": s.get("signature_stamp", False),
    }


@router.post("/settings")
async def save_settings(request_body: dict):
    existing = _load_settings()
    existing.update(request_body)
    _save_settings_file(existing)
    return {"ok": True}


@router.post("/preview")
async def preview(request_body: dict):
    case = request_body.get("case", {})
    if not case:
        raise HTTPException(400, "case is required")

    settings = _load_settings()
    sig_counts   = {**DEFAULT_SIG_COUNTS, **settings.get("sig_counts", {})}
    signatories  = settings.get("signatories", DEFAULT_SIGNATORIES)
    rtype        = case.get("report_type", "single_hla")
    nabl         = case.get("nabl", True)
    sig_stamp    = case.get("signature_stamp", settings.get("signature_stamp", False))

    c = copy.deepcopy(case)
    _decode_case_binary_fields(c)
    _auto_compute_derived_fields(c)
    c["signatories"]  = _build_signatories(rtype, nabl, sig_counts, signatories,
                                            c.pop("sig_name_overrides", {}))
    if sig_stamp and any("rayvathy" in s["name"].lower() for s in c["signatories"]):
        for s in c["signatories"]:
            if "rayvathy" in s["name"].lower():
                s["seal_b64"] = hla_assets.SEAL_REVATHY_B64

    try:
        fname = make_filename(c)
    except Exception:
        fname = "preview"
    file_id  = f"{fname}_{uuid.uuid4().hex[:8]}.pdf"
    tmp_path = os.path.join(HLA_TEMP_DIR, file_id)

    try:
        generate_pdf(c, tmp_path)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))

    return {"preview_url": f"/hla/preview-file/{file_id}"}


@router.get("/preview-file/{filename}")
def preview_file(filename: str):
    path = os.path.join(HLA_TEMP_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Preview not found")
    return FileResponse(path, media_type="application/pdf")


@router.post("/generate")
async def generate(request_body: dict):
    case       = request_body.get("case", {})
    output_dir = request_body.get("output_dir") or None
    if not case:
        raise HTTPException(400, "case is required")

    settings    = _load_settings()
    sig_counts  = {**DEFAULT_SIG_COUNTS, **settings.get("sig_counts", {})}
    signatories = settings.get("signatories", DEFAULT_SIGNATORIES)
    rtype       = case.get("report_type", "single_hla")
    nabl        = case.get("nabl", True)
    sig_stamp   = case.get("signature_stamp", settings.get("signature_stamp", False))

    c = copy.deepcopy(case)
    _decode_case_binary_fields(c)
    _auto_compute_derived_fields(c)
    c["signatories"] = _build_signatories(rtype, nabl, sig_counts, signatories,
                                           c.pop("sig_name_overrides", {}))
    if sig_stamp and any("rayvathy" in s["name"].lower() for s in c["signatories"]):
        for s in c["signatories"]:
            if "rayvathy" in s["name"].lower():
                s["seal_b64"] = hla_assets.SEAL_REVATHY_B64

    try:
        fname    = make_filename(c)
        tmp_id   = fname + "_" + str(uuid.uuid4())[:8] + ".pdf"
        tmp_path = os.path.join(HLA_TEMP_DIR, tmp_id)
        generate_pdf(c, tmp_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            out_path = unique_output_path(output_dir, fname)
            shutil.copy(tmp_path, out_path)
            fname = os.path.basename(out_path)
        return {"ok": True, "filename": fname, "download_url": f"/hla/preview-file/{tmp_id}"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))


@router.post("/generate-bulk")
async def generate_bulk(request_body: dict):
    cases      = request_body.get("cases", [])
    output_dir = request_body.get("output_dir") or None
    with_logo  = request_body.get("with_logo", True)
    sig_stamp  = request_body.get("signature_stamp", False)
    # nabl sent by the frontend reflects the global checkbox at generate time;
    # fall back to per-case value if the request predates this field.
    req_nabl   = request_body.get("nabl", None)

    settings    = _load_settings()
    sig_counts  = {**DEFAULT_SIG_COUNTS, **settings.get("sig_counts", {})}
    signatories = settings.get("signatories", DEFAULT_SIGNATORIES)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    success, failed = [], []

    for case in cases:
        c = copy.deepcopy(case)
        _decode_case_binary_fields(c)
        _auto_compute_derived_fields(c)
        c["with_logo"]       = with_logo
        c["signature_stamp"] = sig_stamp
        rtype = c.get("report_type", "single_hla")
        nabl  = req_nabl if req_nabl is not None else c.get("nabl", True)
        c["nabl"] = nabl

        if rtype not in ("sab_class1", "sab_class2") and _has_insufficient_data(c.get("patient", {})):
            failed.append({"filename": c.get("patient", {}).get("name", "?"), "error": "Insufficient Data"})
            continue

        c["signatories"] = _build_signatories(rtype, nabl, sig_counts, signatories,
                                               c.pop("sig_name_overrides", {}))
        if sig_stamp and any("rayvathy" in s["name"].lower() for s in c["signatories"]):
            for s in c["signatories"]:
                if "rayvathy" in s["name"].lower():
                    s["seal_b64"] = hla_assets.SEAL_REVATHY_B64

        fname    = make_filename(c)
        tmp_id   = fname + "_" + str(uuid.uuid4())[:8] + ".pdf"
        tmp_path = os.path.join(HLA_TEMP_DIR, tmp_id)
        try:
            generate_pdf(c, tmp_path)
            if output_dir:
                out_path = unique_output_path(output_dir, fname)
                shutil.copy(tmp_path, out_path)
                fname = os.path.basename(out_path)
            success.append({"filename": fname, "download_url": f"/hla/preview-file/{tmp_id}"})
        except Exception as e:
            traceback.print_exc()
            failed.append({"filename": fname, "error": str(e)})

    return {"success": success, "failed": failed}


_PDF_LABEL_KEYS = [
    ("Patient name", "_person_name"),
    ("Donor name", "_donor_marker"),
    ("Gender / Age", "gender_age"),
    ("Gender/ Age", "gender_age"),
    ("Hospital MR No", "hospital_mr_no"),
    ("Diagnosis", "diagnosis"),
    ("Referred By", "referred_by"),
    ("Hospital/Clinic", "hospital_clinic"),
    ("Hospital / Clinic", "hospital_clinic"),
    ("Relationship stated/Claimed", "_relationship"),
    ("Relationship", "_relationship"),
    ("PIN", "pin"),
    ("Sample Number", "sample_number"),
    ("Specimen", "specimen"),
    ("Sample collection date", "collection_date"),
    ("Collection Date", "collection_date"),
    ("Sample receipt date", "receipt_date"),
    ("Report date", "report_date"),
]


def _extract_patient_donor_from_pdf(content: bytes) -> dict:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    text = " ".join(text_parts).replace("\n", " ")
    text = text.replace("—", "").replace("�", "")
    text = re.sub(r"LOCUS\b.*?(?=Donor name\s*:|Patient name\s*:|$)", " ", text,
                  flags=re.IGNORECASE)

    labels_sorted = sorted(_PDF_LABEL_KEYS, key=lambda kv: -len(kv[0]))
    label_alt = "|".join(re.escape(lbl) for lbl, _ in labels_sorted)
    pattern = re.compile(
        rf"({label_alt})\s*:\s*(.*?)(?=\s*(?:{label_alt})\s*:|$)",
        re.IGNORECASE,
    )
    label_to_key = {lbl.lower(): key for lbl, key in _PDF_LABEL_KEYS}

    matches = list(pattern.finditer(text))
    donor_start = next((m.start() for m in matches if m.group(1).lower() == "donor name"), None)

    def _collect(field_matches):
        out = {}
        for m in field_matches:
            key = label_to_key.get(m.group(1).lower())
            value = m.group(2).strip()
            if not key or key.startswith("_") or not value:
                continue
            out[key] = value
        return out

    if donor_start is not None:
        patient_fields = _collect(m for m in matches if m.start() < donor_start)
        donor_fields = _collect(m for m in matches if m.start() >= donor_start)
        name_match = next((m for m in matches if m.group(1).lower() == "donor name" and m.start() >= donor_start), None)
        if name_match:
            donor_fields["name"] = name_match.group(2).strip()
    else:
        patient_fields = _collect(matches)
        donor_fields = None

    name_match = next((m for m in matches if m.group(1).lower() == "patient name"), None)
    if name_match:
        patient_fields["name"] = name_match.group(2).strip()

    return {
        "report_type": "transplant_donor" if donor_fields else "single_hla",
        "patient": patient_fields,
        "donors": [donor_fields] if donor_fields else [],
    }


@router.post("/pdf-to-draft")
async def pdf_to_draft(file: UploadFile = File(...)):
    content = await file.read()
    try:
        case = _extract_patient_donor_from_pdf(content)
    except Exception as e:
        raise HTTPException(400, f"Could not read this PDF: {e}")
    if not case["patient"].get("name"):
        raise HTTPException(422, "Could not find a 'Patient name' field in this PDF.")
    return {"ok": True, "rtype": case["report_type"], "case": case}


def _serialize_cases(cases: list) -> list:
    serialized = []
    for case in cases:
        c = copy.deepcopy(case)
        pat = c.get("patient") or {}
        if isinstance(pat.get("photo_bytes"), (bytes, bytearray)):
            pat["photo_bytes"] = base64.b64encode(pat["photo_bytes"]).decode()
        for d in c.get("donors", []):
            if isinstance(d.get("photo_bytes"), (bytes, bytearray)):
                d["photo_bytes"] = base64.b64encode(d["photo_bytes"]).decode()
        for lx_key in ("luminex_pat_photo", "luminex_don_photo"):
            if isinstance(c.get(lx_key), (bytes, bytearray)):
                c[lx_key] = base64.b64encode(c[lx_key]).decode()
        if isinstance(c.get("sab_chart_bytes"), (bytes, bytearray)):
            c["sab_chart_bytes"] = base64.b64encode(c["sab_chart_bytes"]).decode()
        serialized.append(c)
    return serialized


@router.post("/parse-excel")
async def parse_excel_file(
    file: UploadFile = File(...),
    nabl: bool = Form(True),
):
    tmp_path = os.path.join(HLA_UPLOAD_DIR, file.filename or "upload.xlsx")
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)
        cases = parse_excel(tmp_path, nabl=nabl)
        if not cases:
            try:
                sheet_names = pd.ExcelFile(tmp_path).sheet_names
            except Exception:
                sheet_names = []
            raise HTTPException(
                400,
                "No HLA cases could be recognised in this file. Sheets found: "
                f"{', '.join(sheet_names) or 'none'}. Expected an HLA typing export "
                "('patient-donor detail' + 'result data'/'complete csv data' sheets), "
                "or a CDC/DSA/Flow/Luminex/PRA/KIR crossmatch workbook — check the "
                "filename/sheet layout matches one of the supported formats (see User Guide).",
            )
        return {"cases": _serialize_cases(cases), "summary": get_case_summary(cases)}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@router.post("/parse-patient-result-csv")
async def parse_patient_result_csv(
    patient_file: UploadFile = File(...),
    result_file: UploadFile = File(...),
    nabl: bool = Form(True),
):
    patient_path = os.path.join(HLA_UPLOAD_DIR, patient_file.filename or "patients.csv")
    result_path = os.path.join(HLA_UPLOAD_DIR, result_file.filename or "results.csv")
    try:
        with open(patient_path, "wb") as f:
            f.write(await patient_file.read())
        with open(result_path, "wb") as f:
            f.write(await result_file.read())

        cases = parse_patient_and_result_csv(patient_path, result_path, nabl=nabl)
        if not cases:
            result_lookup = parse_result_csv(result_path)
            n_results = len(result_lookup)
            n_with_id = sum(1 for e in result_lookup.values() if e.get("patient_id_candidates"))
            n_patients = len(_parse_patient_list_csv(patient_path, nabl=nabl))
            raise HTTPException(
                400,
                f"No patients could be matched. Patient CSV: {n_patients} patient(s) parsed. "
                f"Result CSV: {n_results} sample(s) parsed, of which {n_with_id} contain a "
                "recognizable Patient No. If that count is 0, this Result CSV doesn't embed "
                "the Patient No yet — matching will work automatically once it does.",
            )
        return {"cases": _serialize_cases(cases), "summary": get_case_summary(cases)}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))
    finally:
        for p in (patient_path, result_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@router.post("/compute-rpl-reference")
async def compute_rpl(request_body: dict):
    patient = request_body.get("patient", {})
    donor   = request_body.get("donor", {})
    ref     = compute_rpl_reference(patient, donor)
    return ref


@router.post("/parse-sab-excel")
async def parse_sab_excel_file(
    file: UploadFile = File(...),
    kit: str = Form("kit1"),
):
    tmp_path = os.path.join(HLA_SAB_UPLOAD_DIR, file.filename or "sab_upload.xlsx")
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)
        data = parse_sab_excel(tmp_path, kit=kit)
        chart_bytes = data.get("chart_bytes")
        return {
            "patient":     data.get("patient", {}),
            "alleles":     data.get("alleles", []),
            "chart_bytes": base64.b64encode(chart_bytes).decode() if chart_bytes else None,
            "pra_pct":     data.get("pra_pct"),
            "sab_class":   data.get("sab_class"),
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Failed to parse SAB Excel file: {e}")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@router.post("/parse-sab-allele-text")
async def parse_sab_allele_text_endpoint(request_body: dict):
    text = request_body.get("text", "")
    return {"alleles": parse_sab_allele_text(text)}


@router.post("/c-supertype")
async def get_c_supertype(request_body: dict):
    allele = request_body.get("allele", "")
    return {"supertype": c_supertype(allele)}



@router.get("/download")
def download_report(path: str):
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="application/pdf",
                        filename=os.path.basename(path))
