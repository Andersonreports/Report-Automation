
import os
import re
import json
import uuid
import shutil
import base64
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import UploadFile, File, Request, Form
from fastapi.responses import FileResponse, JSONResponse

from karyotype_template import KaryotypeReportGenerator

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.environ.get("FRONTEND_DIR") or os.path.join(os.path.dirname(BASE_DIR), "frontend")

KARYO_REPORT_DIR = os.path.join(BASE_DIR, "reports-karyotype")
KARYO_TEMP_DIR   = os.path.join(BASE_DIR, "temp", "karyotype")
KARYO_IMG_DIR    = os.path.join(BASE_DIR, "uploads", "karyotype_img")
KARYO_DRAFT_DIR  = os.path.join(BASE_DIR, "drafts", "KARYOTYPE")

for _d in (KARYO_REPORT_DIR, KARYO_TEMP_DIR, KARYO_IMG_DIR, KARYO_DRAFT_DIR):
    os.makedirs(_d, exist_ok=True)


REPORT_TEMPLATES = {
    "Normal Male": {
        "INTERPRETATION": "Karyotype shows an apparently normal male.",
        "COMMENTS": "",
        "RECOMMENDATIONS": (
            "• Genetic counseling is recommended to discuss the implications of the result.\n"
            "• Additional genetic testing may be warranted based on the specific phenotypic indication."
        ),
        "AUTOSOME": "Normal",
        "SEX CHROMOSOME": "Normal",
    },
    "Normal Female": {
        "INTERPRETATION": "Karyotype shows an apparently normal female.",
        "COMMENTS": "",
        "RECOMMENDATIONS": (
            "• Genetic counseling is recommended to discuss the implications of the result.\n"
            "• Additional genetic testing may be warranted based on the specific phenotypic indication."
        ),
        "AUTOSOME": "Normal",
        "SEX CHROMOSOME": "Normal",
    },
    "Trisomy 21 (Down Syndrome)": {
        "INTERPRETATION": (
            "The constitutional karyotype shows a [male/female] with three copies of chromosome 21, "
            "indicating Down (Trisomy 21) syndrome."
        ),
        "COMMENTS": (
            "Trisomy 21 is a genetic syndrome associated with impairment of cognitive ability and "
            "physical growth as well as a particular set of facial characteristics."
        ),
        "RECOMMENDATIONS": "Advised genetic counseling for the parents.",
        "AUTOSOME": "Abnormal",
        "SEX CHROMOSOME": "Normal",
    },
    "Translocation": {
        "INTERPRETATION": (
            "Karyotype shows a [male/female] with an apparently balanced translocation involving "
            "chromosome [X] and [Y] with the breakpoints [Xp/q] and [Yp/q]."
        ),
        "COMMENTS": (
            "Usually this arrangement has no effect on development or general health because no genes "
            "have been lost or gained. However, the carrier of a balanced translocation has an increased "
            "risk of infertility, recurrent abortions and live-born offspring with chromosome imbalances "
            "like Emanuel syndrome."
        ),
        "RECOMMENDATIONS": (
            "Genetic counseling advised (to include review of partners’ karyotype). "
            "Prenatal diagnosis of all subsequent pregnancies is strongly recommended."
        ),
        "AUTOSOME": "Abnormal",
        "SEX CHROMOSOME": "Normal",
    },
    "Mosaic": {
        "INTERPRETATION": (
            "Karyotype analysis showed the presence of two cell lines: [X]% cells with [description] "
            "and [Y]% of the cells with [description]. This indicates a mosaic karyotype."
        ),
        "COMMENTS": (
            "Reports of individuals with this mosaic karyotype have indicated that they can present "
            "a wide spectrum of phenotypes. Clinical correlation is advised."
        ),
        "RECOMMENDATIONS": "Clinical correlation and genetic counselling.",
        "AUTOSOME": "Normal",
        "SEX CHROMOSOME": "Abnormal",
    },
    "Klinefelter's Syndrome (47,XXY)": {
        "INTERPRETATION": (
            "Karyotype analysis shows two X chromosomes and one Y chromosome, "
            "indicating Klinefelter’s syndrome."
        ),
        "COMMENTS": (
            "Klinefelter’s syndrome is characterized by eunuchoid body proportions, taller than "
            "average, gynecomastia, elevated luteinizing hormone (LH) and follicle stimulating hormone "
            "(FSH) levels."
        ),
        "RECOMMENDATIONS": "Advised genetic counseling.",
        "AUTOSOME": "Normal",
        "SEX CHROMOSOME": "Abnormal",
    },
    "Turner Syndrome (45,X)": {
        "INTERPRETATION": (
            "Karyotype analysis shows a single X chromosome (monosomy X), indicating Turner syndrome."
        ),
        "COMMENTS": (
            "Turner syndrome is characterized by short stature, gonadal dysgenesis, and various "
            "clinical features that may include cardiac defects and infertility."
        ),
        "RECOMMENDATIONS": "Advised genetic counseling and specialist evaluation.",
        "AUTOSOME": "Normal",
        "SEX CHROMOSOME": "Abnormal",
    },
    "Chromosomal Variant": {
        "INTERPRETATION": "",
        "COMMENTS": "",
        "RECOMMENDATIONS": "Genetic counseling advised.",
        "AUTOSOME": "Variant Observed",
        "SEX CHROMOSOME": "Normal",
    },
    "Other (Custom)": {
        "INTERPRETATION": "",
        "COMMENTS": "",
        "RECOMMENDATIONS": "",
        "AUTOSOME": "Normal",
        "SEX CHROMOSOME": "Normal",
    },
}

REPORT_TYPE_OPTIONS = list(REPORT_TEMPLATES.keys())

FIELD_DEFS = [
    ("Patient Name",              "NAME",                      "line",  ""),
    ("Gender",                    "GENDER",                    "combo", ["Male", "Female"]),
    ("Age",                       "AGE",                       "line",  "e.g. 25 Years"),
    ("Specimen",                  "SPECIMEN",                  "line",  "Peripheral blood"),
    ("PIN",                       "PIN",                       "line",  ""),
    ("Sample Number",             "SAMPLE NUMBER",             "line",  ""),
    ("Sample Collection Date",    "SAMPLE COLLECTION DATE",    "line",  "DD-MM-YYYY"),
    ("Sample Receipt Date",       "SAMPLE RECEIPT DATE",       "line",  "DD-MM-YYYY"),
    ("Report Date",               "REPORT DATE",               "line",  "DD-MM-YYYY"),
    ("Referring Clinician",       "REFERRING CLINICIAN",       "line",  ""),
    ("Hospital / Clinic",         "HOSPITAL/CLINIC",           "line",  ""),
    ("Test Indication",           "TEST INDICATION",           "line",  "To rule out gross chromosomal abnormality"),
    ("ISCN Result",               "RESULT",                    "line",  "e.g. 46,XX"),
    ("Metaphase Analysed",        "METAPHASE ANALYSED",        "line",  "25"),
    ("Estimated Band Resolution", "ESTIMATED BAND RESOLUTION", "line",  "475"),
    ("Autosome",                  "AUTOSOME",                  "combo", ["Normal", "Abnormal", "Variant Observed"]),
    ("Sex Chromosome",            "SEX CHROMOSOME",            "combo", ["Normal", "Abnormal"]),
    ("Interpretation",            "INTERPRETATION",            "text",  ""),
    ("Comments",                  "COMMENTS",                  "text",  ""),
    ("Recommendations",           "RECOMMENDATIONS",           "text",  ""),
]


def _clean(v) -> str:
    s = str(v).strip()
    return "" if s in ("nan", "NaT", "None", "NaN", "") else s


def _fmt_date(v) -> str:
    s = _clean(str(v))
    if not s:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.split(" ")[0], fmt.split(" ")[0]).strftime("%d-%m-%Y")
        except Exception:
            pass
    return s


def _detect_report_type(iscn: str) -> str:
    s = (iscn or "").strip()
    if not s:
        return "Other (Custom)"
    sl = s.lower()
    if sl.startswith("mos"):
        return "Mosaic"
    if "xxy" in sl:
        return "Klinefelter's Syndrome (47,XXY)"
    if re.search(r"45\s*,\s*x\b", sl):
        return "Turner Syndrome (45,X)"
    if "t(" in sl or "rob(" in sl:
        return "Translocation"
    if "+21" in s:
        return "Trisomy 21 (Down Syndrome)"
    if re.match(r"^46\s*,\s*xy$", s, re.IGNORECASE):
        return "Normal Male"
    if re.match(r"^46\s*,\s*xx$", s, re.IGNORECASE):
        return "Normal Female"
    if re.search(r"del\(|dup\(|inv\(|ins\(|add\(", sl):
        return "Chromosomal Variant"
    return "Other (Custom)"


def _find_images_for_sample(sample_no: str, search_dir: str) -> list:
    if not sample_no or not search_dir or not os.path.isdir(search_dir):
        return []
    sample_no = str(sample_no).strip()
    if not sample_no:
        return []

    results = []
    search_path = Path(search_dir)
    extensions = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
    try:
        for file_path in search_path.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in [ext.lower() for ext in extensions]:
                continue
            fname = file_path.stem.strip()
            clean_fname = re.sub(r'[_+\-]', ' ', fname)
            clean_fname = re.sub(r'\s+', ' ', clean_fname).strip()
            if clean_fname == sample_no or re.match(rf"^{re.escape(sample_no)}\s+\d+$", clean_fname):
                results.append(file_path.name)
        results.sort()
    except (OSError, PermissionError):
        return []
    return results


def _safe_component(name: str) -> str:
    name = os.path.basename(str(name or ""))
    return re.sub(r'[^\w\s\-\(\)\.]', '_', name).strip() or "file"


def _column_key(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(name or "").upper())


COLUMN_ALIASES = {
    "NAME": {
        "NAME", "PATIENTNAME", "PATIENT", "PATIENTFULLNAME", "PTNAME",
        "BENEFICIARYNAME",
    },
    "GENDER": {"GENDER", "SEX"},
    "AGE": {"AGE", "DATEOFBIRTHAGE", "DOBAGE"},
    "SPECIMEN": {"SPECIMEN", "SAMPLETYPE", "TYPEOFSAMPLE"},
    "PIN": {"PIN", "UHID", "UMR", "UMRNO", "MRN", "PATIENTID"},
    "SAMPLE NUMBER": {
        "SAMPLENUMBER", "SAMPLENO", "SAMPLEID", "LABNO", "LABNUMBER",
        "ACCESSIONNO", "ACCESSIONNUMBER", "BARCODE",
    },
    "SAMPLE COLLECTION DATE": {
        "SAMPLECOLLECTIONDATE", "COLLECTIONDATE", "COLLECTEDDATE",
        "COLDATE", "DATEOFCOLLECTION",
    },
    "SAMPLE RECEIPT DATE": {
        "SAMPLERECEIPTDATE", "RECEIPTDATE", "RECEIVEDDATE", "RECDATE",
        "DATEOFRECEIPT", "DATEOFRECEIVING",
    },
    "REPORT DATE": {"REPORTDATE", "DATEOFREPORT", "REPORTEDDATE"},
    "REFERRING CLINICIAN": {
        "REFERRINGCLINICIAN", "REFERRINGDOCTOR", "REFDOCTOR",
        "DOCTOR", "CLINICIAN", "CONSULTANT",
    },
    "HOSPITAL/CLINIC": {
        "HOSPITALCLINIC", "HOSPITAL", "CLINIC", "CENTER", "CENTRE",
        "REFERRALCENTRE",
    },
    "TEST INDICATION": {
        "TESTINDICATION", "INDICATION", "CLINICALINDICATION",
        "REASONFORTEST",
    },
    "RESULT": {
        "RESULT", "ISCNRESULT", "KARYOTYPERESULT", "KARYOTYPE",
        "FINALRESULT", "CYTOGENETICRESULT",
    },
    "METAPHASE ANALYSED": {
        "METAPHASEANALYSED", "METAPHASESANALYSED", "METAPHASEANALYZED",
        "METAPHASESANALYZED", "METAPHASE",
    },
    "ESTIMATED BAND RESOLUTION": {
        "ESTIMATEDBANDRESOLUTION", "BANDRESOLUTION", "BANDINGRESOLUTION",
        "RESOLUTION",
    },
    "AUTOSOME": {"AUTOSOME", "AUTOSOMES"},
    "SEX CHROMOSOME": {"SEXCHROMOSOME", "SEXCHROMOSOMES"},
    "INTERPRETATION": {"INTERPRETATION", "IMPRESSION"},
    "COMMENTS": {"COMMENTS", "COMMENT", "REMARKS"},
    "RECOMMENDATIONS": {"RECOMMENDATIONS", "RECOMMENDATION", "ADVICE"},
}

ALIAS_TO_FIELD = {
    alias: field
    for field, aliases in COLUMN_ALIASES.items()
    for alias in aliases
}


def _inline_image_to_file(item: dict) -> str:
    data_url = str(item.get("data_url") or item.get("dataUrl") or item.get("base64") or "")
    if not data_url:
        return ""
    ext = os.path.splitext(str(item.get("filename") or item.get("original") or ""))[1].lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".png" if "image/png" in data_url[:40].lower() else ".jpg"
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    try:
        raw = base64.b64decode(data_url)
    except Exception:
        return ""
    os.makedirs(KARYO_TEMP_DIR, exist_ok=True)
    path = os.path.join(KARYO_TEMP_DIR, f"inline_{uuid.uuid4().hex[:10]}{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    return path


def _resolve_images(image_names) -> list:
    paths = []
    base = os.path.realpath(KARYO_IMG_DIR)
    for item in (image_names or []):
        if not item:
            continue
        if isinstance(item, dict):
            inline_path = _inline_image_to_file(item)
            if inline_path and os.path.isfile(inline_path):
                paths.append(inline_path)
                continue
            nm = item.get("filename") or item.get("name") or item.get("path") or ""
        else:
            nm = item
        candidate = os.path.realpath(os.path.join(KARYO_IMG_DIR, str(nm).replace("\\", "/")))
        if candidate.startswith(base) and os.path.isfile(candidate):
            paths.append(candidate)
    return paths


def _normalize_row(row: dict) -> dict:
    row = {k: _clean(v) for k, v in row.items()}
    for k, v in list(row.items()):
        canonical = ALIAS_TO_FIELD.get(_column_key(k))
        if canonical and not _clean(row.get(canonical, "")):
            row[canonical] = v
    for dc in ("SAMPLE COLLECTION DATE", "SAMPLE RECEIPT DATE", "REPORT DATE"):
        for variant in (dc, dc + " ", " " + dc):
            if variant in row:
                row[dc] = _fmt_date(row[variant])
    for k in list(row.keys()):
        canonical = k.strip()
        if canonical != k and canonical not in row:
            row[canonical] = row[k]
    return row


def register_karyotype_routes(app):

    @app.get("/karyotype")
    @app.get("/karyotype.html")
    def karyotype_page():
        p = os.path.join(FRONTEND_DIR, "karyotype.html")
        if os.path.isfile(p):
            return FileResponse(p)
        return JSONResponse({"error": "karyotype.html not found"}, status_code=404)

    @app.get("/karyotype/meta")
    def karyotype_meta():
        return {
            "report_types": REPORT_TYPE_OPTIONS,
            "templates": REPORT_TEMPLATES,
            "fields": [
                {"label": l, "key": k, "type": t,
                 "options": (o if isinstance(o, list) else []),
                 "placeholder": (o if isinstance(o, str) else "")}
                for (l, k, t, o) in FIELD_DEFS
            ],
        }

    @app.get("/reports-karyotype/{filename}")
    def karyotype_report_file(filename: str):
        p = os.path.join(KARYO_REPORT_DIR, os.path.basename(filename))
        if os.path.isfile(p):
            return FileResponse(p, media_type="application/pdf", filename=os.path.basename(p))
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/karyotype/preview-file/{filename}")
    def karyotype_preview_file(filename: str):
        p = os.path.join(KARYO_TEMP_DIR, os.path.basename(filename))
        if os.path.isfile(p):
            return FileResponse(p, media_type="application/pdf")
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/karyotype/image/{path:path}")
    def karyotype_image(path: str):
        candidate = os.path.realpath(os.path.join(KARYO_IMG_DIR, path.replace("\\", "/")))
        base = os.path.realpath(KARYO_IMG_DIR)
        if candidate.startswith(base) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.post("/karyotype/upload-image")
    async def karyotype_upload_image(file: UploadFile = File(...)):
        ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png"):
            return JSONResponse({"error": "Only JPG/PNG images are allowed"}, status_code=400)
        stem = _safe_component(os.path.splitext(file.filename or "image")[0])
        stored = f"{uuid.uuid4().hex[:8]}_{stem}{ext}"
        dest = os.path.join(KARYO_IMG_DIR, stored)
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"filename": stored,
                "original": file.filename,
                "url": f"/karyotype/image/{stored}"}

    @app.post("/karyotype/preview")
    async def karyotype_preview(request: Request):
        body = await request.json()
        data = body.get("data", {}) or {}
        images = _resolve_images(body.get("images", []))
        with_logo = bool(body.get("with_logo", True))
        if not _clean(data.get("NAME", "")):
            return JSONResponse({"error": "Patient Name is required"}, status_code=400)
        try:
            _name_seg = re.sub(r'[^a-zA-Z0-9]+', '_', _clean(data.get("NAME", "")) or "preview").strip("_") or "preview"
            file_id = f"karyo_{_name_seg}_{uuid.uuid4().hex[:8]}.pdf"
            gen = KaryotypeReportGenerator(data, images, KARYO_TEMP_DIR, include_logo=with_logo)
            gen.filepath = os.path.join(KARYO_TEMP_DIR, file_id)
            gen.filename = file_id
            gen.generate()
            preview_url = f"/karyotype/preview-file/{file_id}"
            return {
                "preview_url": preview_url,
                "previewUrl": preview_url,
                "pdf_url": preview_url,
                "pdfUrl": preview_url,
                "url": preview_url,
                "file": file_id,
            }
        except Exception as e:
            import traceback
            return JSONResponse({"error": str(e), "trace": traceback.format_exc()},
                                status_code=500)

    @app.post("/karyotype/generate")
    async def karyotype_generate(request: Request):
        body = await request.json()
        data = body.get("data", {}) or {}
        images = _resolve_images(body.get("images", []))
        with_logo = bool(body.get("with_logo", True))
        if not _clean(data.get("NAME", "")):
            return JSONResponse({"error": "Patient Name is required"}, status_code=400)
        try:
            gen = KaryotypeReportGenerator(data, images, KARYO_REPORT_DIR, include_logo=with_logo)
            path = gen.generate()
            fn = os.path.basename(path)
            return {"file": fn, "url": f"/reports-karyotype/{fn}"}
        except Exception as e:
            import traceback
            return JSONResponse({"error": str(e), "trace": traceback.format_exc()},
                                status_code=500)

    @app.post("/karyotype/generate-bulk")
    async def karyotype_generate_bulk(request: Request):
        body = await request.json()
        patients = body.get("patients", []) or []
        with_logo = bool(body.get("with_logo", True))
        results, errors = [], []
        for i, p in enumerate(patients, 1):
            data = p.get("data", {}) or {}
            name = _clean(data.get("NAME", "")) or f"Row {i}"
            imgs = _resolve_images(p.get("images", []))
            try:
                gen = KaryotypeReportGenerator(data, imgs, KARYO_REPORT_DIR, include_logo=with_logo)
                path = gen.generate()
                fn = os.path.basename(path)
                results.append({"name": name, "file": fn, "url": f"/reports-karyotype/{fn}"})
            except Exception as e:
                errors.append(f"{name}: {e}")
        return {"generated": len(results), "results": results, "errors": errors}

    @app.post("/karyotype/parse-excel")
    async def karyotype_parse_excel(file: UploadFile = File(...),
                                    images: list[UploadFile] = File(default=[])):
        try:
            contents = await file.read()
            import io as _io
            batch_id = uuid.uuid4().hex[:10]
            batch_dir = os.path.join(KARYO_IMG_DIR, batch_id)
            saved_any = False
            for img in (images or []):
                if not img or not img.filename:
                    continue
                os.makedirs(batch_dir, exist_ok=True)
                saved_any = True
                with open(os.path.join(batch_dir, _safe_component(img.filename)), "wb") as f:
                    shutil.copyfileobj(img.file, f)

            rows = []
            scanned_sheets = []
            xls = pd.ExcelFile(_io.BytesIO(contents))
            for sheet_name in xls.sheet_names:
                raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str, nrows=12)
                header_row = 0
                for i, raw_row in raw.iterrows():
                    vals = [_column_key(v) for v in raw_row.values if str(v).strip()]
                    if any(v in ALIAS_TO_FIELD or v in ("SNO", "SLNO", "SERIALNO") for v in vals):
                        header_row = int(i)
                        break

                df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row, dtype=str)
                df.columns = [str(c).strip().upper() for c in df.columns]
                df = df.dropna(how="all")
                scanned_sheets.append(sheet_name)

                for _, ser in df.iterrows():
                    row = _normalize_row({k: v for k, v in ser.items()})
                    if not _clean(row.get("NAME", "")):
                        continue
                    row["REPORT_TYPE"] = _detect_report_type(row.get("RESULT", ""))
                    imgs = []
                    if saved_any:
                        imgs = [f"{batch_id}/{n}" for n in
                                _find_images_for_sample(row.get("SAMPLE NUMBER", ""), batch_dir)]
                    row["IMAGES"] = imgs
                    rows.append(row)

            return {"rows": rows, "count": len(rows), "batch_id": batch_id,
                    "sheets": scanned_sheets}
        except Exception as e:
            import traceback
            return JSONResponse({"error": str(e), "trace": traceback.format_exc()},
                                status_code=500)

    @app.post("/karyotype/draft/save")
    async def karyotype_save_draft(request: Request):
        body = await request.json()
        name = _clean((body.get("data", {}) or {}).get("NAME", "")) or "draft"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"karyo_draft_{_safe_component(name).replace(' ', '_')}_{ts}.json"
        with open(os.path.join(KARYO_DRAFT_DIR, fname), "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2, ensure_ascii=False)
        return {"saved": fname}

    @app.get("/karyotype/draft/list")
    def karyotype_list_drafts():
        try:
            files = sorted(
                [f for f in os.listdir(KARYO_DRAFT_DIR) if f.endswith(".json")],
                reverse=True)
            return {"drafts": files}
        except Exception:
            return {"drafts": []}

    @app.get("/karyotype/draft/load/{filename}")
    def karyotype_load_draft(filename: str):
        p = os.path.join(KARYO_DRAFT_DIR, os.path.basename(filename))
        if not os.path.isfile(p):
            return JSONResponse({"error": "not found"}, status_code=404)
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    @app.delete("/karyotype/draft/delete/{filename}")
    def karyotype_delete_draft(filename: str):
        p = os.path.join(KARYO_DRAFT_DIR, os.path.basename(filename))
        if os.path.isfile(p):
            os.remove(p)
            return {"deleted": filename}
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/karyotype/storage/list")
    def karyotype_storage_list():
        try:
            files = sorted(
                [f for f in os.listdir(KARYO_REPORT_DIR) if not f.startswith(".")],
                reverse=True)
            return {"items": [{"name": f, "url": f"/reports-karyotype/{f}"} for f in files]}
        except Exception:
            return {"items": []}

    return app
