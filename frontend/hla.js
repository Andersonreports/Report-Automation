// hla.js — HLA Typing Report Generator (web)
// Mirrors hla_report_generator.py (desktop) logic 1:1 against the FastAPI hla_api.py backend.

const API = ""; // same-origin

const REPORT_TEMPLATES = [
  { name: "With CL", report_type: "single_hla" },
  { name: "RPL", report_type: "rpl_couple" },
  { name: "Single RPL", report_type: "single_rpl" },
  { name: "Single Locus", report_type: "single_locus" },
  { name: "HLA-C", report_type: "hla_c" },
  { name: "HLA Typing High Resolution (Transplant Donor)", report_type: "transplant_donor" },
  { name: "HLA (NGS with Photo)", report_type: "ngs_photo" },
  { name: "HLA Typing High Resolution (11 Loci)", report_type: "loci11" },
  { name: "CDC", report_type: "cdc_crossmatch" },
  { name: "DSA", report_type: "dsa_crossmatch" },
  { name: "SAB Class I", report_type: "sab_class1" },
  { name: "SAB Class II", report_type: "sab_class2" },
  { name: "Flow", report_type: "flow_crossmatch" },
  { name: "HLA Typing (Luminex)", report_type: "luminex_typing" },
  { name: "KIR Genotyping", report_type: "kir_genotyping" },
  { name: "PRA Class I", report_type: "pra_class1" },
  { name: "PRA Class II", report_type: "pra_class2" },
  { name: "Mixed PRA", report_type: "mixed_pra" },
];
const TEMPLATE_TO_RTYPE = {};
REPORT_TEMPLATES.forEach(t => TEMPLATE_TO_RTYPE[t.name] = t.report_type);
const RTYPE_TO_TEMPLATE_NAME = {};
REPORT_TEMPLATES.forEach(t => RTYPE_TO_TEMPLATE_NAME[t.report_type] = t.name);

const HLA_LOCI = ["A", "B", "C", "DRB1", "DQB1", "DPB1", "DRB3", "DPA1", "DQA1"];
const HLA_LOCUS_LABELS = { DRB3: "DRB3/4/5" };
// DRB3/DRB4/DRB5 are shown as THREE separate allele rows for every template
// EXCEPT loci11, which merges them into a single combined "DRB3/4/5" row.
const SEPARATE_DRB_RTYPES = ["ngs_photo", "transplant_donor"]; // kept for bulk splitDrb345 compat
function isSeparateDrb(rtype) { return rtype !== "loci11"; }

const DEFAULT_SIG_COUNTS = {
  single_hla: 3, rpl_couple: 2, single_rpl: 2, single_locus: 2, hla_c: 2,
  transplant_donor: 2, ngs_photo: 2, loci11: 3, cdc_crossmatch: 2, dsa_crossmatch: 2,
  sab_class1: 2, sab_class2: 2,
  flow_crossmatch: 2, luminex_typing: 2, kir_genotyping: 2, pra_class1: 2,
  pra_class2: 2, mixed_pra: 2,
};

const SAB_KIT_NAMES = ["Immucor", "One Lambda"];

function sabKitId(name) {
  const s = String(name || "").trim().toLowerCase();
  if (s.includes("lambda") || s.includes("kit 2") || s.includes("kit2")) return "kit2";
  return "kit1";
}

const _AUTO_SAB_PRA_RE = /^\s*The SAB % PRA Class (?:I|II) is \d+%\.?\s*$/i;

function sabPraSentence(pctText, sabClass) {
  const m = String(pctText || "").match(/\d+/);
  if (!m) return "";
  const cls = String(sabClass || "").trim().toUpperCase().endsWith("II") ? "II" : "I";
  return `The SAB % PRA Class ${cls} is ${parseInt(m[0], 10)}%.`;
}

function isAutoSabPraText(text) {
  return _AUTO_SAB_PRA_RE.test(String(text || ""));
}

function parseSabAlleleTextLocal(text) {
  const result = [];
  for (const raw of String(text || "").trim().split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/^(.*)[,\t]\s*([0-9]+(?:\.[0-9]+)?)\s*$/);
    if (!m) continue;
    const allele = m[1].trim().replace(/,+$/, "").trim();
    if (!allele) continue;
    const mfi = parseInt(parseFloat(m[2]), 10);
    if (Number.isNaN(mfi)) continue;
    result.push([allele, mfi]);
  }
  return result.sort((a, b) => b[1] - a[1]);
}

function applySabPraToRemarksComments(pctText, sabClass, remarksInput, commentsInput) {
  const sentence = sabPraSentence(pctText, sabClass);
  if (!sentence) return;
  if (!remarksInput.value.trim() || isAutoSabPraText(remarksInput.value)) {
    remarksInput.value = sentence;
  }
  if (!commentsInput.value.trim() || isAutoSabPraText(commentsInput.value)) {
    commentsInput.value = sentence;
  }
}

const DEFAULT_SIGNATORIES = [
  { name: "Ms. S Aruna Devi", title: "Team Lead – Transplant Immunogenetics<br/>(Reviewed By)" },
  { name: "Nikhala Shree S, Ph.D", title: "Molecular Biologist" },
  { name: "Dr. B. Rayvathy", title: "Consultant Microbiologist" },
];

// ── App state ───────────────────────────────────────────────────────────────
const state = {
  rtype: "single_hla",
  withLogo: true,
  manualCase: null,
  manualDonors: [],
  previewTimer: null,
  bulkCases: [],
  bulkSelected: new Set(),
  bulkCurrentIndex: -1,
  bulkPhotoBytes: {},
  savedPatient: null,
  settings: { signatories: DEFAULT_SIGNATORIES, sig_counts: { ...DEFAULT_SIG_COUNTS }, with_logo: true, nabl: true, signature_stamp: false },
};

// ── Helpers ─────────────────────────────────────────────────────────────────
const _pdfTokens = {};
const _dirHandles = {};

function renderPdfToCanvas(arrayBuffer, host, token, tokenKey) {
  const lib = window['pdfjs-dist/build/pdf'];
  if (!lib) {
    if (host.dataset.blobUrl) URL.revokeObjectURL(host.dataset.blobUrl);
    const u = URL.createObjectURL(new Blob([arrayBuffer], {type: "application/pdf"}));
    host.dataset.blobUrl = u;
    host.innerHTML = `<iframe src="${u}#toolbar=0&navpanes=0" style="width:100%;flex:1;border:none;min-height:400px;"></iframe>`;
    return Promise.resolve();
  }
  return lib.getDocument({data: arrayBuffer}).promise.then(doc => {
    if (_pdfTokens[tokenKey] !== token) return;
    host.innerHTML = "";
    const containerW = Math.max((host.clientWidth || 440) - 24, 240);
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    let chain = Promise.resolve();
    for (let n = 1; n <= doc.numPages; n++) {
      const num = n;
      chain = chain.then(() => {
        if (_pdfTokens[tokenKey] !== token) return;
        return doc.getPage(num).then(page => {
          if (_pdfTokens[tokenKey] !== token) return;
          const vp = page.getViewport({scale: 1});
          const cssScale = Math.max(0.4, containerW / vp.width);
          const svp = page.getViewport({scale: cssScale * dpr});
          const canvas = document.createElement("canvas");
          canvas.className = "preview-page-canvas";
          canvas.width = svp.width;
          canvas.height = svp.height;
          host.appendChild(canvas);
          return page.render({canvasContext: canvas.getContext("2d"), viewport: svp}).promise;
        });
      });
    }
    return chain;
  });
}

function praResultFor(pct) {
  const v = parseFloat(String(pct || "").replace("%", "").trim());
  if (isNaN(v)) return "";
  if (v < 4)   return "Negative";
  if (v <= 10) return "Weak Positive";
  if (v <= 50) return "Moderate Positive";
  return "Strong Positive";
}

function showToast(msg, type = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (type ? " " + type : "");
  setTimeout(() => t.classList.remove("show"), 2800);
}

function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  });
  (Array.isArray(children) ? children : [children]).forEach(c => {
    if (c == null) return;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  return e;
}

async function apiPost(path, body) {
  const r = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) {
    const t = await r.text();
    try { const j = JSON.parse(t); throw new Error(j.detail || t); } catch (e) { if (e instanceof SyntaxError) throw new Error(t); throw e; }
  }
  return r.json();
}
async function apiGet(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function emptyHla() {
  const o = {};
  HLA_LOCI.forEach(l => o[l] = ["", ""]);
  return o;
}

function emptyPerson(extra = {}) {
  return {
    name: "", gender_age: "", hospital_mr_no: "NA", diagnosis: "", referred_by: "",
    hospital_clinic: "", pin: "", sample_number: "", specimen: "Blood - EDTA",
    collection_date: "", receipt_date: "", report_date: "", remarks: "",
    hla: emptyHla(), hla_c_type: "", relationship: "", match: "", ...extra,
  };
}

// ══════════════════════════════════════════════════════════════════════════
// TAB SWITCHING
// ══════════════════════════════════════════════════════════════════════════
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
  });
});

// ══════════════════════════════════════════════════════════════════════════
// PATIENT DATA PERSISTENCE ACROSS TEMPLATE SWITCHES
// ══════════════════════════════════════════════════════════════════════════
function capturePatientForRestore() {
  try {
    const c = collectManualCase();
    if (c && c.patient) {
      const hla = {};
      Object.entries(manualHlaFields).forEach(([locus, pair]) => {
        hla[locus] = [pair[0] ? pair[0].value : "", pair[1] ? pair[1].value : ""];
      });
      state.savedPatient = { ...c.patient, _hla: hla };
    }
  } catch (e) {
    state.savedPatient = null;
  }
}

function restorePatientAfterRender() {
  const p = state.savedPatient;
  if (!p) return;
  function set(input, value) { if (input && value != null && String(value).trim()) input.value = value; }
  const g_a = p.gender_age || [p.gender, p.age].filter(Boolean).join(" / ");

  // Standard templates
  set(manualFields.patient_name, p.name);
  set(manualFields.gender_age, g_a);
  set(manualFields.pin, p.pin);
  set(manualFields.sample_number, p.sample_number);
  set(manualFields.hospital_clinic, p.hospital_clinic);
  if (p.specimen && p.specimen !== "Blood - EDTA") set(manualFields.specimen, p.specimen);
  set(manualFields.collection_date, p.collection_date);
  set(manualFields.receipt_date, p.receipt_date);
  set(manualFields.report_date, p.report_date);
  set(manualFields.remarks, p.remarks);
  if (p.hospital_mr_no && p.hospital_mr_no !== "NA") set(manualFields.hospital_mr_no, p.hospital_mr_no);
  set(manualFields.diagnosis, p.diagnosis);
  set(manualFields.referred_by, p.referred_by);

  // HLA alleles
  if (p._hla) {
    Object.entries(p._hla).forEach(([locus, [a1, a2]]) => {
      if (manualHlaFields[locus]) { set(manualHlaFields[locus][0], a1); set(manualHlaFields[locus][1], a2); }
    });
  }

  // PRA templates
  const pra = manualSpecialFields.pra && manualSpecialFields.pra.patient;
  if (pra) {
    set(pra.patient_name, p.name);
    set(pra.gender, p.gender || (g_a.includes("/") ? g_a.split("/")[0].trim() : g_a));
    set(pra.age, p.age || (g_a.includes("/") ? (g_a.split("/")[1] || "").trim() : ""));
    set(pra.pin, p.pin); set(pra.sample_number, p.sample_number);
    set(pra.hospital_clinic, p.hospital_clinic); set(pra.specimen, p.specimen);
    set(pra.collection_date, p.collection_date); set(pra.receipt_date, p.receipt_date);
    set(pra.report_date, p.report_date);
  }

  // Crossmatch templates
  const xp = manualSpecialFields.crossmatch && manualSpecialFields.crossmatch.patient;
  if (xp) {
    set(xp.name, p.name); set(xp.gender_age, g_a); set(xp.pin, p.pin);
    set(xp.sample_number, p.sample_number); set(xp.hospital_clinic, p.hospital_clinic);
    set(xp.collection_date, p.collection_date); set(xp.receipt_date, p.receipt_date);
    set(xp.report_date, p.report_date);
  }

  // SAB / Luminex / KIR — all use patient_name key
  ["sab", "luminex", "kir"].forEach(key => {
    const sp = manualSpecialFields[key] && manualSpecialFields[key].patient;
    if (!sp) return;
    set(sp.patient_name, p.name); set(sp.gender_age, g_a); set(sp.pin, p.pin);
    set(sp.sample_number, p.sample_number); set(sp.hospital_clinic, p.hospital_clinic);
    set(sp.collection_date, p.collection_date); set(sp.receipt_date, p.receipt_date);
    set(sp.report_date, p.report_date);
  });
}

// ══════════════════════════════════════════════════════════════════════════
// HEADER: TEMPLATE + LOGO SELECT
// ══════════════════════════════════════════════════════════════════════════
function initTemplateSelect() {
  const sel = document.getElementById("templateSelect");
  REPORT_TEMPLATES.forEach(t => {
    sel.appendChild(el("option", { value: t.name }, t.name));
  });
  sel.addEventListener("change", () => {
    const newRtype = TEMPLATE_TO_RTYPE[sel.value];
    const activeTab = document.querySelector(".tab.active")?.dataset.tab;
    const bulkCase = state.bulkCases[state.bulkCurrentIndex];
    if (activeTab === "bulk" && bulkCase) {
      // A bulk case is selected — retarget its report type instead of the manual form.
      bulkCase.report_type = newRtype;
      renderBulkList();
      renderBulkEditor(state.bulkCurrentIndex);
      previewBulkCase(state.bulkCurrentIndex);
    } else {
      capturePatientForRestore();
      state.rtype = newRtype;
      renderManualForm();
      restorePatientAfterRender();
    }
  });
  document.getElementById("logoSelect").addEventListener("change", e => {
    state.withLogo = e.target.value === "true";
    // Keep bulk logo checkbox in sync
    const bulkChk = document.getElementById("bulkLogoChk");
    if (bulkChk) bulkChk.checked = state.withLogo;
    if (document.querySelector(".tab[data-tab='bulk']")?.classList.contains("active") && state.bulkCurrentIndex >= 0) {
      previewBulkCase(state.bulkCurrentIndex);
    } else {
      scheduleManualPreview();
    }
  });
  document.getElementById("globalNablChk").addEventListener("change", scheduleManualPreview);
  document.getElementById("globalStampChk").addEventListener("change", scheduleManualPreview);
}

// ══════════════════════════════════════════════════════════════════════════
// MANUAL TAB — FORM BUILDER
// ══════════════════════════════════════════════════════════════════════════
const PAT_FIELDS = [
  ["patient_name", "Patient Name *", ""],
  ["gender_age", "Gender / Age", ""],
  ["hospital_mr_no", "Hospital MR No.", "NA"],
  ["diagnosis", "Diagnosis", ""],
  ["referred_by", "Referred By", ""],
  ["hospital_clinic", "Hospital / Clinic", ""],
  ["pin", "PIN *", ""],
  ["sample_number", "Sample Number", ""],
  ["specimen", "Specimen", "Blood - EDTA"],
  ["collection_date", "Collection Date (DD-MM-YYYY)", ""],
  ["receipt_date", "Sample Receipt Date (DD-MM-YYYY)", ""],
  ["report_date", "Report Date (DD-MM-YYYY)", ""],
  ["remarks", "Remarks", ""],
];

function buildPatientInfoCard(prefix, fieldsRef) {
  const card = el("div", { class: "card" }, [
    el("h3", {}, [el("i", { class: "fas fa-user" }), " Patient Information"]),
  ]);
  const grid = el("div", { class: "field-grid" });
  PAT_FIELDS.forEach(([key, label, def]) => {
    const input = el("input", { type: "text", id: `${prefix}_${key}`, value: def, oninput: scheduleManualPreview });
    fieldsRef[key] = input;
    const wrap = el("div", { class: "field" + (key === "remarks" ? " full" : "") }, [
      el("label", {}, label),
      input,
    ]);
    grid.appendChild(wrap);
  });
  card.appendChild(grid);
  return card;
}

function buildHlaAlleleCard(prefix, hlaFieldsRef, separateDrb = false) {
  const card = el("div", { class: "card" }, [
    el("h3", {}, [el("i", { class: "fas fa-dna" }), " HLA Results"]),
  ]);
  const grid = el("div", { class: "allele-grid" });
  grid.appendChild(el("div", { class: "allele-row" }, [
    el("span", {}, ""), el("span", { style: "font-size:10px;font-weight:700;color:var(--text-muted);" }, "ALLELE 1"),
    el("span", { style: "font-size:10px;font-weight:700;color:var(--text-muted);" }, "ALLELE 2"),
  ]));
  function addRow(locus, label) {
    const a1 = el("input", { type: "text", placeholder: "e.g. A*02:01:01", id: `${prefix}_${locus}_1`, oninput: scheduleManualPreview });
    const a2 = el("input", { type: "text", placeholder: "Allele 2", id: `${prefix}_${locus}_2`, oninput: scheduleManualPreview });
    hlaFieldsRef[locus] = [a1, a2];
    grid.appendChild(el("div", { class: "allele-row" }, [el("span", { class: "locus-lbl" }, label), a1, a2]));
  }
  HLA_LOCI.forEach(locus => {
    if (locus === "DRB3" && separateDrb) {
      addRow("DRB3", "DRB3");
      addRow("DRB4", "DRB4");
      addRow("DRB5", "DRB5");
    } else {
      addRow(locus, HLA_LOCUS_LABELS[locus] || locus);
    }
  });
  card.appendChild(grid);
  return card;
}

function buildDonorCard(prefix, fieldsRef, hlaFieldsRef, title = "Donor Information", separateDrb = false) {
  const card = el("div", { class: "card" }, [
    el("h3", {}, [el("i", { class: "fas fa-user-friends" }), " " + title]),
  ]);
  const grid = el("div", { class: "field-grid" });
  const DONOR_FIELDS = [
    ["name", "Donor Name", ""], ["gender_age", "Gender / Age", ""],
    ["relationship", "Relationship", ""], ["hospital_mr_no", "Hospital MR No.", "NA"],
    ["diagnosis", "Diagnosis", ""], ["referred_by", "Referred By", ""],
    ["hospital_clinic", "Hospital / Clinic", ""], ["pin", "PIN", "NA"],
    ["sample_number", "Sample Number", "NA"], ["specimen", "Specimen", "Blood - EDTA"],
    ["collection_date", "Collection Date", ""], ["receipt_date", "Sample Receipt Date", ""],
    ["report_date", "Report Date", ""], ["match", "Match (e.g. '6 of 12 at High Resolution')", ""],
    ["remarks", "Remarks", ""],
  ];
  DONOR_FIELDS.forEach(([key, label, def]) => {
    const input = el("input", { type: "text", value: def, oninput: scheduleManualPreview });
    fieldsRef[key] = input;
    grid.appendChild(el("div", { class: "field" }, [el("label", {}, label), input]));
  });
  card.appendChild(grid);
  const hlaCard = buildHlaAlleleCard(prefix + "_donor", hlaFieldsRef, separateDrb);
  card.appendChild(hlaCard.querySelector(".allele-grid"));
  return card;
}

async function browseOutputFolder(inputEl, btnEl) {
  if (window.showDirectoryPicker) {
    try {
      const handle = await window.showDirectoryPicker({ mode: "readwrite" });
      _dirHandles[inputEl.id] = handle;
      inputEl.value = handle.name;
    } catch (e) {
      if (e.name !== "AbortError") showToast("Could not open folder picker.", "error");
    }
    return;
  }
  // Fallback for non-Chrome browsers
  const originalHtml = btnEl.innerHTML;
  btnEl.disabled = true;
  btnEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Waiting…';
  try {
    const r = await fetch(API + "/open-folder-dialog");
    const d = await r.json();
    if (d.path) { inputEl.value = d.path; delete _dirHandles[inputEl.id]; }
    else { inputEl.focus(); }
  } catch (e) {
    showToast("Could not open the folder dialog. Type the path manually.", "error");
    inputEl.focus();
  } finally {
    btnEl.disabled = false;
    btnEl.innerHTML = originalHtml;
  }
}

function buildGenBar(onGenerate) {
  const outputInput = el("input", { type: "text", id: "manualOutputInput", placeholder: "Output folder (leave blank for default backend/reports-hla)", style: "flex:1; padding:7px 10px; border:1px solid var(--input-border); border-radius:6px; font-size:11px;" });
  const browseBtn = el("button", { class: "btn-folder-sm" }, [el("i", { class: "fas fa-folder-open" }), " Browse"]);
  browseBtn.addEventListener("click", () => browseOutputFolder(outputInput, browseBtn));
  const row1 = el("div", { class: "gen-bar" }, [
    outputInput,
    browseBtn,
    el("button", { class: "btn-sm btn-primary", onclick: onGenerate }, [el("i", { class: "fas fa-file-pdf" }), " Generate Report"]),
  ]);
  const row2 = el("div", { class: "gen-bar" }, [
    el("button", { class: "btn-sm btn-outline", onclick: () => saveDraft("manual") }, [el("i", { class: "fas fa-save" }), " Save Draft"]),
    el("button", { class: "btn-sm btn-outline", onclick: () => loadDraft("manual") }, [el("i", { class: "fas fa-folder-open" }), " Load Draft"]),
    el("button", { class: "btn-sm btn-danger-outline", onclick: () => renderManualForm() }, [el("i", { class: "fas fa-eraser" }), " Clear Form"]),
  ]);
  return el("div", {}, [row1, row2]);
}

// Per-template field registries — rebuilt every render
let manualFields = {};
let manualHlaFields = {};
let manualDonorFields = [];
let manualDonorHlaFields = [];
let manualDonorPhotoBytes = [];   // base64 strings, one per donor, parallel to manualDonorFields
let manualPatientPhoto = { bytes: null };
let manualSpecialFields = {};
let manualDonorsListEl = null;    // DOM container for dynamically added/removed donor cards

function clearManualRefs() {
  manualFields = {};
  manualHlaFields = {};
  manualDonorFields = [];
  manualDonorHlaFields = [];
  manualDonorPhotoBytes = [];
  manualPatientPhoto = { bytes: null };
  manualSpecialFields = {};
  manualDonorsListEl = null;
}

const SPECIALIZED_RTYPES = [
  "cdc_crossmatch", "dsa_crossmatch", "flow_crossmatch", "luminex_typing",
  "kir_genotyping", "pra_class1", "pra_class2", "mixed_pra",
  "sab_class1", "sab_class2",
];

// Templates whose Donor Information section supports more than one donor
// (hla_report_generator.py _add_manual_donor / _remove_manual_donor).
const MULTI_DONOR_RTYPES = ["transplant_donor", "rpl_couple", "ngs_photo"];
// Templates with a dedicated patient/donor Photo upload field
// (hla_report_generator.py _upload_std_photo / _upload_cdc_photo / etc.).
const PHOTO_RTYPES = ["ngs_photo", "cdc_crossmatch", "dsa_crossmatch", "flow_crossmatch", "luminex_typing"];

function buildPhotoUploadField(label, onChange, existingB64 = null) {
  const fileInput = el("input", { type: "file", accept: "image/png,image/jpeg,image/bmp,image/tiff", class: "hidden" });
  const status = el("span", { style: "font-size:11px; color:var(--text-muted);" },
    existingB64 ? "Photo loaded." : "No photo selected.");
  const btn = el("button", { class: "btn-sm btn-outline", type: "button", onclick: () => fileInput.click() },
    [el("i", { class: "fas fa-camera" }), " Upload Photo"]);
  fileInput.addEventListener("change", () => {
    if (!fileInput.files.length) return;
    const file = fileInput.files[0];
    const reader = new FileReader();
    reader.onload = () => {
      onChange(reader.result.split(",")[1]);
      status.textContent = "Uploaded: " + file.name;
      scheduleManualPreview();
    };
    reader.readAsDataURL(file);
  });
  return el("div", { class: "field" }, [
    el("label", {}, label),
    el("div", { style: "display:flex; align-items:center; gap:10px;" }, [btn, fileInput, status]),
  ]);
}

// ── Multi-donor helpers (MULTI_DONOR_RTYPES: transplant_donor, rpl_couple, ngs_photo) ──
function buildManualDonorsSection(rtype, col) {
  const sectionTitle = rtype === "rpl_couple" ? "Spouse / Donor" : "Donor";
  const outerCard = el("div", { class: "card" });
  const hdr = el("div", { style: "display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;" }, [
    el("h3", { style: "margin:0;" }, [el("i", { class: "fas fa-user-friends" }), " Donors"]),
    el("button", { class: "btn-sm btn-outline", type: "button",
      onclick: () => addManualDonorCard(rtype, sectionTitle) },
      [el("i", { class: "fas fa-plus" }), " Add Donor"]),
  ]);
  outerCard.appendChild(hdr);
  manualDonorsListEl = el("div", {});
  outerCard.appendChild(manualDonorsListEl);
  col.appendChild(outerCard);
  addManualDonorCard(rtype, sectionTitle);
}

function addManualDonorCard(rtype, sectionTitle) {
  const idx = manualDonorFields.length;
  const df = {}, dhf = {}, photoRef = { bytes: null };
  manualDonorFields.push(df);
  manualDonorHlaFields.push(dhf);
  manualDonorPhotoBytes.push(photoRef);
  const separateDrb = isSeparateDrb(rtype);
  const cardTitle = sectionTitle + " " + (idx + 1);

  const card = el("div", { class: "card donor-card", style: "margin-bottom:8px; border:1px solid var(--card-border);" });
  const cardHdr = el("div", { style: "display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;" }, [
    el("h4", { style: "margin:0; font-size:13px;" }, [el("i", { class: "fas fa-user-friends" }), " " + cardTitle]),
  ]);
  const rmBtn = el("button", { class: "btn-sm btn-danger-outline", type: "button" }, [el("i", { class: "fas fa-times" }), " Remove"]);
  rmBtn.addEventListener("click", () => {
    const i = manualDonorFields.indexOf(df);
    if (i >= 0) { manualDonorFields.splice(i, 1); manualDonorHlaFields.splice(i, 1); manualDonorPhotoBytes.splice(i, 1); }
    card.remove();
    renumberManualDonorCards(sectionTitle);
    scheduleManualPreview();
  });
  cardHdr.appendChild(rmBtn);
  card.appendChild(cardHdr);

  const DONOR_FIELDS = [
    ["name", "Donor Name", ""], ["gender_age", "Gender / Age", ""],
    ["relationship", "Relationship", ""], ["hospital_mr_no", "Hospital MR No.", "NA"],
    ["diagnosis", "Diagnosis", ""], ["referred_by", "Referred By", ""],
    ["hospital_clinic", "Hospital / Clinic", ""], ["pin", "PIN", "NA"],
    ["sample_number", "Sample Number", "NA"], ["specimen", "Specimen", "Blood - EDTA"],
    ["collection_date", "Collection Date", ""], ["receipt_date", "Sample Receipt Date", ""],
    ["report_date", "Report Date", ""], ["match", "Match (e.g. '6 of 12 at High Resolution')", ""],
    ["remarks", "Remarks", ""],
  ];
  const grid = el("div", { class: "field-grid" });
  DONOR_FIELDS.forEach(([key, label, def]) => {
    const input = el("input", { type: "text", value: def, oninput: scheduleManualPreview });
    df[key] = input;
    grid.appendChild(el("div", { class: "field" }, [el("label", {}, label), input]));
  });
  card.appendChild(grid);

  const hlaWrapper = buildHlaAlleleCard("man_donor" + idx, dhf, separateDrb);
  card.appendChild(hlaWrapper.querySelector(".allele-grid"));

  if (rtype === "ngs_photo") {
    card.appendChild(buildPhotoUploadField("Donor Photo", b64 => { photoRef.bytes = b64; }));
  }

  if (manualDonorsListEl) manualDonorsListEl.appendChild(card);
  scheduleManualPreview();
}

function renumberManualDonorCards(sectionTitle) {
  if (!manualDonorsListEl) return;
  manualDonorsListEl.querySelectorAll(".donor-card h4").forEach((h, i) => {
    h.innerHTML = '<i class="fas fa-user-friends"></i> ' + sectionTitle + " " + (i + 1);
  });
}

function renderManualForm() {
  clearManualRefs();
  const col = document.getElementById("manualFormCol");
  col.innerHTML = "";
  const rtype = state.rtype;

  if (!SPECIALIZED_RTYPES.includes(rtype)) {
    col.appendChild(buildPatientInfoCard("man", manualFields));
  }

  if (rtype === "ngs_photo") {
    const photoCard = el("div", { class: "card" });
    photoCard.appendChild(el("h3", {}, [el("i", { class: "fas fa-camera" }), " Patient Photo"]));
    photoCard.appendChild(buildPhotoUploadField("Patient Photo", b64 => { manualPatientPhoto.bytes = b64; }));
    col.appendChild(photoCard);
  }

  if (["single_hla", "transplant_donor", "ngs_photo", "loci11", "rpl_couple", "single_rpl"].includes(rtype)) {
    col.appendChild(buildHlaAlleleCard("man_pat", manualHlaFields, isSeparateDrb(rtype)));
  }

  if (MULTI_DONOR_RTYPES.includes(rtype)) {
    buildManualDonorsSection(rtype, col);
  }

  if (rtype === "single_locus") {
    const card = el("div", { class: "card" }, [el("h3", {}, "Single Locus Result")]);
    const grid = el("div", { class: "field-grid" });
    [["Locus", "sl_locus"], ["Allele 1", "sl_allele1"], ["Allele 2", "sl_allele2"], ["Note (optional)", "sl_note"]].forEach(([lbl, key]) => {
      const input = el("input", { type: "text", oninput: scheduleManualPreview });
      manualSpecialFields[key] = input;
      grid.appendChild(el("div", { class: "field" }, [el("label", {}, lbl), input]));
    });
    card.appendChild(grid);
    col.appendChild(card);
  }

  if (rtype === "hla_c") {
    const card = el("div", { class: "card" }, [el("h3", {}, "HLA-C Result")]);
    const grid = el("div", { class: "field-grid" });
    [["Allele 1", "hc_allele1"], ["Allele 2", "hc_allele2"], ["Remark (Maternal HLA-C Type)", "hc_remark"]].forEach(([lbl, key]) => {
      const input = el("input", { type: "text", oninput: scheduleManualPreview });
      manualSpecialFields[key] = input;
      grid.appendChild(el("div", { class: "field" }, [el("label", {}, lbl), input]));
    });
    card.appendChild(grid);
    col.appendChild(card);
  }

  if (rtype === "cdc_crossmatch" || rtype === "dsa_crossmatch" || rtype === "flow_crossmatch") {
    buildCrossmatchSection(col, rtype);
  }

  if (rtype === "luminex_typing") {
    buildLuminexSection(col);
  }

  if (rtype === "kir_genotyping") {
    buildKirSection(col);
  }

  if (["pra_class1", "pra_class2", "mixed_pra"].includes(rtype)) {
    buildPraSection(col, rtype);
  }

  if (rtype === "sab_class1" || rtype === "sab_class2") {
    buildSabSection(col, rtype);
  }

  col.appendChild(buildGenBar(generateManual));
  scheduleManualPreview();
}

// ── CDC / DSA / Flow crossmatch section ──────────────────────────────────────
function buildCrossmatchSection(col, rtype) {
  const patCard = el("div", { class: "card" }, [el("h3", {}, [el("i", { class: "fas fa-user" }), " Patient (Crossmatch)"])]);
  const patGrid = el("div", { class: "field-grid" });
  const PAT_X_FIELDS = [["name", "Patient Name"], ["gender_age", "Gender / Age"], ["pin", "PIN"],
    ["sample_number", "Sample Number"], ["diagnosis", "Diagnosis"], ["hospital_clinic", "Hospital/Clinic"],
    ["sample_type", "Sample Type"], ["collection_date", "Collection Date"], ["receipt_date", "Receipt Date"],
    ["report_date", "Report Date"], ["remarks", "Remarks (optional)"], ["comments", "Additional Comment (optional)"]];
  const xf = { patient: {}, donor: {}, patientPhoto: null, donorPhoto: null };
  PAT_X_FIELDS.forEach(([k, l]) => {
    const input = el("input", { type: "text", oninput: scheduleManualPreview });
    xf.patient[k] = input;
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
  });
  patCard.appendChild(patGrid);
  patCard.appendChild(buildPhotoUploadField("Patient Photo", b64 => { xf.patientPhoto = b64; }));
  col.appendChild(patCard);

  const donCard = el("div", { class: "card" }, [el("h3", {}, [el("i", { class: "fas fa-user-friends" }), " Donor (Crossmatch)"])]);
  const donGrid = el("div", { class: "field-grid" });
  const DON_X_FIELDS = [["name", "Donor Name"], ["gender_age", "Gender / Age"], ["pin", "PIN"],
    ["sample_number", "Sample Number"], ["relationship", "Relationship"], ["sample_type", "Sample Type"],
    ["collection_date", "Collection Date"], ["receipt_date", "Receipt Date"], ["report_date", "Report Date"]];
  DON_X_FIELDS.forEach(([k, l]) => {
    const input = el("input", { type: "text", oninput: scheduleManualPreview });
    xf.donor[k] = input;
    donGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
  });
  donCard.appendChild(donGrid);
  donCard.appendChild(buildPhotoUploadField("Donor Photo", b64 => { xf.donorPhoto = b64; }));
  col.appendChild(donCard);

  manualSpecialFields.crossmatch = xf;

  const resCard = el("div", { class: "card" }, [el("h3", {}, "Results")]);
  const resGrid = el("div", { class: "field-grid" });
  if (rtype === "cdc_crossmatch") {
    const r = {};
    [["t_cell", "T-Cell Result"], ["b_cell", "B-Cell Result"], ["t_with_dtt", "T-Cell with DTT"],
     ["b_with_dtt", "B-Cell with DTT"]].forEach(([k, l]) => {
      const sel = el("select", { onchange: scheduleManualPreview }, [
        el("option", { value: "Negative" }, "Negative"), el("option", { value: "Positive" }, "Positive"), el("option", { value: "Doubtful" }, "Doubtful"),
      ]);
      r[k] = sel;
      resGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), sel]));
    });
    manualSpecialFields.cdc_results = r;
  } else if (rtype === "dsa_crossmatch") {
    const r = {};
    [["class1_result", "Class I Result"], ["class1_mfi", "Class I MFI"], ["class1_cutoff", "Class I Cutoff"],
     ["class2_result", "Class II Result"], ["class2_mfi", "Class II MFI"], ["class2_cutoff", "Class II Cutoff"]].forEach(([k, l]) => {
      const input = el("input", { type: "text", oninput: scheduleManualPreview });
      r[k] = input;
      resGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
    });
    manualSpecialFields.dsa_results = r;
  } else if (rtype === "flow_crossmatch") {
    const r = {};
    [["t_mcs", "T-Cells MCS"], ["t_interpretation", "T-Cells Interpretation"],
     ["b_mcs", "B-Cells MCS"], ["b_interpretation", "B-Cells Interpretation"]].forEach(([k, l]) => {
      const input = el("input", { type: "text", oninput: scheduleManualPreview });
      r[k] = input;
      resGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
    });
    const interpInput = el("input", { type: "text", placeholder: "Leave blank to auto-generate from MCS values", oninput: scheduleManualPreview });
    r.interpretation = interpInput;
    resGrid.appendChild(el("div", { class: "field full" }, [el("label", {}, "Interpretation Override (optional)"), interpInput]));
    manualSpecialFields.flow_results = r;
  }
  resCard.appendChild(resGrid);
  col.appendChild(resCard);
}

// ── Luminex section ────────────────────────────────────────────────────────
function buildLuminexSection(col) {
  const patCard = el("div", { class: "card" }, [el("h3", {}, "Patient")]);
  const patGrid = el("div", { class: "field-grid" });
  const lx = { patient: {}, donor: {}, patHla: {}, donHla: {}, patPhoto: null, donPhoto: null };
  [["patient_name", "Patient Name"], ["gender_age", "Gender / Age"], ["pin", "PIN"], ["sample_number", "Sample Number"],
   ["diagnosis", "Diagnosis"], ["hospital_clinic", "Hospital/Clinic"], ["relation", "Relation"],
   ["sample_type", "Sample Type"], ["collection_date", "Collection Date"], ["receipt_date", "Receipt Date"], ["report_date", "Report Date"]
  ].forEach(([k, l]) => {
    const input = el("input", { type: "text", oninput: scheduleManualPreview });
    lx.patient[k] = input;
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
  });
  patCard.appendChild(patGrid);
  patCard.appendChild(buildPhotoUploadField("Patient Photo", b64 => { lx.patPhoto = b64; }));
  col.appendChild(patCard);

  const patHlaCard = buildHlaAlleleCard("lx_pat", lx.patHla);
  col.appendChild(patHlaCard);

  const donCard = el("div", { class: "card" }, [el("h3", {}, "Donor")]);
  const donGrid = el("div", { class: "field-grid" });
  [["name", "Donor Name"], ["gender_age", "Gender / Age"], ["pin", "PIN"], ["sample_number", "Sample Number"],
   ["relation", "Relation"], ["sample_type", "Sample Type"], ["collection_date", "Collection Date"]
  ].forEach(([k, l]) => {
    const input = el("input", { type: "text", oninput: scheduleManualPreview });
    lx.donor[k] = input;
    donGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
  });
  donCard.appendChild(donGrid);
  donCard.appendChild(buildPhotoUploadField("Donor Photo", b64 => { lx.donPhoto = b64; }));
  col.appendChild(donCard);

  const donHlaCard = buildHlaAlleleCard("lx_don", lx.donHla);
  col.appendChild(donHlaCard);

  const interpCard = el("div", { class: "card" }, [el("h3", {}, "Interpretation")]);
  const interpInput = el("textarea", { oninput: scheduleManualPreview });
  lx.interpretation = interpInput;
  interpCard.appendChild(el("div", { class: "field full" }, [el("label", {}, "Interpretation"), interpInput]));
  col.appendChild(interpCard);

  const lxRemCard = el("div", { class: "card" }, [el("h3", {}, "Remarks / Comments")]);
  const lxRemarksInput = el("textarea", { oninput: scheduleManualPreview });
  const lxCommentsInput = el("textarea", { oninput: scheduleManualPreview });
  lx.patient.remarks = lxRemarksInput;
  lx.patient.comments = lxCommentsInput;
  lxRemCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), lxRemarksInput]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), lxCommentsInput]),
  ]));
  col.appendChild(lxRemCard);

  manualSpecialFields.luminex = lx;
}

// ── KIR section ────────────────────────────────────────────────────────────
const KIR_GENES = ["2DL1","2DL2","2DL3","2DL4","2DL5","2DS1","2DS2","2DS3","2DS4","2DS5","2DP1","3DL1","3DL2","3DL3","3DP1","3DS1"];

function buildKirSection(col) {
  const patCard = el("div", { class: "card" }, [el("h3", {}, "Patient")]);
  const patGrid = el("div", { class: "field-grid" });
  const kir = { patient: {}, genes: {} };
  [["patient_name", "Patient Name"], ["gender_age", "Gender / Age"], ["pin", "PIN"], ["sample_number", "Sample Number"],
   ["hospital_mr_no", "Hospital MR No."], ["specimen", "Specimen"], ["hospital_clinic", "Hospital/Clinic"],
   ["collection_date", "Collection Date"], ["receipt_date", "Receipt Date"], ["report_date", "Report Date"]
  ].forEach(([k, l]) => {
    const input = el("input", { type: "text", oninput: scheduleManualPreview });
    kir.patient[k] = input;
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
  });
  patCard.appendChild(patGrid);
  col.appendChild(patCard);

  const geneCard = el("div", { class: "card" }, [el("h3", {}, "KIR Genes (Present / Absent)")]);
  const geneGrid = el("div", { class: "field-grid cols-3" });
  KIR_GENES.forEach(g => {
    const sel = el("select", { onchange: scheduleManualPreview }, [
      el("option", { value: "Absent" }, "Absent"), el("option", { value: "Present" }, "Present"),
    ]);
    kir.genes[g] = sel;
    geneGrid.appendChild(el("div", { class: "field" }, [el("label", {}, "KIR" + g), sel]));
  });
  geneCard.appendChild(geneGrid);
  col.appendChild(geneCard);

  const gtCard = el("div", { class: "card" }, [el("h3", {}, "Genotype / Interpretation")]);
  const gtSel = el("select", { onchange: scheduleManualPreview }, [
    el("option", { value: "Auto" }, "Auto-calculate"), el("option", { value: "AA" }, "AA"), el("option", { value: "AB" }, "AB"), el("option", { value: "BB" }, "BB"),
  ]);
  kir.genotypeOverride = gtSel;
  const interp = el("textarea", { oninput: scheduleManualPreview });
  kir.interpretation = interp;
  gtCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field" }, [el("label", {}, "Genotype Override"), gtSel]),
    el("div", { class: "field full" }, [el("label", {}, "Interpretation"), interp]),
  ]));
  col.appendChild(gtCard);

  const kirRemCard = el("div", { class: "card" }, [el("h3", {}, "Remarks / Comments")]);
  const kirRemarksInput = el("textarea", { oninput: scheduleManualPreview });
  const kirCommentsInput = el("textarea", { oninput: scheduleManualPreview });
  kir.patient.remarks = kirRemarksInput;
  kir.patient.comments = kirCommentsInput;
  kirRemCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), kirRemarksInput]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), kirCommentsInput]),
  ]));
  col.appendChild(kirRemCard);

  manualSpecialFields.kir = kir;
}

// ── PRA section ───────────────────────────────────────────────────────────
function buildPraSection(col, rtype) {
  const patCard = el("div", { class: "card" }, [el("h3", {}, "Patient")]);
  const patGrid = el("div", { class: "field-grid" });
  const pra = { patient: {}, result: {} };
  [["patient_name", "Patient Name"], ["gender", "Gender"], ["age", "Age"], ["specimen", "Specimen"],
   ["hospital_clinic", "Hospital/Clinic"], ["pin", "PIN"], ["sample_number", "Sample Number"],
   ["collection_date", "Collection Date"], ["receipt_date", "Receipt Date"], ["report_date", "Report Date"]
  ].forEach(([k, l]) => {
    const input = el("input", { type: "text", oninput: scheduleManualPreview });
    pra.patient[k] = input;
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
  });
  patCard.appendChild(patGrid);
  col.appendChild(patCard);

  const resCard = el("div", { class: "card" }, [el("h3", {}, "Result")]);
  const resGrid = el("div", { class: "field-grid" });
  if (rtype === "mixed_pra") {
    const pct1 = el("input", { type: "text", placeholder: "e.g. 25" });
    const res1 = el("input", { type: "text", readonly: true,
      style: "background:#f1f5f9; color:var(--text-muted); cursor:default;" });
    const pct2 = el("input", { type: "text", placeholder: "e.g. 10" });
    const res2 = el("input", { type: "text", readonly: true,
      style: "background:#f1f5f9; color:var(--text-muted); cursor:default;" });

    function syncResults() {
      res1.value = praResultFor(pct1.value);
      res2.value = praResultFor(pct2.value);
      scheduleManualPreview();
    }
    pct1.addEventListener("input", syncResults);
    pct2.addEventListener("input", syncResults);

    pra.result.pra_percentage_1 = pct1; pra.result.pra_result_1 = res1;
    pra.result.pra_percentage_2 = pct2; pra.result.pra_result_2 = res2;

    [["% PRA Class I", pct1], ["Result Class I", res1],
     ["% PRA Class II", pct2], ["Result Class II", res2]].forEach(([l, inp]) => {
      resGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), inp]));
    });
  } else {
    [["pra_percentage", "% PRA"], ["pra_result", "Result (blank = auto)"]].forEach(([k, l]) => {
      const input = el("input", { type: "text", oninput: scheduleManualPreview });
      pra.result[k] = input;
      resGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
    });
  }
  resCard.appendChild(resGrid);
  col.appendChild(resCard);

  const praRemCard = el("div", { class: "card" }, [el("h3", {}, "Remarks / Comments")]);
  const praRemarksInput = el("textarea", { oninput: scheduleManualPreview });
  const praCommentsInput = el("textarea", { oninput: scheduleManualPreview });
  pra.patient.remarks = praRemarksInput;
  pra.patient.comments = praCommentsInput;
  praRemCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), praRemarksInput]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), praCommentsInput]),
  ]));
  col.appendChild(praRemCard);

  manualSpecialFields.pra = pra;
}

// ── SAB Class I / II section ──────────────────────────────────────────────
function applySabImportData(sab, data) {
  const fields = data.patient || {};
  Object.entries(fields).forEach(([k, v]) => {
    if (sab.patient[k] && v) sab.patient[k].value = v;
  });
  if (data.alleles && data.alleles.length) {
    sab.alleleTextarea.value = data.alleles.map(([a, m]) => `${a},${m}`).join("\n");
  }
  if (data.chart_bytes) {
    sab.chartBytes = data.chart_bytes;
    sab.chartStatus.textContent = "Chart imported from Excel.";
  }
  if (data.sab_class) {
    sab.classSelect.value = data.sab_class;
  }
  if (data.pra_pct != null) {
    sab.praInput.value = String(data.pra_pct);
  }
  applySabPraToRemarksComments(sab.praInput.value, sab.classSelect.value,
    sab.patient.remarks, sab.patient.comments);
  scheduleManualPreview();
}

function buildSabSection(col, rtype) {
  const sab = { patient: {} };
  manualSpecialFields.sab = sab;

  // ── Kit + Excel import ────────────────────────────────────────────────
  const importCard = el("div", { class: "card" }, [el("h3", {}, [el("i", { class: "fas fa-file-import" }), " Import from SAB Excel"])]);
  const kitSelect = el("select", {}, SAB_KIT_NAMES.map(k => el("option", { value: k }, k)));
  sab.kitSelect = kitSelect;
  const importStatus = el("span", { style: "font-size:11px; color:var(--text-muted);" }, "");
  const sabFileInput = el("input", { type: "file", accept: ".xlsx,.xls", class: "hidden" });
  const importBtn = el("button", { class: "btn-sm btn-outline", type: "button", onclick: () => sabFileInput.click() },
    [el("i", { class: "fas fa-upload" }), " Browse Excel…"]);
  sabFileInput.addEventListener("change", async () => {
    if (!sabFileInput.files.length) return;
    importStatus.textContent = "Parsing…";
    try {
      const fd = new FormData();
      fd.append("file", sabFileInput.files[0]);
      fd.append("kit", sabKitId(kitSelect.value));
      const r = await fetch("/hla/parse-sab-excel", { method: "POST", body: fd });
      if (!r.ok) {
        let msg = await r.text();
        try { msg = JSON.parse(msg).detail || msg; } catch (_) { /* not JSON */ }
        throw new Error(msg);
      }
      const data = await r.json();
      applySabImportData(sab, data);
      importStatus.textContent = "Imported: " + sabFileInput.files[0].name;
      showToast("SAB Excel imported successfully.", "success");
    } catch (e) {
      importStatus.textContent = "";
      showToast("SAB import error: " + e.message, "error");
    }
  });
  importCard.appendChild(el("div", { style: "display:flex; align-items:flex-end; gap:10px; flex-wrap:wrap;" }, [
    el("div", { class: "field" }, [el("label", {}, "Kit"), kitSelect]),
    el("div", { class: "field" }, [el("label", {}, " "), importBtn]),
    importStatus,
  ]));
  importCard.appendChild(sabFileInput);
  col.appendChild(importCard);

  // ── Patient Information ──────────────────────────────────────────────
  const patCard = el("div", { class: "card" }, [el("h3", {}, [el("i", { class: "fas fa-user" }), " Patient Information"])]);
  const patGrid = el("div", { class: "field-grid" });
  const SAB_PAT_FIELDS = [
    ["patient_name", "Patient Name *", ""], ["gender_age", "Gender / Age", ""],
    ["hospital_mr_no", "Hospital MR No", "NA"], ["specimen", "Specimen", "Serum"],
    ["hospital_clinic", "Hospital / Clinic", ""], ["pin", "PIN", ""],
    ["sample_number", "Sample Number", ""], ["collection_date", "Sample Collection Date (DD-MM-YYYY)", ""],
    ["receipt_date", "Sample Receipt Date (DD-MM-YYYY)", ""], ["report_date", "Report Date (DD-MM-YYYY)", ""],
  ];
  SAB_PAT_FIELDS.forEach(([key, label, def]) => {
    const input = el("input", { type: "text", value: def, oninput: scheduleManualPreview });
    sab.patient[key] = input;
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, label), input]));
  });
  patCard.appendChild(patGrid);
  col.appendChild(patCard);

  // ── SAB Class + % PRA ────────────────────────────────────────────────
  const classCard = el("div", { class: "card" }, [el("h3", {}, "SAB Class & % PRA")]);
  const classSelect = el("select", {}, [el("option", { value: "I" }, "I"), el("option", { value: "II" }, "II")]);
  classSelect.value = rtype === "sab_class2" ? "II" : "I";
  sab.classSelect = classSelect;
  const praInput = el("input", { type: "text", placeholder: "e.g. 79  -> fills Remarks & Comments" });
  sab.praInput = praInput;
  classCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field" }, [el("label", {}, "SAB Class"), classSelect]),
    el("div", { class: "field" }, [el("label", {}, "% PRA"), praInput]),
  ]));
  col.appendChild(classCard);

  // ── Remarks / Comments ───────────────────────────────────────────────
  const remCard = el("div", { class: "card" }, [el("h3", {}, "Remarks / Comments")]);
  const remarksInput = el("textarea", { oninput: scheduleManualPreview });
  const commentsInput = el("textarea", { oninput: scheduleManualPreview });
  sab.patient.remarks = remarksInput;
  sab.patient.comments = commentsInput;
  remCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), remarksInput]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), commentsInput]),
  ]));
  col.appendChild(remCard);

  const refreshPra = () => {
    applySabPraToRemarksComments(praInput.value, classSelect.value, remarksInput, commentsInput);
    scheduleManualPreview();
  };
  praInput.addEventListener("input", refreshPra);
  classSelect.addEventListener("change", refreshPra);

  // ── Allele Data ───────────────────────────────────────────────────────
  const alleleCard = el("div", { class: "card" }, [el("h3", {}, [el("i", { class: "fas fa-vial" }), " Allele Data (one per line: Allele,MFI)"])]);
  const alleleTextarea = el("textarea", {
    placeholder: "A*01:01,2126\nA*36:01,992\nDQA1*01:01, DQB1*05:01,1755",
    style: "min-height:140px; font-family:'Inter',sans-serif; font-size:12px;",
    oninput: scheduleManualPreview,
  });
  sab.alleleTextarea = alleleTextarea;
  alleleCard.appendChild(el("div", { class: "field full" }, [alleleTextarea]));
  col.appendChild(alleleCard);

  // ── Bead Specificity Chart ───────────────────────────────────────────
  const chartCard = el("div", { class: "card" }, [el("h3", {}, [el("i", { class: "fas fa-chart-bar" }), " Bead Specificity Chart"])]);
  const chartStatus = el("span", { style: "font-size:11px; color:var(--text-muted);" }, "No chart uploaded.");
  sab.chartStatus = chartStatus;
  const chartFileInput = el("input", { type: "file", accept: "image/*", class: "hidden" });
  const chartBtn = el("button", { class: "btn-sm btn-outline", type: "button", onclick: () => chartFileInput.click() },
    [el("i", { class: "fas fa-upload" }), " Upload Chart Image"]);
  chartFileInput.addEventListener("change", () => {
    if (!chartFileInput.files.length) return;
    const file = chartFileInput.files[0];
    const reader = new FileReader();
    reader.onload = () => {
      sab.chartBytes = reader.result.split(",")[1];
      chartStatus.textContent = "Uploaded: " + file.name;
      scheduleManualPreview();
    };
    reader.readAsDataURL(file);
  });
  chartCard.appendChild(el("div", { style: "display:flex; align-items:center; gap:10px;" }, [chartBtn, chartFileInput, chartStatus]));
  col.appendChild(chartCard);
}

// ══════════════════════════════════════════════════════════════════════════
// MANUAL TAB — CASE COLLECTION
// ══════════════════════════════════════════════════════════════════════════
function val(input) { return input ? input.value.trim() : ""; }
function checked(input) { return input ? input.checked : false; }

function collectAlleles(hlaFieldsObj) {
  const hla = {};
  Object.entries(hlaFieldsObj).forEach(([locus, [a1, a2]]) => {
    hla[locus] = [val(a1) || null, val(a2) || null];
  });
  return hla;
}

function collectManualCase() {
  const rtype = state.rtype;
  const nabl = checked(document.getElementById("globalNablChk"));
  const stamp = checked(document.getElementById("globalStampChk"));

  let patient, donors = [];

  if (rtype === "cdc_crossmatch" || rtype === "dsa_crossmatch" || rtype === "flow_crossmatch") {
    const xf = manualSpecialFields.crossmatch || { patient: {}, donor: {} };
    patient = emptyPerson({
      name: val(xf.patient.name), gender_age: val(xf.patient.gender_age), pin: val(xf.patient.pin),
      sample_number: val(xf.patient.sample_number), diagnosis: val(xf.patient.diagnosis) || "NA",
      hospital_clinic: val(xf.patient.hospital_clinic), sample_type: val(xf.patient.sample_type) || "Serum",
      collection_date: val(xf.patient.collection_date), receipt_date: val(xf.patient.receipt_date),
      report_date: val(xf.patient.report_date), photo_bytes: xf.patientPhoto || null,
      remarks: val(xf.patient.remarks), comments: val(xf.patient.comments),
    });
    const donor = emptyPerson({
      name: val(xf.donor.name), gender_age: val(xf.donor.gender_age), pin: val(xf.donor.pin) || "NA",
      sample_number: val(xf.donor.sample_number) || "NA", relationship: val(xf.donor.relationship),
      sample_type: val(xf.donor.sample_type) || "Sodium Heparin Whole Blood",
      collection_date: val(xf.donor.collection_date), receipt_date: val(xf.donor.receipt_date),
      report_date: val(xf.donor.report_date), photo_bytes: xf.donorPhoto || null,
    });
    donors = [donor];
    const c = { report_type: rtype, nabl, with_logo: state.withLogo, signature_stamp: stamp, patient, donors, rpl_reference: {} };
    if (rtype === "cdc_crossmatch") {
      const r = manualSpecialFields.cdc_results || {};
      c.cdc_results = {
        t_cell: r.t_cell ? r.t_cell.value : "Negative", b_cell: r.b_cell ? r.b_cell.value : "Negative",
        t_with_dtt: val(r.t_with_dtt) || "<10% Dead cells", t_without_dtt: val(r.t_with_dtt) || "<10% Dead cells",
        b_with_dtt: val(r.b_with_dtt) || "<10% Dead cells", b_without_dtt: val(r.b_with_dtt) || "<10% Dead cells",
      };
    } else if (rtype === "dsa_crossmatch") {
      const r = manualSpecialFields.dsa_results || {};
      c.dsa_results = {
        class1_result: val(r.class1_result) || "Negative", class1_mfi: val(r.class1_mfi),
        class1_cutoff: val(r.class1_cutoff) || ">1000", class2_result: val(r.class2_result) || "Negative",
        class2_mfi: val(r.class2_mfi), class2_cutoff: val(r.class2_cutoff) || ">1000",
      };
    } else if (rtype === "flow_crossmatch") {
      const r = manualSpecialFields.flow_results || {};
      c.flow_results = {
        t_mcs: val(r.t_mcs) || "<45", t_interpretation: val(r.t_interpretation) || "Negative",
        b_mcs: val(r.b_mcs) || "<86", b_interpretation: val(r.b_interpretation) || "Negative",
        interpretation: val(r.interpretation) || "",
      };
    }
    return c;
  }

  if (rtype === "luminex_typing") {
    const lx = manualSpecialFields.luminex || { patient: {}, donor: {}, patHla: {}, donHla: {} };
    patient = emptyPerson({
      name: val(lx.patient.patient_name), gender_age: val(lx.patient.gender_age), pin: val(lx.patient.pin) || "NA",
      sample_number: val(lx.patient.sample_number) || "NA", relation: val(lx.patient.relation) || "Patient",
      diagnosis: val(lx.patient.diagnosis) || "NA", hospital_clinic: val(lx.patient.hospital_clinic),
      sample_type: val(lx.patient.sample_type) || "EDTA Blood", collection_date: val(lx.patient.collection_date),
      receipt_date: val(lx.patient.receipt_date), report_date: val(lx.patient.report_date),
      hla: collectAlleles(lx.patHla),
      remarks: val(lx.patient.remarks),
    });
    patient.comments = val(lx.patient.comments);
    const donor = emptyPerson({
      name: val(lx.donor.name), gender_age: val(lx.donor.gender_age), pin: val(lx.donor.pin) || "NA",
      sample_number: val(lx.donor.sample_number) || "NA", relation: val(lx.donor.relation),
      sample_type: val(lx.donor.sample_type) || "EDTA Blood", collection_date: val(lx.donor.collection_date),
      hla: collectAlleles(lx.donHla),
    });
    return {
      report_type: rtype, nabl, with_logo: state.withLogo, signature_stamp: stamp,
      patient, donors: [donor], rpl_reference: {},
      luminex_interpretation: lx.interpretation ? lx.interpretation.value.trim() : "",
      luminex_pat_photo: lx.patPhoto || null,
      luminex_don_photo: lx.donPhoto || null,
    };
  }

  if (rtype === "kir_genotyping") {
    const kir = manualSpecialFields.kir || { patient: {}, genes: {} };
    patient = emptyPerson({
      name: val(kir.patient.patient_name), gender_age: val(kir.patient.gender_age), pin: val(kir.patient.pin),
      sample_number: val(kir.patient.sample_number), hospital_mr_no: val(kir.patient.hospital_mr_no) || "NA",
      specimen: val(kir.patient.specimen) || "Blood EDTA", hospital_clinic: val(kir.patient.hospital_clinic),
      collection_date: val(kir.patient.collection_date), receipt_date: val(kir.patient.receipt_date),
      report_date: val(kir.patient.report_date),
      remarks: val(kir.patient.remarks),
    });
    patient.comments = val(kir.patient.comments);
    const genes = {};
    Object.entries(kir.genes || {}).forEach(([g, sel]) => genes[g] = sel.value);
    return {
      report_type: rtype, nabl, with_logo: state.withLogo, signature_stamp: stamp,
      patient, donors: [], rpl_reference: {}, kir_genes: genes,
      kir_genotype_override: kir.genotypeOverride ? kir.genotypeOverride.value : "Auto",
      kir_interpretation: kir.interpretation ? kir.interpretation.value.trim() : "",
    };
  }

  if (["pra_class1", "pra_class2", "mixed_pra"].includes(rtype)) {
    const pra = manualSpecialFields.pra || { patient: {}, result: {} };
    patient = emptyPerson({
      name: val(pra.patient.patient_name), gender_age: "", pin: val(pra.patient.pin),
      sample_number: val(pra.patient.sample_number), hospital_clinic: val(pra.patient.hospital_clinic),
      specimen: val(pra.patient.specimen) || "Serum", collection_date: val(pra.patient.collection_date),
      receipt_date: val(pra.patient.receipt_date), report_date: val(pra.patient.report_date),
      remarks: val(pra.patient.remarks),
    });
    patient.comments = val(pra.patient.comments);
    patient.gender = val(pra.patient.gender);
    patient.age = val(pra.patient.age);
    const c = { report_type: rtype, nabl, with_logo: state.withLogo, signature_stamp: stamp, patient, donors: [], rpl_reference: {} };
    if (rtype === "mixed_pra") {
      c.pra_percentage_1 = val(pra.result.pra_percentage_1); c.pra_result_1 = val(pra.result.pra_result_1);
      c.pra_percentage_2 = val(pra.result.pra_percentage_2); c.pra_result_2 = val(pra.result.pra_result_2);
    } else {
      c.pra_percentage = val(pra.result.pra_percentage); c.pra_result = val(pra.result.pra_result);
      c.pra_class = rtype === "pra_class2" ? "II" : "I";
    }
    return c;
  }

  if (rtype === "sab_class1" || rtype === "sab_class2") {
    const sab = manualSpecialFields.sab || { patient: {} };
    patient = emptyPerson({
      name: val(sab.patient.patient_name), gender_age: val(sab.patient.gender_age),
      hospital_mr_no: val(sab.patient.hospital_mr_no) || "NA", specimen: val(sab.patient.specimen) || "Serum",
      hospital_clinic: val(sab.patient.hospital_clinic), pin: val(sab.patient.pin),
      sample_number: val(sab.patient.sample_number), collection_date: val(sab.patient.collection_date),
      receipt_date: val(sab.patient.receipt_date), report_date: val(sab.patient.report_date),
      remarks: val(sab.patient.remarks),
    });
    patient.comments = val(sab.patient.comments);
    const c = {
      report_type: rtype, nabl, with_logo: state.withLogo, signature_stamp: stamp,
      patient, donors: [], rpl_reference: {},
      sab_alleles: parseSabAlleleTextLocal(sab.alleleTextarea ? sab.alleleTextarea.value : ""),
      sab_chart_bytes: sab.chartBytes || null,
      sab_class: sab.classSelect ? sab.classSelect.value : (rtype === "sab_class2" ? "II" : "I"),
    };
    return c;
  }

  // Default: NGS / RPL / single locus / HLA-C templates
  patient = emptyPerson({
    name: val(manualFields.patient_name), gender_age: val(manualFields.gender_age),
    hospital_mr_no: val(manualFields.hospital_mr_no) || "NA", diagnosis: val(manualFields.diagnosis),
    referred_by: val(manualFields.referred_by), hospital_clinic: val(manualFields.hospital_clinic),
    pin: val(manualFields.pin), sample_number: val(manualFields.sample_number),
    specimen: val(manualFields.specimen) || "Blood - EDTA", collection_date: val(manualFields.collection_date),
    receipt_date: val(manualFields.receipt_date), report_date: val(manualFields.report_date),
    remarks: val(manualFields.remarks),
    hla: Object.keys(manualHlaFields).length ? collectAlleles(manualHlaFields) : emptyHla(),
    photo_bytes: rtype === "ngs_photo" ? (manualPatientPhoto.bytes || null) : null,
  });

  if (MULTI_DONOR_RTYPES.includes(rtype) && manualDonorFields.length) {
    donors = manualDonorFields.map((df, i) => {
      const dhf = manualDonorHlaFields[i] || {};
      const photoRef = manualDonorPhotoBytes[i] || { bytes: null };
      return emptyPerson({
        name: val(df.name), gender_age: val(df.gender_age), relationship: val(df.relationship),
        hospital_mr_no: val(df.hospital_mr_no) || "NA", diagnosis: val(df.diagnosis),
        referred_by: val(df.referred_by), hospital_clinic: val(df.hospital_clinic),
        pin: val(df.pin) || "NA", sample_number: val(df.sample_number) || "NA",
        specimen: val(df.specimen) || "Blood - EDTA",
        collection_date: val(df.collection_date), receipt_date: val(df.receipt_date),
        report_date: val(df.report_date), match: val(df.match), remarks: val(df.remarks),
        hla: Object.keys(dhf).length ? collectAlleles(dhf) : emptyHla(),
        photo_bytes: rtype === "ngs_photo" ? (photoRef.bytes || null) : null,
      });
    });
  }

  const c = { report_type: rtype, nabl, with_logo: state.withLogo, signature_stamp: stamp, patient, donors, rpl_reference: {} };

  if (rtype === "single_locus") {
    // Keys must match hla_template.py: case["locus"], case["sl_allele1"], case["sl_allele2"], case["sl_note"]
    c.locus      = manualSpecialFields.sl_locus   ? manualSpecialFields.sl_locus.value.trim()   : "";
    c.sl_allele1 = manualSpecialFields.sl_allele1 ? manualSpecialFields.sl_allele1.value.trim() : "";
    c.sl_allele2 = manualSpecialFields.sl_allele2 ? manualSpecialFields.sl_allele2.value.trim() : "";
    c.sl_note    = manualSpecialFields.sl_note    ? manualSpecialFields.sl_note.value.trim()    : "";
  }
  if (rtype === "hla_c") {
    // Keys must match hla_template.py: case["hlac_allele1"], case["hlac_allele2"], case["hlac_remark"]
    c.hlac_allele1 = manualSpecialFields.hc_allele1 ? manualSpecialFields.hc_allele1.value.trim() : "";
    c.hlac_allele2 = manualSpecialFields.hc_allele2 ? manualSpecialFields.hc_allele2.value.trim() : "";
    c.hlac_remark  = manualSpecialFields.hc_remark  ? manualSpecialFields.hc_remark.value.trim()  : "";
  }

  return c;
}

// ══════════════════════════════════════════════════════════════════════════
// MANUAL TAB — LIVE PREVIEW
// ══════════════════════════════════════════════════════════════════════════
function scheduleManualPreview() {
  clearTimeout(state.previewTimer);
  state.previewTimer = setTimeout(refreshManualPreview, 600);
}

function scheduleBulkPreview(i) {
  clearTimeout(state._bulkPreviewTimer);
  state._bulkPreviewTimer = setTimeout(() => previewBulkCase(i), 600);
}

async function refreshManualPreview() {
  const statusEl = document.getElementById("manualPreviewStatus");
  const body = document.getElementById("manualPreviewBody");
  _pdfTokens["manual"] = (_pdfTokens["manual"] || 0) + 1;
  const myTok = _pdfTokens["manual"];
  try {
    const c = collectManualCase();
    const isSab = c.report_type === "sab_class1" || c.report_type === "sab_class2";
    // SAB imports (especially Kit2/One Lambda) may carry only allele data with no
    // patient name yet — preview that content immediately rather than blocking on
    // a name the user hasn't typed in yet, matching the desktop app's behavior.
    const hasPreviewableContent = isSab
      ? ((c.patient && c.patient.name) || (c.sab_alleles && c.sab_alleles.length))
      : (c.patient && c.patient.name);
    if (!hasPreviewableContent) {
      body.innerHTML = '<div class="preview-placeholder">Fill in patient details to see a live preview.</div>';
      if (statusEl) statusEl.textContent = "";
      return;
    }
    if (statusEl) statusEl.textContent = "Generating...";
    body.innerHTML = '<div class="preview-placeholder" style="padding-top:40px;">Generating preview...</div>';
    const resp = await apiPost("/hla/preview", { case: c });
    if (_pdfTokens["manual"] !== myTok) return;
    if (!resp.preview_url) throw new Error("No preview URL returned.");
    const pdfResp = await fetch(resp.preview_url + "?t=" + Date.now(), {cache: "no-store"});
    if (!pdfResp.ok) throw new Error("PDF not found (" + pdfResp.status + ")");
    const buf = await pdfResp.arrayBuffer();
    if (_pdfTokens["manual"] !== myTok) return;
    body.innerHTML = "";
    await renderPdfToCanvas(buf, body, myTok, "manual");
    if (_pdfTokens["manual"] === myTok && statusEl) statusEl.textContent = "Updated " + new Date().toLocaleTimeString();
  } catch (e) {
    if (_pdfTokens["manual"] === myTok) {
      if (statusEl) statusEl.textContent = "Preview error.";
      body.innerHTML = '<div class="preview-placeholder">Preview error.</div>';
    }
  }
}

async function generateManual() {
  const c = collectManualCase();
  if (!c.patient || !c.patient.name) { showToast("Patient Name is required.", "error"); return; }
  const outputInput = document.getElementById("manualOutputInput");
  const dirHandle = outputInput && _dirHandles[outputInput.id];
  const outputDir = val(outputInput);
  try {
    const resp = await apiPost("/hla/generate", { case: c, output_dir: dirHandle ? undefined : (outputDir || undefined) });
    if (dirHandle && resp.download_url) {
      const pdfResp = await fetch(resp.download_url + "?t=" + Date.now(), { cache: "no-store" });
      if (!pdfResp.ok) throw new Error("Download failed (" + pdfResp.status + ")");
      const blob = await pdfResp.blob();
      const fh = await dirHandle.getFileHandle(resp.filename, { create: true });
      const writable = await fh.createWritable();
      await writable.write(blob);
      await writable.close();
    }
    showToast("Generated: " + resp.filename, "success");
    refreshManualPreview();
  } catch (e) {
    showToast("Error: " + e.message, "error");
  }
}

// ══════════════════════════════════════════════════════════════════════════
// MODAL HELPERS
// ══════════════════════════════════════════════════════════════════════════
function showInputModal(title, defaultValue) {
  return new Promise(resolve => {
    const backdrop = el("div", { class: "hla-modal-backdrop" });
    const input = el("input", { type: "text", value: defaultValue });
    const okBtn = el("button", { style: "background:var(--primary);color:#fff;border-color:var(--primary);" }, "Save");
    const cancelBtn = el("button", { style: "background:transparent;color:var(--text-muted);border-color:var(--input-border);" }, "Cancel");
    const modal = el("div", { class: "hla-modal" }, [
      el("h4", {}, title),
      input,
      el("div", { class: "hla-modal-actions" }, [cancelBtn, okBtn]),
    ]);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    input.focus(); input.select();
    const done = val => { document.body.removeChild(backdrop); resolve(val); };
    okBtn.addEventListener("click", () => done(input.value.trim() || null));
    cancelBtn.addEventListener("click", () => done(null));
    input.addEventListener("keydown", e => { if (e.key === "Enter") done(input.value.trim() || null); if (e.key === "Escape") done(null); });
    backdrop.addEventListener("click", e => { if (e.target === backdrop) done(null); });
  });
}

function showPickerModal(title, items) {
  return new Promise(resolve => {
    const backdrop = el("div", { class: "hla-modal-backdrop" });
    const list = el("div", { class: "hla-modal-list" });
    items.forEach(name => {
      const btn = el("button", { class: "hla-modal-item" }, name);
      btn.addEventListener("click", () => { document.body.removeChild(backdrop); resolve(name); });
      list.appendChild(btn);
    });
    const cancelBtn = el("button", { style: "background:transparent;color:var(--text-muted);border-color:var(--input-border);padding:7px 18px;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;border:1.5px solid;" }, "Cancel");
    cancelBtn.addEventListener("click", () => { document.body.removeChild(backdrop); resolve(null); });
    const modal = el("div", { class: "hla-modal" }, [
      el("h4", {}, title),
      list,
      el("div", { class: "hla-modal-actions" }, [cancelBtn]),
    ]);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    backdrop.addEventListener("click", e => { if (e.target === backdrop) { document.body.removeChild(backdrop); resolve(null); } });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// DRAFTS
// ══════════════════════════════════════════════════════════════════════════
async function saveDraft(scope) {
  const name = await showInputModal("Save Draft", scope === "manual" ? "manual_draft" : "bulk_draft");
  if (!name) return;
  const data = scope === "manual" ? { rtype: state.rtype, case: collectManualCase() } : { cases: state.bulkCases };
  try {
    await apiPost("/hla/drafts/save", { name, data });
    showToast("Draft saved: " + name, "success");
  } catch (e) { showToast("Error saving draft", "error"); }
}

async function loadDraft(scope) {
  try {
    const list = await apiGet("/hla/drafts");
    if (!list.drafts || !list.drafts.length) { showToast("No drafts found.", "error"); return; }
    const name = await showPickerModal("Select a Draft to Load", list.drafts);
    if (!name) return;
    const data = await apiGet("/hla/drafts/" + encodeURIComponent(name));
    if (scope === "manual" && data.case) {
      state.rtype = data.rtype || "single_hla";
      document.getElementById("templateSelect").value = Object.keys(TEMPLATE_TO_RTYPE).find(k => TEMPLATE_TO_RTYPE[k] === state.rtype) || "With CL";
      renderManualForm();
      setTimeout(() => populateManualForm(data.case), 50);
    } else if (scope === "bulk" && data.cases) {
      state.bulkCases = data.cases;
      renderBulkList();
    }
    showToast("Draft loaded: " + name, "success");
  } catch (e) { showToast("Error loading draft", "error"); }
}

function populateManualForm(c) {
  const p = c.patient || {};
  Object.entries(manualFields).forEach(([key, input]) => {
    const map = { patient_name: "name" };
    const pk = map[key] || key;
    if (p[pk] != null) input.value = p[pk];
  });
  if (p.hla) {
    Object.entries(manualHlaFields).forEach(([locus, [a1, a2]]) => {
      const pair = p.hla[locus] || ["", ""];
      a1.value = pair[0] || ""; a2.value = pair[1] || "";
    });
  }
  scheduleManualPreview();
}

function _downloadJson(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function saveBulkDraft() {
  if (!state.bulkCases.length) { showToast("No cases to save.", "error"); return; }
  _downloadJson(state.bulkCases, "hla_bulk_draft.json");
  showToast("Draft downloaded: hla_bulk_draft.json", "success");
}

function saveSelectedDraft() {
  if (!state.bulkSelected.size) { showToast("No cases selected.", "error"); return; }
  const cases = Array.from(state.bulkSelected).sort((a, b) => a - b).map(i => state.bulkCases[i]);
  _downloadJson(cases, "hla_selected_draft.json");
  showToast("Draft downloaded: hla_selected_draft.json (" + cases.length + " case" + (cases.length > 1 ? "s" : "") + ")", "success");
}

function loadBulkDraft() {
  document.getElementById("bulkDraftFileInput").click();
}

function _onBulkDraftFileChange(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const cases = JSON.parse(e.target.result);
      if (!Array.isArray(cases)) throw new Error("Expected a JSON array of cases.");
      state.bulkCases = cases;
      state.bulkSelected = new Set(cases.map((_, i) => i));
      renderBulkList();
      updateBulkSelectedCount();
      showToast("Loaded " + cases.length + " case" + (cases.length > 1 ? "s" : "") + " from draft.", "success");
    } catch (err) {
      showToast("Invalid draft file: " + err.message, "error");
    }
    input.value = "";
  };
  reader.readAsText(file);
}

function updateBulkSelectedCount() {
  const el = document.getElementById("bulkSelectedCount");
  if (el) el.textContent = state.bulkSelected.size + " of " + state.bulkCases.length + " selected";
}

function toggleBulkGenBar() {
  const panel = document.getElementById("bulkBottomControls");
  const btn = document.getElementById("bulkBottomToggle");
  if (!panel) return;
  const collapsed = panel.classList.toggle("collapsed");
  if (btn) btn.classList.toggle("collapsed", collapsed);
}

// ══════════════════════════════════════════════════════════════════════════
// BULK TAB
// ══════════════════════════════════════════════════════════════════════════
function initBulkTab() {
  const fi = document.getElementById("bulkFileInput");
  const zone = document.getElementById("bulkExcelZone");

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", e => {
    e.preventDefault(); zone.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      const dt = e.dataTransfer;
      const fileArr = Array.from(dt.files).filter(f => /\.(xlsx?|xls)$/i.test(f.name));
      if (!fileArr.length) { showToast("Please drop an Excel file (.xlsx / .xls).", "error"); return; }
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(fileArr[0]);
      fi.files = dataTransfer.files;
      updateExcelLabel(fi.files[0].name);
      parseBulkExcel();
    }
  });

  fi.addEventListener("change", () => {
    if (fi.files.length) {
      updateExcelLabel(fi.files[0].name);
      parseBulkExcel();
    }
  });

  function updateExcelLabel(name) {
    document.getElementById("bulkDropzoneLabel").textContent = name;
  }

  const bulkOutputBtn = document.getElementById("bulkOutputBrowseBtn");
  bulkOutputBtn.addEventListener("click", () => browseOutputFolder(document.getElementById("bulkOutputInput"), bulkOutputBtn));

  document.getElementById("bulkSearchBox").addEventListener("input", renderBulkList);
  document.getElementById("bulkSelectAllBtn").addEventListener("click", () => {
    state.bulkCases.forEach((_, i) => state.bulkSelected.add(i));
    renderBulkList(); updateBulkSelectedCount();
  });
  document.getElementById("bulkDeselectAllBtn").addEventListener("click", () => {
    state.bulkSelected.clear();
    renderBulkList(); updateBulkSelectedCount();
  });
  document.getElementById("bulkGenAllBtn").addEventListener("click", () => generateBulk(false));
  document.getElementById("bulkGenSelectedBtn").addEventListener("click", () => generateBulk(true));
  const draftFileInput = document.getElementById("bulkDraftFileInput");
  if (draftFileInput) draftFileInput.addEventListener("change", () => _onBulkDraftFileChange(draftFileInput));

  const sabKitSelect = document.getElementById("bulkSabKitSelect");
  SAB_KIT_NAMES.forEach(k => sabKitSelect.appendChild(el("option", { value: k }, k)));
  const sabFileInput = document.getElementById("bulkSabFileInput");
  document.getElementById("bulkSabImportBtn").addEventListener("click", () => sabFileInput.click());
  sabFileInput.addEventListener("change", async () => {
    const activeTab = document.querySelector(".tab.active")?.dataset.tab;
    if (activeTab === "manual") {
      await importSabToManual(sabFileInput, sabKitSelect);
    } else {
      await importBulkSabExcel(sabFileInput, sabKitSelect);
    }
  });
}

async function importSabToManual(sabFileInput, sabKitSelect) {
  if (!sabFileInput.files.length) return;
  const statusEl = document.getElementById("bulkSabImportStatus");
  statusEl.textContent = "Parsing…";
  try {
    const fd = new FormData();
    fd.append("file", sabFileInput.files[0]);
    fd.append("kit", sabKitId(sabKitSelect.value));
    const r = await fetch("/hla/parse-sab-excel", { method: "POST", body: fd });
    if (!r.ok) {
      let msg = await r.text();
      try { msg = JSON.parse(msg).detail || msg; } catch (_) { /* not JSON */ }
      throw new Error(msg);
    }
    const data = await r.json();
    const sabClass = data.sab_class || "I";
    const rtype = sabClass === "II" ? "sab_class2" : "sab_class1";
    state.rtype = rtype;
    const templateSelect = document.getElementById("templateSelect");
    if (templateSelect) templateSelect.value = RTYPE_TO_TEMPLATE_NAME[rtype] || "SAB Class I";
    renderManualForm();
    if (manualSpecialFields.sab) {
      applySabImportData(manualSpecialFields.sab, data);
    }
    statusEl.textContent = "Imported: " + sabFileInput.files[0].name;
    showToast("SAB Excel imported into manual form.", "success");
  } catch (e) {
    statusEl.textContent = "";
    showToast("SAB import error: " + e.message, "error");
  }
}

async function importBulkSabExcel(sabFileInput, sabKitSelect) {
  if (!sabFileInput.files.length) return;
  const statusEl = document.getElementById("bulkSabImportStatus");
  statusEl.textContent = "Parsing…";
  try {
    const fd = new FormData();
    fd.append("file", sabFileInput.files[0]);
    fd.append("kit", sabKitId(sabKitSelect.value));
    const r = await fetch("/hla/parse-sab-excel", { method: "POST", body: fd });
    if (!r.ok) {
      let msg = await r.text();
      try { msg = JSON.parse(msg).detail || msg; } catch (_) { /* not JSON */ }
      throw new Error(msg);
    }
    const data = await r.json();
    const sabClass = data.sab_class || "I";
    const fields = data.patient || {};
    const patient = emptyPerson({
      name: fields.patient_name || "", gender_age: fields.gender_age || "",
      hospital_mr_no: fields.hospital_mr_no || "NA", specimen: fields.specimen || "Serum",
      hospital_clinic: fields.hospital_clinic || "", pin: fields.pin || "",
      sample_number: fields.sample_number || "", collection_date: fields.collection_date || "",
      receipt_date: fields.receipt_date || "", report_date: fields.report_date || "",
    });
    patient.comments = "";
    if (data.pra_pct != null) {
      const sentence = sabPraSentence(String(data.pra_pct), sabClass);
      patient.remarks = sentence;
      patient.comments = sentence;
    }
    const newCase = {
      report_type: sabClass === "II" ? "sab_class2" : "sab_class1",
      nabl: checked(document.getElementById("globalNablChk")),
      with_logo: state.withLogo,
      signature_stamp: checked(document.getElementById("globalStampChk")),
      patient, donors: [], rpl_reference: {},
      sab_alleles: data.alleles || [],
      sab_chart_bytes: data.chart_bytes || null,
      sab_class: sabClass,
    };
    state.bulkCases = [newCase];
    state.bulkSelected = new Set([0]);
    state.bulkCurrentIndex = -1;
    renderBulkList();
    selectBulkCase(0);
    statusEl.textContent = "Imported: " + sabFileInput.files[0].name;
    showToast("SAB case loaded into bulk list.", "success");
  } catch (e) {
    statusEl.textContent = "";
    showToast("SAB import error: " + e.message, "error");
  }
}

async function parseBulkExcel() {
  const fi = document.getElementById("bulkFileInput");
  if (!fi.files.length) { showToast("Please select an Excel file first.", "error"); return; }
  const nabl = checked(document.getElementById("globalNablChk"));
  const fd = new FormData();
  fd.append("file", fi.files[0]);
  fd.append("nabl", nabl);
  try {
    showToast("Parsing Excel file…");
    const r = await fetch("/hla/parse-excel", { method: "POST", body: fd });
    if (!r.ok) {
      let msg = await r.text();
      try { msg = JSON.parse(msg).detail || msg; } catch (_) { /* not JSON, use raw text */ }
      throw new Error(msg);
    }
    const data = await r.json();
    state.bulkCases = data.cases || [];
    state.bulkSelected = new Set(state.bulkCases.map((_, i) => i));
    state.bulkCurrentIndex = -1;
    renderBulkList();
    showToast(`Parsed ${state.bulkCases.length} case(s).`, "success");
  } catch (e) {
    showToast("Parse error — see details below.", "error");
    const listEl = document.getElementById("bulkCaseList");
    listEl.innerHTML = "";
    listEl.appendChild(el("div", { style: "padding:14px; font-size:11.5px; color:var(--danger); line-height:1.5;" }, [
      el("i", { class: "fas fa-exclamation-triangle", style: "margin-right:6px;" }),
      e.message,
    ]));
  }
}

function renderBulkList() {
  updateBulkSelectedCount();
  const listEl = document.getElementById("bulkCaseList");
  listEl.innerHTML = "";
  if (!state.bulkCases.length) {
    listEl.innerHTML = '<div class="preview-placeholder" style="padding:20px;">No cases loaded yet.</div>';
    return;
  }
  const q = (document.getElementById("bulkSearchBox").value || "").toLowerCase();
  state.bulkCases.forEach((c, i) => {
    const patName = (c.patient && c.patient.name) || "Unnamed";
    const donors = c.donors || [];
    const donorNames = donors.map(d => d.name).filter(Boolean);
    const displayName = donorNames.length ? patName + " + " + donorNames.join(" + ") : patName;
    if (q && !displayName.toLowerCase().includes(q)) return;
    const chk = document.createElement("input");
    chk.type = "checkbox";
    chk.checked = state.bulkSelected.has(i);
    chk.addEventListener("click", (e) => { e.stopPropagation(); toggleBulkSelect(i, e.target.checked); });
    const item = el("div", { class: "case-item" + (i === state.bulkCurrentIndex ? " selected" : ""), onclick: () => selectBulkCase(i) }, [
      chk,
      el("span", { class: "ci-name" }, displayName),
    ]);
    listEl.appendChild(item);
  });
}

function toggleBulkSelect(i, isChecked) {
  if (isChecked) state.bulkSelected.add(i); else state.bulkSelected.delete(i);
  updateBulkSelectedCount();
}

function selectBulkCase(i) {
  state.bulkCurrentIndex = i;
  const c = state.bulkCases[i];
  const tplName = c && RTYPE_TO_TEMPLATE_NAME[c.report_type];
  if (tplName) {
    document.getElementById("templateSelect").value = tplName;
  }
  renderBulkList();
  renderBulkEditor(i);
  previewBulkCase(i);
}

// ── Shared bulk editor helper ──────────────────────────────────────────────
function _bulkRefreshRow(editCol, i) {
  // Refresh Preview button intentionally removed — preview auto-updates on case select
}

function _buildBulkPatientCard(p, patFields, onChange) {
  const card = el("div", { class: "card" }, [el("h3", {}, "Patient Information")]);
  const grid = el("div", { class: "field-grid" });
  patFields.forEach(([key, label]) => {
    const pk = key === "patient_name" ? "name" : key;
    const input = el("input", { type: "text", value: p[pk] || "" });
    input.addEventListener("input", () => { p[pk] = input.value; if (onChange) onChange(); });
    grid.appendChild(el("div", { class: "field" }, [el("label", {}, label), input]));
  });
  card.appendChild(grid);
  return card;
}

// ── Bulk Crossmatch (CDC / DSA / Flow) editor ──────────────────────────────
function renderBulkCrossmatchEditor(editCol, c, i) {
  const p = c.patient || {};
  const d = (c.donors || [])[0] || {};
  const refresh = () => scheduleBulkPreview(i);
  const PAT_X = [["patient_name","Patient Name"],["gender_age","Gender / Age"],["pin","PIN"],
    ["sample_number","Sample Number"],["diagnosis","Diagnosis"],["hospital_clinic","Hospital/Clinic"],
    ["sample_type","Sample Type"],["collection_date","Collection Date"],
    ["receipt_date","Receipt Date"],["report_date","Report Date"]];
  const patCard = _buildBulkPatientCard(p, PAT_X, refresh);
  patCard.appendChild(buildPhotoUploadField("Patient Photo",
    b64 => { p.photo_bytes = b64; refresh(); }, p.photo_bytes || null));
  editCol.appendChild(patCard);

  const donCard = el("div", { class: "card" }, [el("h3", {}, "Donor")]);
  const donGrid = el("div", { class: "field-grid" });
  [["name","Donor Name"],["gender_age","Gender / Age"],["pin","PIN"],
   ["sample_number","Sample Number"],["relationship","Relationship"],
   ["sample_type","Sample Type"],["collection_date","Collection Date"],
   ["receipt_date","Receipt Date"],["report_date","Report Date"]].forEach(([k,l]) => {
    const inp = el("input", { type: "text", value: d[k] || "" });
    inp.addEventListener("input", () => { d[k] = inp.value; refresh(); });
    donGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), inp]));
  });
  donCard.appendChild(donGrid);
  donCard.appendChild(buildPhotoUploadField("Donor Photo",
    b64 => { d.photo_bytes = b64; refresh(); }, d.photo_bytes || null));
  editCol.appendChild(donCard);

  const resCard = el("div", { class: "card" }, [el("h3", {}, "Results")]);
  const resGrid = el("div", { class: "field-grid" });
  if (c.report_type === "cdc_crossmatch") {
    const r = c.cdc_results || {};
    [["t_cell","T-Cell Result"],["b_cell","B-Cell Result"],
     ["t_with_dtt","T with DTT"],["b_with_dtt","B with DTT"]].forEach(([k,l]) => {
      const sel = el("select", {}, [
        el("option",{value:"Negative"},"Negative"),
        el("option",{value:"Positive"},"Positive"),
        el("option",{value:"Doubtful"},"Doubtful"),
      ]);
      sel.value = r[k] || "Negative";
      sel.addEventListener("change", () => { r[k] = sel.value; c.cdc_results = r; refresh(); });
      resGrid.appendChild(el("div",{class:"field"},[el("label",{},l),sel]));
    });
  } else if (c.report_type === "dsa_crossmatch") {
    const r = c.dsa_results || {};
    [["class1_result","Class I Result"],["class1_mfi","Class I MFI"],["class1_cutoff","Class I Cutoff"],
     ["class2_result","Class II Result"],["class2_mfi","Class II MFI"],["class2_cutoff","Class II Cutoff"]].forEach(([k,l]) => {
      const inp = el("input",{type:"text",value:r[k]||""});
      inp.addEventListener("input",()=>{r[k]=inp.value; c.dsa_results=r; refresh();});
      resGrid.appendChild(el("div",{class:"field"},[el("label",{},l),inp]));
    });
  } else {
    const r = c.flow_results || {};
    [["t_mcs","T-Cells MCS"],["t_interpretation","T-Cells Interpretation"],
     ["b_mcs","B-Cells MCS"],["b_interpretation","B-Cells Interpretation"]].forEach(([k,l]) => {
      const inp = el("input",{type:"text",value:r[k]||""});
      inp.addEventListener("input",()=>{r[k]=inp.value; c.flow_results=r; refresh();});
      resGrid.appendChild(el("div",{class:"field"},[el("label",{},l),inp]));
    });
  }
  resCard.appendChild(resGrid);
  editCol.appendChild(resCard);
  _bulkRefreshRow(editCol, i);
}

// ── Bulk Luminex editor ────────────────────────────────────────────────────
function renderBulkLuminexEditor(editCol, c, i) {
  const p = c.patient || {};
  const don = (c.donors || [])[0] || {};
  const refresh = () => scheduleBulkPreview(i);
  const PAT_LX = [["patient_name","Patient Name"],["gender_age","Gender / Age"],["pin","PIN"],
    ["sample_number","Sample Number"],["diagnosis","Diagnosis"],["hospital_clinic","Hospital/Clinic"],
    ["relation","Relation"],["sample_type","Sample Type"],["collection_date","Collection Date"],
    ["receipt_date","Receipt Date"],["report_date","Report Date"]];
  const patCard = _buildBulkPatientCard(p, PAT_LX, refresh);
  patCard.appendChild(buildPhotoUploadField("Patient Photo",
    b64 => { c.luminex_pat_photo = b64; refresh(); }, c.luminex_pat_photo || null));
  editCol.appendChild(patCard);

  if (p.hla) {
    const ph = el("div", { class: "card" }, [el("h3", {}, "Patient HLA")]);
    const phGrid = el("div", { class: "allele-grid" });
    HLA_LOCI.forEach(locus => {
      if (locus === "DRB3") {
        const pair = mergeDrb345ForDisplay(p.hla);
        const a1 = el("input",{type:"text",value:pair[0]||""});
        const a2 = el("input",{type:"text",value:pair[1]||""});
        a1.addEventListener("input",()=>{p.hla["DRB3"]=[a1.value,a2.value]; refresh();});
        a2.addEventListener("input",()=>{p.hla["DRB3"]=[a1.value,a2.value]; refresh();});
        phGrid.appendChild(el("div",{class:"allele-row"},[el("span",{class:"locus-lbl"},"DRB3/4/5"),a1,a2]));
      } else {
        const pair = p.hla[locus] || ["",""];
        const a1 = el("input",{type:"text",value:pair[0]||""});
        const a2 = el("input",{type:"text",value:pair[1]||""});
        a1.addEventListener("input",()=>{p.hla[locus]=[a1.value,a2.value]; refresh();});
        a2.addEventListener("input",()=>{p.hla[locus]=[a1.value,a2.value]; refresh();});
        phGrid.appendChild(el("div",{class:"allele-row"},[el("span",{class:"locus-lbl"},HLA_LOCUS_LABELS[locus]||locus),a1,a2]));
      }
    });
    ph.appendChild(phGrid);
    editCol.appendChild(ph);
  }

  const donCard = el("div", { class: "card" }, [el("h3", {}, "Donor")]);
  const donGrid = el("div", { class: "field-grid" });
  [["name","Donor Name"],["gender_age","Gender / Age"],["pin","PIN"],
   ["sample_number","Sample Number"],["relation","Relation"],
   ["sample_type","Sample Type"],["collection_date","Collection Date"]].forEach(([k,l]) => {
    const inp = el("input",{type:"text",value:don[k]||""});
    inp.addEventListener("input",()=>{don[k]=inp.value; refresh();});
    donGrid.appendChild(el("div",{class:"field"},[el("label",{},l),inp]));
  });
  donCard.appendChild(donGrid);
  donCard.appendChild(buildPhotoUploadField("Donor Photo",
    b64 => { c.luminex_don_photo = b64; refresh(); }, c.luminex_don_photo || null));
  editCol.appendChild(donCard);

  if (don.hla) {
    const dh = el("div", { class: "card" }, [el("h3", {}, "Donor HLA")]);
    const dhGrid = el("div", { class: "allele-grid" });
    HLA_LOCI.forEach(locus => {
      if (locus === "DRB3") {
        const pair = mergeDrb345ForDisplay(don.hla);
        const a1 = el("input",{type:"text",value:pair[0]||""});
        const a2 = el("input",{type:"text",value:pair[1]||""});
        a1.addEventListener("input",()=>{don.hla["DRB3"]=[a1.value,a2.value]; refresh();});
        a2.addEventListener("input",()=>{don.hla["DRB3"]=[a1.value,a2.value]; refresh();});
        dhGrid.appendChild(el("div",{class:"allele-row"},[el("span",{class:"locus-lbl"},"DRB3/4/5"),a1,a2]));
      } else {
        const pair = don.hla[locus]||["",""];
        const a1 = el("input",{type:"text",value:pair[0]||""});
        const a2 = el("input",{type:"text",value:pair[1]||""});
        a1.addEventListener("input",()=>{don.hla[locus]=[a1.value,a2.value]; refresh();});
        a2.addEventListener("input",()=>{don.hla[locus]=[a1.value,a2.value]; refresh();});
        dhGrid.appendChild(el("div",{class:"allele-row"},[el("span",{class:"locus-lbl"},HLA_LOCUS_LABELS[locus]||locus),a1,a2]));
      }
    });
    dh.appendChild(dhGrid);
    editCol.appendChild(dh);
  }

  const interpCard = el("div", { class: "card" }, [el("h3", {}, "Interpretation")]);
  const interpTA = el("textarea", {});
  interpTA.value = c.luminex_interpretation || "";
  interpTA.addEventListener("input", () => { c.luminex_interpretation = interpTA.value; refresh(); });
  interpCard.appendChild(el("div",{class:"field full"},[el("label",{},"Interpretation"),interpTA]));
  editCol.appendChild(interpCard);

  const lxRemCard = el("div", { class: "card" }, [el("h3", {}, "Remarks / Comments")]);
  const lxRemarksTA = el("textarea", { value: p.remarks || "" });
  lxRemarksTA.value = p.remarks || "";
  lxRemarksTA.addEventListener("input", () => { p.remarks = lxRemarksTA.value; refresh(); });
  const lxCommentsTA = el("textarea", {});
  lxCommentsTA.value = p.comments || "";
  lxCommentsTA.addEventListener("input", () => { p.comments = lxCommentsTA.value; refresh(); });
  lxRemCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), lxRemarksTA]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), lxCommentsTA]),
  ]));
  editCol.appendChild(lxRemCard);
  _bulkRefreshRow(editCol, i);
}

// ── Bulk KIR editor ────────────────────────────────────────────────────────
function renderBulkKirEditor(editCol, c, i) {
  const p = c.patient || {};
  const refresh = () => scheduleBulkPreview(i);
  const PAT_KIR = [["patient_name","Patient Name"],["gender_age","Gender / Age"],["pin","PIN"],
    ["sample_number","Sample Number"],["hospital_mr_no","Hospital MR No"],
    ["specimen","Specimen"],["hospital_clinic","Hospital/Clinic"],
    ["collection_date","Collection Date"],["receipt_date","Receipt Date"],["report_date","Report Date"]];
  editCol.appendChild(_buildBulkPatientCard(p, PAT_KIR, refresh));

  const geneCard = el("div", { class: "card" }, [el("h3", {}, "KIR Genes")]);
  const geneGrid = el("div", { class: "field-grid cols-3" });
  const genes = c.kir_genes || {};
  KIR_GENES.forEach(g => {
    const sel = el("select", {}, [el("option",{value:"Absent"},"Absent"),el("option",{value:"Present"},"Present")]);
    sel.value = genes[g] || "Absent";
    sel.addEventListener("change", () => { genes[g] = sel.value; c.kir_genes = genes; refresh(); });
    geneGrid.appendChild(el("div",{class:"field"},[el("label",{},"KIR"+g),sel]));
  });
  geneCard.appendChild(geneGrid);
  editCol.appendChild(geneCard);

  const gtCard = el("div", { class: "card" }, [el("h3", {}, "Genotype / Interpretation")]);
  const gtGrid = el("div", { class: "field-grid" });
  const gtSel = el("select", {}, [
    el("option",{value:"Auto"},"Auto"),el("option",{value:"AA"},"AA"),
    el("option",{value:"AB"},"AB"),el("option",{value:"BB"},"BB"),
  ]);
  gtSel.value = c.kir_genotype_override || "Auto";
  gtSel.addEventListener("change", () => { c.kir_genotype_override = gtSel.value; refresh(); });
  gtGrid.appendChild(el("div",{class:"field"},[el("label",{},"Genotype"),gtSel]));
  const interpTA = el("textarea", {});
  interpTA.value = c.kir_interpretation || "";
  interpTA.addEventListener("input", () => { c.kir_interpretation = interpTA.value; refresh(); });
  gtGrid.appendChild(el("div",{class:"field full"},[el("label",{},"Interpretation"),interpTA]));
  gtCard.appendChild(gtGrid);
  editCol.appendChild(gtCard);

  const kirRemCard = el("div", { class: "card" }, [el("h3", {}, "Remarks / Comments")]);
  const kirRemarksTA = el("textarea", { value: p.remarks || "" });
  kirRemarksTA.value = p.remarks || "";
  kirRemarksTA.addEventListener("input", () => { p.remarks = kirRemarksTA.value; refresh(); });
  const kirCommentsTA = el("textarea", {});
  kirCommentsTA.value = p.comments || "";
  kirCommentsTA.addEventListener("input", () => { p.comments = kirCommentsTA.value; refresh(); });
  kirRemCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), kirRemarksTA]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), kirCommentsTA]),
  ]));
  editCol.appendChild(kirRemCard);
  _bulkRefreshRow(editCol, i);
}

// ── Bulk PRA editor ────────────────────────────────────────────────────────
function renderBulkPraEditor(editCol, c, i) {
  const p = c.patient || {};
  const refresh = () => scheduleBulkPreview(i);
  const PAT_PRA = [["patient_name","Patient Name"],["gender","Gender"],["age","Age"],
    ["specimen","Specimen"],["hospital_clinic","Hospital/Clinic"],["pin","PIN"],
    ["sample_number","Sample Number"],["collection_date","Collection Date"],
    ["receipt_date","Receipt Date"],["report_date","Report Date"]];
  editCol.appendChild(_buildBulkPatientCard(p, PAT_PRA, refresh));

  const resCard = el("div", { class: "card" }, [el("h3", {}, "PRA Result")]);
  const resGrid = el("div", { class: "field-grid" });
  if (c.report_type === "mixed_pra") {
    [["pra_percentage_1","% PRA Class I"],["pra_result_1","Result Class I"],
     ["pra_percentage_2","% PRA Class II"],["pra_result_2","Result Class II"]].forEach(([k,l]) => {
      const inp = el("input",{type:"text",value:c[k]||""});
      inp.addEventListener("input",()=>{c[k]=inp.value; refresh();});
      resGrid.appendChild(el("div",{class:"field"},[el("label",{},l),inp]));
    });
  } else {
    [["pra_percentage","% PRA"],["pra_result","Result"]].forEach(([k,l]) => {
      const inp = el("input",{type:"text",value:c[k]||""});
      inp.addEventListener("input",()=>{c[k]=inp.value; refresh();});
      resGrid.appendChild(el("div",{class:"field"},[el("label",{},l),inp]));
    });
  }
  resCard.appendChild(resGrid);
  editCol.appendChild(resCard);

  const praRemCard = el("div", { class: "card" }, [el("h3", {}, "Remarks / Comments")]);
  const praRemarksTA = el("textarea", { value: p.remarks || "" });
  praRemarksTA.value = p.remarks || "";
  praRemarksTA.addEventListener("input", () => { p.remarks = praRemarksTA.value; refresh(); });
  const praCommentsTA = el("textarea", {});
  praCommentsTA.value = p.comments || "";
  praCommentsTA.addEventListener("input", () => { p.comments = praCommentsTA.value; refresh(); });
  praRemCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), praRemarksTA]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), praCommentsTA]),
  ]));
  editCol.appendChild(praRemCard);
  _bulkRefreshRow(editCol, i);
}

function renderBulkSabEditor(editCol, c, i) {
  const p = c.patient || {};
  const refresh = () => scheduleBulkPreview(i);

  const patCard = el("div", { class: "card" }, [el("h3", {}, "Patient Information")]);
  const patGrid = el("div", { class: "field-grid" });
  const SAB_BULK_FIELDS = [
    ["name", "Patient Name"], ["gender_age", "Gender / Age"], ["hospital_mr_no", "Hospital MR No"],
    ["specimen", "Specimen"], ["hospital_clinic", "Hospital / Clinic"], ["pin", "PIN"],
    ["sample_number", "Sample Number"], ["collection_date", "Collection Date"],
    ["receipt_date", "Receipt Date"], ["report_date", "Report Date"],
  ];
  SAB_BULK_FIELDS.forEach(([key, label]) => {
    const input = el("input", { type: "text", value: p[key] || "" });
    input.addEventListener("input", () => { p[key] = input.value; refresh(); });
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, label), input]));
  });
  patCard.appendChild(patGrid);
  editCol.appendChild(patCard);

  const classCard = el("div", { class: "card" }, [el("h3", {}, "SAB Class & % PRA")]);
  const classSelect = el("select", {}, [el("option", { value: "I" }, "I"), el("option", { value: "II" }, "II")]);
  classSelect.value = c.sab_class || "I";
  classSelect.addEventListener("change", () => {
    c.sab_class = classSelect.value;
    c.report_type = classSelect.value === "II" ? "sab_class2" : "sab_class1";
    renderBulkList();
  });
  classCard.appendChild(el("div", { class: "field" }, [el("label", {}, "SAB Class"), classSelect]));
  editCol.appendChild(classCard);

  const remCard = el("div", { class: "card" }, [el("h3", {}, "Remarks / Comments")]);
  const remarksInput = el("textarea", { value: p.remarks || "" });
  remarksInput.value = p.remarks || "";
  remarksInput.addEventListener("input", () => { p.remarks = remarksInput.value; refresh(); });
  const commentsInput = el("textarea", {});
  commentsInput.value = p.comments || "";
  commentsInput.addEventListener("input", () => { p.comments = commentsInput.value; refresh(); });
  remCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), remarksInput]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), commentsInput]),
  ]));
  editCol.appendChild(remCard);

  const alleleCard = el("div", { class: "card" }, [el("h3", {}, "Allele Data (one per line: Allele,MFI)")]);
  const alleleTextarea = el("textarea", { style: "min-height:140px; font-family:'Inter',sans-serif; font-size:12px;" });
  alleleTextarea.value = (c.sab_alleles || []).map(([a, m]) => `${a},${m}`).join("\n");
  alleleTextarea.addEventListener("input", () => {
    c.sab_alleles = parseSabAlleleTextLocal(alleleTextarea.value);
    refresh();
  });
  alleleCard.appendChild(el("div", { class: "field full" }, [alleleTextarea]));
  editCol.appendChild(alleleCard);

  const chartCard = el("div", { class: "card" }, [el("h3", {}, "Bead Specificity Chart")]);
  const chartStatus = el("span", { style: "font-size:11px; color:var(--text-muted);" },
    c.sab_chart_bytes ? "Chart attached." : "No chart uploaded.");
  const chartFileInput = el("input", { type: "file", accept: "image/*", class: "hidden" });
  const chartBtn = el("button", { class: "btn-sm btn-outline", type: "button", onclick: () => chartFileInput.click() },
    [el("i", { class: "fas fa-upload" }), " Upload Chart Image"]);
  chartFileInput.addEventListener("change", () => {
    if (!chartFileInput.files.length) return;
    const file = chartFileInput.files[0];
    const reader = new FileReader();
    reader.onload = () => {
      c.sab_chart_bytes = reader.result.split(",")[1];
      chartStatus.textContent = "Uploaded: " + file.name;
    };
    reader.readAsDataURL(file);
  });
  chartCard.appendChild(el("div", { style: "display:flex; align-items:center; gap:10px;" }, [chartBtn, chartFileInput, chartStatus]));
  editCol.appendChild(chartCard);
}

// DRB3/DRB4/DRB5 may be stored under any of the three keys (bulk Excel imports
// always merge them into "DRB3"; manual separate-mode entry stores each under
// its own key) — these mirror hla_template.py's _merged_drb345 / _split_drb345
// so the bulk editor displays whichever key actually has data.
function mergeDrb345ForDisplay(hla) {
  for (const k of ["DRB3", "DRB4", "DRB5"]) {
    const v = hla[k];
    if (v && v.some(x => x && String(x).trim())) return v;
  }
  return ["", ""];
}

function splitDrb345ForDisplay(hla) {
  const out = {};
  for (const k of ["DRB3", "DRB4", "DRB5"]) {
    const v = hla[k];
    if (!v || !v.some(x => x && String(x).trim())) continue;
    const a1 = v.find(x => x && String(x).trim()) || "";
    const m = String(a1).trim().match(/^(DRB[345])\*/i);
    out[m ? m[1].toUpperCase() : k] = v;
  }
  return out;
}

function renderBulkEditor(i) {
  const editCol = document.getElementById("bulkEditCol");
  editCol.innerHTML = "";
  const c = state.bulkCases[i];
  if (!c) return;

  if (c.report_type === "sab_class1" || c.report_type === "sab_class2") {
    renderBulkSabEditor(editCol, c, i);
    _bulkRefreshRow(editCol, i);
    return;
  }
  if (c.report_type === "cdc_crossmatch" || c.report_type === "dsa_crossmatch" || c.report_type === "flow_crossmatch") {
    renderBulkCrossmatchEditor(editCol, c, i);
    return;
  }
  if (c.report_type === "luminex_typing") {
    renderBulkLuminexEditor(editCol, c, i);
    return;
  }
  if (c.report_type === "kir_genotyping") {
    renderBulkKirEditor(editCol, c, i);
    return;
  }
  if (["pra_class1", "pra_class2", "mixed_pra"].includes(c.report_type)) {
    renderBulkPraEditor(editCol, c, i);
    return;
  }

  const p = c.patient || {};
  const separateDrb = isSeparateDrb(c.report_type);

  function buildHlaGrid(hla) {
    const hgrid = el("div", { class: "allele-grid" });
    function addRow(locus, label, pair) {
      const a1 = el("input", { type: "text", value: pair[0] || "" });
      const a2 = el("input", { type: "text", value: pair[1] || "" });
      a1.addEventListener("input", () => { hla[locus] = [a1.value, a2.value]; scheduleBulkPreview(i); });
      a2.addEventListener("input", () => { hla[locus] = [a1.value, a2.value]; scheduleBulkPreview(i); });
      hgrid.appendChild(el("div", { class: "allele-row" }, [el("span", { class: "locus-lbl" }, label), a1, a2]));
    }
    HLA_LOCI.forEach(locus => {
      if (locus === "DRB3" && separateDrb) {
        const split = splitDrb345ForDisplay(hla);
        addRow("DRB3", "DRB3", split.DRB3 || ["", ""]);
        addRow("DRB4", "DRB4", split.DRB4 || ["", ""]);
        addRow("DRB5", "DRB5", split.DRB5 || ["", ""]);
      } else if (locus === "DRB3") {
        addRow("DRB3", HLA_LOCUS_LABELS.DRB3, mergeDrb345ForDisplay(hla));
      } else {
        addRow(locus, HLA_LOCUS_LABELS[locus] || locus, hla[locus] || ["", ""]);
      }
    });
    return hgrid;
  }

  const card = el("div", { class: "card" }, [el("h3", {}, "Patient Information")]);
  const grid = el("div", { class: "field-grid" });
  const fields = {};
  PAT_FIELDS.forEach(([key, label]) => {
    const pk = key === "patient_name" ? "name" : key;
    const isRemarks = key === "remarks";
    const input = isRemarks
      ? el("textarea", { style: "resize:vertical; min-height:48px;" })
      : el("input", { type: "text", value: p[pk] || "" });
    if (isRemarks) input.value = p[pk] || "";
    fields[pk] = input;
    input.addEventListener("input", () => { p[pk] = input.value; scheduleBulkPreview(i); });
    grid.appendChild(el("div", { class: "field" + (isRemarks ? " full" : "") }, [el("label", {}, label), input]));
  });
  card.appendChild(grid);
  if (PHOTO_RTYPES.includes(c.report_type)) {
    const patPhotoKey = c.report_type === "luminex_typing" ? "luminex_pat_photo" : "photo_bytes";
    const existingPat = c.report_type === "luminex_typing" ? (c.luminex_pat_photo || null) : (p.photo_bytes || null);
    card.appendChild(buildPhotoUploadField("Patient Photo", b64 => {
      if (c.report_type === "luminex_typing") c.luminex_pat_photo = b64; else p.photo_bytes = b64;
    }, existingPat));
  }
  editCol.appendChild(card);

  const _hlaRtypes = ["single_hla","transplant_donor","ngs_photo","loci11","rpl_couple","single_rpl","hla_c","single_locus"];
  if (p.hla && _hlaRtypes.includes(c.report_type)) {
    const hlaCard = el("div", { class: "card" }, [el("h3", {}, "HLA Results")]);
    hlaCard.appendChild(buildHlaGrid(p.hla));
    editCol.appendChild(hlaCard);
  }

  (c.donors || []).forEach((d, di) => {
    const dCard = el("div", { class: "card" });
    const dHdr = el("div", { style: "display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;" }, [
      el("h3", { style: "margin:0;" }, `Donor ${di + 1}: ${d.name || ""}`),
    ]);
    if (MULTI_DONOR_RTYPES.includes(c.report_type)) {
      const rmBtn = el("button", { class: "btn-sm btn-danger-outline", type: "button",
        onclick: () => { c.donors.splice(di, 1); renderBulkEditor(i); } },
        [el("i", { class: "fas fa-times" }), " Remove"]);
      dHdr.appendChild(rmBtn);
    }
    dCard.appendChild(dHdr);
    const dgrid = el("div", { class: "field-grid" });
    ["name", "gender_age", "relationship", "pin", "sample_number", "match"].forEach(key => {
      const input = el("input", { type: "text", value: d[key] || "" });
      input.addEventListener("input", () => { d[key] = input.value; scheduleBulkPreview(i); });
      dgrid.appendChild(el("div", { class: "field" }, [el("label", {}, key.replace("_", " ")), input]));
    });
    dCard.appendChild(dgrid);
    if (d.hla) {
      dCard.appendChild(buildHlaGrid(d.hla));
    }
    if (PHOTO_RTYPES.includes(c.report_type)) {
      const donPhotoKey = c.report_type === "luminex_typing" ? "luminex_don_photo" : "photo_bytes";
      const existingDon = c.report_type === "luminex_typing" ? (c.luminex_don_photo || null) : (d.photo_bytes || null);
      dCard.appendChild(buildPhotoUploadField("Donor Photo", b64 => {
        if (c.report_type === "luminex_typing") c.luminex_don_photo = b64; else d.photo_bytes = b64;
      }, existingDon));
    }
    editCol.appendChild(dCard);
  });

  if (MULTI_DONOR_RTYPES.includes(c.report_type)) {
    const addDonorBtn = el("button", { class: "btn-sm btn-outline", type: "button",
      onclick: () => {
        c.donors = c.donors || [];
        c.donors.push(emptyPerson({ pin: "NA", sample_number: "NA", hla: emptyHla() }));
        renderBulkEditor(i);
      }
    }, [el("i", { class: "fas fa-plus" }), " Add Donor"]);
    editCol.appendChild(el("div", { style: "margin:6px 0;" }, [addDonorBtn]));
  }

}

async function previewBulkCase(i) {
  const c = state.bulkCases[i];
  if (!c) return;
  const statusEl = document.getElementById("bulkPreviewStatus");
  const body = document.getElementById("bulkPreviewBody");
  _pdfTokens["bulk"] = (_pdfTokens["bulk"] || 0) + 1;
  const myTok = _pdfTokens["bulk"];
  // Apply current logo/nabl/stamp settings to preview (bulk cases store parse-time values)
  const previewCase = { ...c, with_logo: state.withLogo,
    nabl: checked(document.getElementById("globalNablChk")),
    signature_stamp: checked(document.getElementById("globalStampChk")) };
  try {
    if (statusEl) statusEl.textContent = "Generating...";
    body.innerHTML = '<div class="preview-placeholder" style="padding-top:40px;">Generating preview...</div>';
    const resp = await apiPost("/hla/preview", { case: previewCase });
    if (_pdfTokens["bulk"] !== myTok) return;
    if (!resp.preview_url) throw new Error("No preview URL returned.");
    const pdfResp = await fetch(resp.preview_url + "?t=" + Date.now(), {cache: "no-store"});
    if (!pdfResp.ok) throw new Error("PDF not found (" + pdfResp.status + ")");
    const buf = await pdfResp.arrayBuffer();
    if (_pdfTokens["bulk"] !== myTok) return;
    body.innerHTML = "";
    await renderPdfToCanvas(buf, body, myTok, "bulk");
    if (_pdfTokens["bulk"] === myTok && statusEl) statusEl.textContent = "Updated " + new Date().toLocaleTimeString();
  } catch (e) {
    if (_pdfTokens["bulk"] === myTok) {
      if (statusEl) statusEl.textContent = "Preview error.";
      body.innerHTML = '<div class="preview-placeholder">Preview error.</div>';
    }
  }
}

async function generateBulk(selectedOnly) {
  const indices = selectedOnly ? Array.from(state.bulkSelected) : state.bulkCases.map((_, i) => i);
  if (!indices.length) { showToast("No cases to generate.", "error"); return; }
  const cases = indices.map(i => state.bulkCases[i]);
  const outputInput = document.getElementById("bulkOutputInput");
  const dirHandle = outputInput && _dirHandles[outputInput.id];
  const outputDir = val(outputInput);
  const withLogo = checked(document.getElementById("bulkLogoChk"));
  const stamp = checked(document.getElementById("globalStampChk"));

  const progWrap = document.getElementById("bulkProgressWrap");
  const progBar = document.getElementById("bulkProgressBar");
  progWrap.classList.remove("hidden");
  progBar.style.width = "10%";

  try {
    const resp = await apiPost("/hla/generate-bulk", { cases, output_dir: dirHandle ? undefined : (outputDir || undefined), with_logo: withLogo, signature_stamp: stamp });
    progBar.style.width = "70%";
    if (dirHandle && resp.success && resp.success.length) {
      let written = 0;
      for (const item of resp.success) {
        if (item.download_url) {
          try {
            const pdfResp = await fetch(item.download_url + "?t=" + Date.now(), { cache: "no-store" });
            if (pdfResp.ok) {
              const blob = await pdfResp.blob();
              const fh = await dirHandle.getFileHandle(item.filename, { create: true });
              const writable = await fh.createWritable();
              await writable.write(blob);
              await writable.close();
              written++;
            }
          } catch (_) { /* best effort */ }
        }
      }
      progBar.style.width = "100%";
      showToast(`Saved ${written} of ${resp.success.length} report(s) to folder${resp.failed.length ? ", " + resp.failed.length + " failed" : ""}.`, resp.failed.length ? "error" : "success");
    } else {
      progBar.style.width = "100%";
      showToast(`Generated ${resp.success.length} report(s), ${resp.failed.length} failed.`, resp.failed.length ? "error" : "success");
    }
  } catch (e) {
    showToast("Bulk generation error: " + e.message, "error");
  } finally {
    setTimeout(() => { progWrap.classList.add("hidden"); progBar.style.width = "0%"; }, 1500);
  }
}

// ══════════════════════════════════════════════════════════════════════════
// SETTINGS TAB
// ══════════════════════════════════════════════════════════════════════════
async function initSettingsTab() {
  try {
    state.settings = await apiGet("/hla/settings");
  } catch (e) { /* use defaults */ }

  document.getElementById("settLogoChk").checked = state.settings.with_logo;
  document.getElementById("settNablChk").checked = state.settings.nabl;
  document.getElementById("settStampChk").checked = state.settings.signature_stamp;

  renderSigCountGrid();
  renderSigTable();

  document.getElementById("sigAddBtn").addEventListener("click", () => {
    state.settings.signatories.push({ name: "New Signatory", title: "Title" });
    renderSigTable();
  });
  document.getElementById("sigResetBtn").addEventListener("click", () => {
    state.settings.signatories = JSON.parse(JSON.stringify(DEFAULT_SIGNATORIES));
    renderSigTable();
  });
  document.getElementById("sigSaveBtn").addEventListener("click", saveAllSettings);
}

function renderSigCountGrid() {
  const grid = document.getElementById("sigCountGrid");
  grid.innerHTML = "";
  REPORT_TEMPLATES.forEach(t => {
    const input = el("input", { type: "number", min: "1", max: "5", value: state.settings.sig_counts[t.report_type] ?? DEFAULT_SIG_COUNTS[t.report_type] ?? 2 });
    input.addEventListener("change", () => { state.settings.sig_counts[t.report_type] = parseInt(input.value, 10) || 2; });
    grid.appendChild(el("div", { class: "sig-count-item" }, [el("span", {}, t.name), input]));
  });
}

function renderSigTable() {
  const tbody = document.getElementById("sigTableBody");
  tbody.innerHTML = "";
  state.settings.signatories.forEach((sig, i) => {
    const nameInput = el("input", { type: "text", value: sig.name });
    nameInput.addEventListener("input", () => { sig.name = nameInput.value; });
    const titleInput = el("input", { type: "text", value: sig.title });
    titleInput.addEventListener("input", () => { sig.title = titleInput.value; });
    const upBtn = el("button", { class: "btn-sm btn-outline", style: "padding:3px 8px;", onclick: () => { if (i > 0) { [state.settings.signatories[i-1], state.settings.signatories[i]] = [state.settings.signatories[i], state.settings.signatories[i-1]]; renderSigTable(); } } }, [el("i", { class: "fas fa-arrow-up" })]);
    const dnBtn = el("button", { class: "btn-sm btn-outline", style: "padding:3px 8px;", onclick: () => { if (i < state.settings.signatories.length - 1) { [state.settings.signatories[i+1], state.settings.signatories[i]] = [state.settings.signatories[i], state.settings.signatories[i+1]]; renderSigTable(); } } }, [el("i", { class: "fas fa-arrow-down" })]);
    const rmBtn = el("button", { class: "btn-sm btn-danger-outline", style: "padding:3px 8px;", onclick: () => { state.settings.signatories.splice(i, 1); renderSigTable(); } }, [el("i", { class: "fas fa-trash" })]);
    const row = el("tr", {}, [
      el("td", {}, nameInput), el("td", {}, titleInput),
      el("td", {}, [upBtn, dnBtn, rmBtn]),
    ]);
    tbody.appendChild(row);
  });
}

async function saveAllSettings() {
  state.settings.with_logo = checked(document.getElementById("settLogoChk"));
  state.settings.nabl = checked(document.getElementById("settNablChk"));
  state.settings.signature_stamp = checked(document.getElementById("settStampChk"));
  try {
    await apiPost("/hla/settings", state.settings);
    showToast("Settings saved successfully.", "success");
  } catch (e) {
    showToast("Error saving settings.", "error");
  }
}

// ══════════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════════
window.addEventListener("DOMContentLoaded", async () => {
  initTemplateSelect();
  renderManualForm();
  initBulkTab();
  await initSettingsTab();
  document.body.classList.add("loaded");

  document.getElementById("manualRefreshBtn")?.addEventListener("click", refreshManualPreview);
  document.getElementById("bulkRefreshBtn")?.addEventListener("click", () => {
    if (state.bulkCurrentIndex >= 0) previewBulkCase(state.bulkCurrentIndex);
  });

  // Set PDF.js worker after script loads
  const pdfLib = window['pdfjs-dist/build/pdf'];
  if (pdfLib) pdfLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
});
