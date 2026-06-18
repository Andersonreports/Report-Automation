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
  settings: { signatories: DEFAULT_SIGNATORIES, sig_counts: { ...DEFAULT_SIG_COUNTS }, with_logo: true, nabl: true, signature_stamp: false },
};

// ── Helpers ─────────────────────────────────────────────────────────────────
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
  if (!r.ok) { const t = await r.text(); throw new Error(t); }
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
      state.rtype = newRtype;
      renderManualForm();
    }
  });
  document.getElementById("logoSelect").addEventListener("change", e => {
    state.withLogo = e.target.value === "true";
    scheduleManualPreview();
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

function buildHlaAlleleCard(prefix, hlaFieldsRef) {
  const card = el("div", { class: "card" }, [
    el("h3", {}, [el("i", { class: "fas fa-dna" }), " HLA Results"]),
  ]);
  const grid = el("div", { class: "allele-grid" });
  grid.appendChild(el("div", { class: "allele-row" }, [
    el("span", {}, ""), el("span", { style: "font-size:10px;font-weight:700;color:var(--text-muted);" }, "ALLELE 1"),
    el("span", { style: "font-size:10px;font-weight:700;color:var(--text-muted);" }, "ALLELE 2"),
  ]));
  HLA_LOCI.forEach(locus => {
    const a1 = el("input", { type: "text", placeholder: "e.g. A*02:01:01", id: `${prefix}_${locus}_1`, oninput: scheduleManualPreview });
    const a2 = el("input", { type: "text", placeholder: "Allele 2", id: `${prefix}_${locus}_2`, oninput: scheduleManualPreview });
    hlaFieldsRef[locus] = [a1, a2];
    grid.appendChild(el("div", { class: "allele-row" }, [
      el("span", { class: "locus-lbl" }, HLA_LOCUS_LABELS[locus] || locus), a1, a2,
    ]));
  });
  card.appendChild(grid);
  return card;
}

function buildDonorCard(prefix, fieldsRef, hlaFieldsRef, title = "Donor Information") {
  const card = el("div", { class: "card" }, [
    el("h3", {}, [el("i", { class: "fas fa-user-friends" }), " " + title]),
  ]);
  const grid = el("div", { class: "field-grid" });
  const DONOR_FIELDS = [
    ["name", "Donor Name", ""], ["gender_age", "Gender / Age", ""],
    ["relationship", "Relationship", ""], ["pin", "PIN", "NA"],
    ["sample_number", "Sample Number", "NA"], ["collection_date", "Collection Date", ""],
    ["receipt_date", "Sample Receipt Date", ""], ["report_date", "Report Date", ""],
    ["match", "Match (e.g. '6 of 12 at High Resolution')", ""],
  ];
  DONOR_FIELDS.forEach(([key, label, def]) => {
    const input = el("input", { type: "text", value: def, oninput: scheduleManualPreview });
    fieldsRef[key] = input;
    grid.appendChild(el("div", { class: "field" }, [el("label", {}, label), input]));
  });
  card.appendChild(grid);
  const hlaCard = buildHlaAlleleCard(prefix + "_donor", hlaFieldsRef);
  card.appendChild(hlaCard.querySelector(".allele-grid"));
  return card;
}

function buildGenBar(onGenerate) {
  const outputInput = el("input", { type: "text", id: "manualOutputInput", placeholder: "Output folder (leave blank for default backend/reports-hla)", style: "flex:1; padding:7px 10px; border:1px solid var(--input-border); border-radius:6px; font-size:11px;" });
  const bar = el("div", { class: "gen-bar" }, [
    outputInput,
    el("button", { class: "btn-sm btn-primary", onclick: onGenerate }, [el("i", { class: "fas fa-file-pdf" }), " Generate Report"]),
    el("button", { class: "btn-sm btn-outline", onclick: () => saveDraft("manual") }, [el("i", { class: "fas fa-save" }), " Save Draft"]),
    el("button", { class: "btn-sm btn-outline", onclick: () => loadDraft("manual") }, [el("i", { class: "fas fa-folder-open" }), " Load Draft"]),
    el("button", { class: "btn-sm btn-danger-outline", onclick: () => renderManualForm() }, [el("i", { class: "fas fa-eraser" }), " Clear Form"]),
  ]);
  return bar;
}

// Per-template field registries — rebuilt every render
let manualFields = {};
let manualHlaFields = {};
let manualDonorFields = [];
let manualDonorHlaFields = [];
let manualSpecialFields = {};

function clearManualRefs() {
  manualFields = {};
  manualHlaFields = {};
  manualDonorFields = [];
  manualDonorHlaFields = [];
  manualSpecialFields = {};
}

const SPECIALIZED_RTYPES = [
  "cdc_crossmatch", "dsa_crossmatch", "flow_crossmatch", "luminex_typing",
  "kir_genotyping", "pra_class1", "pra_class2", "mixed_pra",
  "sab_class1", "sab_class2",
];

function renderManualForm() {
  clearManualRefs();
  const col = document.getElementById("manualFormCol");
  col.innerHTML = "";
  const rtype = state.rtype;

  if (!SPECIALIZED_RTYPES.includes(rtype)) {
    col.appendChild(buildPatientInfoCard("man", manualFields));
  }

  if (["single_hla", "transplant_donor", "ngs_photo", "loci11", "rpl_couple", "single_rpl"].includes(rtype)) {
    col.appendChild(buildHlaAlleleCard("man_pat", manualHlaFields));
  }

  if (["transplant_donor", "rpl_couple"].includes(rtype)) {
    const df = {}; const dhf = {};
    manualDonorFields.push(df); manualDonorHlaFields.push(dhf);
    col.appendChild(buildDonorCard("man", df, dhf, rtype === "rpl_couple" ? "Spouse / Donor (RPL Couple)" : "Donor Information"));
  }

  if (rtype === "single_locus") {
    const card = el("div", { class: "card" }, [el("h3", {}, "Single Locus Result")]);
    const grid = el("div", { class: "field-grid" });
    ["Locus", "Allele 1", "Allele 2"].forEach((lbl, i) => {
      const input = el("input", { type: "text", oninput: scheduleManualPreview });
      manualSpecialFields[`sl_${i}`] = input;
      grid.appendChild(el("div", { class: "field" }, [el("label", {}, lbl), input]));
    });
    card.appendChild(grid);
    col.appendChild(card);
  }

  if (rtype === "hla_c") {
    const card = el("div", { class: "card" }, [el("h3", {}, "HLA-C Result")]);
    const grid = el("div", { class: "field-grid" });
    ["Allele 1", "Allele 2", "Supertype (C1/C2)"].forEach((lbl, i) => {
      const input = el("input", { type: "text", oninput: scheduleManualPreview });
      manualSpecialFields[`hc_${i}`] = input;
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
    ["report_date", "Report Date"]];
  const xf = { patient: {}, donor: {} };
  PAT_X_FIELDS.forEach(([k, l]) => {
    const input = el("input", { type: "text", oninput: scheduleManualPreview });
    xf.patient[k] = input;
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
  });
  patCard.appendChild(patGrid);
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
    manualSpecialFields.flow_results = r;
  }
  resCard.appendChild(resGrid);
  col.appendChild(resCard);
}

// ── Luminex section ────────────────────────────────────────────────────────
function buildLuminexSection(col) {
  const patCard = el("div", { class: "card" }, [el("h3", {}, "Patient")]);
  const patGrid = el("div", { class: "field-grid" });
  const lx = { patient: {}, donor: {}, patHla: {}, donHla: {} };
  [["patient_name", "Patient Name"], ["gender_age", "Gender / Age"], ["pin", "PIN"], ["sample_number", "Sample Number"],
   ["diagnosis", "Diagnosis"], ["hospital_clinic", "Hospital/Clinic"], ["relation", "Relation"],
   ["sample_type", "Sample Type"], ["collection_date", "Collection Date"], ["receipt_date", "Receipt Date"], ["report_date", "Report Date"]
  ].forEach(([k, l]) => {
    const input = el("input", { type: "text", oninput: scheduleManualPreview });
    lx.patient[k] = input;
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
  });
  patCard.appendChild(patGrid);
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
  col.appendChild(donCard);

  const donHlaCard = buildHlaAlleleCard("lx_don", lx.donHla);
  col.appendChild(donHlaCard);

  const interpCard = el("div", { class: "card" }, [el("h3", {}, "Interpretation")]);
  const interpInput = el("textarea", { oninput: scheduleManualPreview });
  lx.interpretation = interpInput;
  interpCard.appendChild(el("div", { class: "field full" }, [el("label", {}, "Interpretation"), interpInput]));
  col.appendChild(interpCard);

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
    [["pra_percentage_1", "% PRA Class I"], ["pra_result_1", "Result Class I"],
     ["pra_percentage_2", "% PRA Class II"], ["pra_result_2", "Result Class II"]].forEach(([k, l]) => {
      const input = el("input", { type: "text", oninput: scheduleManualPreview });
      pra.result[k] = input;
      resGrid.appendChild(el("div", { class: "field" }, [el("label", {}, l), input]));
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
  importCard.appendChild(el("div", { style: "display:flex; align-items:center; gap:10px; flex-wrap:wrap;" }, [
    el("div", { class: "field" }, [el("label", {}, "Kit"), kitSelect]),
    importBtn, sabFileInput, importStatus,
  ]));
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
  const classCard = el("div", { class: "card" }, [el("h3", {}, "SAB Class &amp; % PRA")]);
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
    style: "min-height:140px; font-family:'Courier New',monospace; font-size:11px;",
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
      report_date: val(xf.patient.report_date),
    });
    const donor = emptyPerson({
      name: val(xf.donor.name), gender_age: val(xf.donor.gender_age), pin: val(xf.donor.pin) || "NA",
      sample_number: val(xf.donor.sample_number) || "NA", relationship: val(xf.donor.relationship),
      sample_type: val(xf.donor.sample_type) || "Sodium Heparin Whole Blood",
      collection_date: val(xf.donor.collection_date), receipt_date: val(xf.donor.receipt_date),
      report_date: val(xf.donor.report_date),
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
    });
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
    });
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
    });
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
  });

  if (["transplant_donor", "rpl_couple"].includes(rtype) && manualDonorFields.length) {
    const df = manualDonorFields[0]; const dhf = manualDonorHlaFields[0];
    const donor = emptyPerson({
      name: val(df.name), gender_age: val(df.gender_age), relationship: val(df.relationship),
      pin: val(df.pin) || "NA", sample_number: val(df.sample_number) || "NA",
      collection_date: val(df.collection_date), receipt_date: val(df.receipt_date),
      report_date: val(df.report_date), match: val(df.match),
      hla: collectAlleles(dhf),
    });
    donors = [donor];
  }

  const c = { report_type: rtype, nabl, with_logo: state.withLogo, signature_stamp: stamp, patient, donors, rpl_reference: {} };

  if (rtype === "single_locus") {
    c.single_locus = {
      locus: manualSpecialFields.sl_0 ? manualSpecialFields.sl_0.value.trim() : "",
      allele1: manualSpecialFields.sl_1 ? manualSpecialFields.sl_1.value.trim() : "",
      allele2: manualSpecialFields.sl_2 ? manualSpecialFields.sl_2.value.trim() : "",
    };
  }
  if (rtype === "hla_c") {
    c.hla_c_result = {
      allele1: manualSpecialFields.hc_0 ? manualSpecialFields.hc_0.value.trim() : "",
      allele2: manualSpecialFields.hc_1 ? manualSpecialFields.hc_1.value.trim() : "",
      supertype: manualSpecialFields.hc_2 ? manualSpecialFields.hc_2.value.trim() : "",
    };
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

async function refreshManualPreview() {
  const statusEl = document.getElementById("manualPreviewStatus");
  const body = document.getElementById("manualPreviewBody");
  try {
    statusEl.textContent = "Rendering…";
    const c = collectManualCase();
    if (!c.patient || !c.patient.name) {
      body.innerHTML = '<div class="preview-placeholder">Fill in patient details to see a live preview.</div>';
      statusEl.textContent = "";
      return;
    }
    const resp = await apiPost("/hla/preview", { case: c });
    body.innerHTML = "";
    if (resp.preview_url) {
      body.appendChild(el("iframe", { src: resp.preview_url + "?t=" + Date.now(), style: "width:100%; height:100%; min-height:600px; border:none; flex:1;" }));
    } else {
      body.innerHTML = '<div class="preview-placeholder">No preview available.</div>';
    }
    statusEl.textContent = "";
  } catch (e) {
    statusEl.textContent = "Error";
    console.error(e);
  }
}

async function generateManual() {
  const c = collectManualCase();
  if (!c.patient || !c.patient.name) { showToast("Patient Name is required.", "error"); return; }
  const outputDir = val(document.getElementById("manualOutputInput"));
  try {
    const resp = await apiPost("/hla/generate", { case: c, output_dir: outputDir || undefined });
    showToast("Generated: " + resp.filename, "success");
    refreshManualPreview();
  } catch (e) {
    showToast("Error: " + e.message, "error");
  }
}

// ══════════════════════════════════════════════════════════════════════════
// DRAFTS
// ══════════════════════════════════════════════════════════════════════════
async function saveDraft(scope) {
  const name = prompt("Draft name:", scope === "manual" ? "manual_draft" : "bulk_draft");
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
    const name = prompt("Drafts available:\n" + list.drafts.join("\n") + "\n\nEnter draft name to load:");
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

// ══════════════════════════════════════════════════════════════════════════
// BULK TAB
// ══════════════════════════════════════════════════════════════════════════
function initBulkTab() {
  const dz = document.getElementById("bulkDropzone");
  const fi = document.getElementById("bulkFileInput");
  dz.addEventListener("click", () => fi.click());
  dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("dragover"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
  dz.addEventListener("drop", e => {
    e.preventDefault(); dz.classList.remove("dragover");
    if (e.dataTransfer.files.length) { fi.files = e.dataTransfer.files; updateDzLabel(); }
  });
  fi.addEventListener("change", updateDzLabel);

  function updateDzLabel() {
    if (fi.files.length) {
      document.getElementById("bulkDropzoneLabel").innerHTML =
        `<i class="fas fa-file-excel"></i> ${fi.files[0].name}`;
    }
  }

  document.getElementById("bulkParseBtn").addEventListener("click", parseBulkExcel);
  document.getElementById("bulkSearchBox").addEventListener("input", renderBulkList);
  document.getElementById("bulkSelectAllBtn").addEventListener("click", () => {
    state.bulkCases.forEach((_, i) => state.bulkSelected.add(i));
    renderBulkList();
  });
  document.getElementById("bulkDeselectAllBtn").addEventListener("click", () => {
    state.bulkSelected.clear();
    renderBulkList();
  });
  document.getElementById("bulkGenAllBtn").addEventListener("click", () => generateBulk(false));
  document.getElementById("bulkGenSelectedBtn").addEventListener("click", () => generateBulk(true));

  const sabKitSelect = document.getElementById("bulkSabKitSelect");
  SAB_KIT_NAMES.forEach(k => sabKitSelect.appendChild(el("option", { value: k }, k)));
  const sabFileInput = document.getElementById("bulkSabFileInput");
  document.getElementById("bulkSabImportBtn").addEventListener("click", () => sabFileInput.click());
  sabFileInput.addEventListener("change", () => importBulkSabExcel(sabFileInput, sabKitSelect));
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
    state.bulkCases.push(newCase);
    state.bulkSelected.add(state.bulkCases.length - 1);
    renderBulkList();
    selectBulkCase(state.bulkCases.length - 1);
    statusEl.textContent = "Imported: " + sabFileInput.files[0].name;
    showToast("SAB case added to bulk list.", "success");
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
  const listEl = document.getElementById("bulkCaseList");
  listEl.innerHTML = "";
  if (!state.bulkCases.length) {
    listEl.innerHTML = '<div class="preview-placeholder" style="padding:20px;">No cases loaded yet.</div>';
    return;
  }
  const q = (document.getElementById("bulkSearchBox").value || "").toLowerCase();
  state.bulkCases.forEach((c, i) => {
    const name = (c.patient && c.patient.name) || "Unnamed";
    if (q && !name.toLowerCase().includes(q)) return;
    const item = el("div", { class: "case-item" + (i === state.bulkCurrentIndex ? " selected" : ""), onclick: () => selectBulkCase(i) }, [
      el("input", { type: "checkbox", onclick: (e) => { e.stopPropagation(); toggleBulkSelect(i, e.target.checked); }, checked: state.bulkSelected.has(i) ? "checked" : null }),
      el("span", { class: "ci-name" }, name),
    ]);
    listEl.appendChild(item);
  });
}

function toggleBulkSelect(i, isChecked) {
  if (isChecked) state.bulkSelected.add(i); else state.bulkSelected.delete(i);
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

function renderBulkSabEditor(editCol, c) {
  const p = c.patient || {};

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
    input.addEventListener("input", () => { p[key] = input.value; });
    patGrid.appendChild(el("div", { class: "field" }, [el("label", {}, label), input]));
  });
  patCard.appendChild(patGrid);
  editCol.appendChild(patCard);

  const classCard = el("div", { class: "card" }, [el("h3", {}, "SAB Class &amp; % PRA")]);
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
  remarksInput.addEventListener("input", () => { p.remarks = remarksInput.value; });
  const commentsInput = el("textarea", {});
  commentsInput.value = p.comments || "";
  commentsInput.addEventListener("input", () => { p.comments = commentsInput.value; });
  remCard.appendChild(el("div", { class: "field-grid" }, [
    el("div", { class: "field full" }, [el("label", {}, "Remarks"), remarksInput]),
    el("div", { class: "field full" }, [el("label", {}, "Comments"), commentsInput]),
  ]));
  editCol.appendChild(remCard);

  const alleleCard = el("div", { class: "card" }, [el("h3", {}, "Allele Data (one per line: Allele,MFI)")]);
  const alleleTextarea = el("textarea", { style: "min-height:140px; font-family:'Courier New',monospace; font-size:11px;" });
  alleleTextarea.value = (c.sab_alleles || []).map(([a, m]) => `${a},${m}`).join("\n");
  alleleTextarea.addEventListener("input", () => {
    c.sab_alleles = parseSabAlleleTextLocal(alleleTextarea.value);
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

function renderBulkEditor(i) {
  const editCol = document.getElementById("bulkEditCol");
  editCol.innerHTML = "";
  const c = state.bulkCases[i];
  if (!c) return;

  if (c.report_type === "sab_class1" || c.report_type === "sab_class2") {
    renderBulkSabEditor(editCol, c);
    editCol.appendChild(el("div", { style: "display:flex; gap:8px; margin-top:8px;" }, [
      el("button", { class: "btn-sm btn-primary", onclick: () => previewBulkCase(i) }, [el("i", { class: "fas fa-sync" }), " Refresh Preview"]),
    ]));
    return;
  }

  const p = c.patient || {};

  const card = el("div", { class: "card" }, [el("h3", {}, "Patient Information")]);
  const grid = el("div", { class: "field-grid" });
  const fields = {};
  PAT_FIELDS.forEach(([key, label]) => {
    const pk = key === "patient_name" ? "name" : key;
    const input = el("input", { type: "text", value: p[pk] || "" });
    fields[pk] = input;
    input.addEventListener("input", () => { p[pk] = input.value; });
    grid.appendChild(el("div", { class: "field" + (key === "remarks" ? " full" : "") }, [el("label", {}, label), input]));
  });
  card.appendChild(grid);
  editCol.appendChild(card);

  if (p.hla) {
    const hlaCard = el("div", { class: "card" }, [el("h3", {}, "HLA Results")]);
    const hgrid = el("div", { class: "allele-grid" });
    HLA_LOCI.forEach(locus => {
      const pair = p.hla[locus] || ["", ""];
      const a1 = el("input", { type: "text", value: pair[0] || "" });
      const a2 = el("input", { type: "text", value: pair[1] || "" });
      a1.addEventListener("input", () => { p.hla[locus] = [a1.value, a2.value]; });
      a2.addEventListener("input", () => { p.hla[locus] = [a1.value, a2.value]; });
      hgrid.appendChild(el("div", { class: "allele-row" }, [el("span", { class: "locus-lbl" }, HLA_LOCUS_LABELS[locus] || locus), a1, a2]));
    });
    hlaCard.appendChild(hgrid);
    editCol.appendChild(hlaCard);
  }

  (c.donors || []).forEach((d, di) => {
    const dCard = el("div", { class: "card" }, [el("h3", {}, `Donor ${di + 1}: ${d.name || ""}`)]);
    const dgrid = el("div", { class: "field-grid" });
    ["name", "gender_age", "relationship", "pin", "sample_number", "match"].forEach(key => {
      const input = el("input", { type: "text", value: d[key] || "" });
      input.addEventListener("input", () => { d[key] = input.value; });
      dgrid.appendChild(el("div", { class: "field" }, [el("label", {}, key.replace("_", " ")), input]));
    });
    dCard.appendChild(dgrid);
    if (d.hla) {
      const dhgrid = el("div", { class: "allele-grid" });
      HLA_LOCI.forEach(locus => {
        const pair = d.hla[locus] || ["", ""];
        const a1 = el("input", { type: "text", value: pair[0] || "" });
        const a2 = el("input", { type: "text", value: pair[1] || "" });
        a1.addEventListener("input", () => { d.hla[locus] = [a1.value, a2.value]; });
        a2.addEventListener("input", () => { d.hla[locus] = [a1.value, a2.value]; });
        dhgrid.appendChild(el("div", { class: "allele-row" }, [el("span", { class: "locus-lbl" }, HLA_LOCUS_LABELS[locus] || locus), a1, a2]));
      });
      dCard.appendChild(dhgrid);
    }
    editCol.appendChild(dCard);
  });

  const btnRow = el("div", { style: "display:flex; gap:8px; margin-top:8px;" }, [
    el("button", { class: "btn-sm btn-primary", onclick: () => previewBulkCase(i) }, [el("i", { class: "fas fa-sync" }), " Refresh Preview"]),
  ]);
  editCol.appendChild(btnRow);
}

async function previewBulkCase(i) {
  const c = state.bulkCases[i];
  if (!c) return;
  const body = document.getElementById("bulkPreviewBody");
  body.innerHTML = '<div class="preview-placeholder">Rendering…</div>';
  try {
    const resp = await apiPost("/hla/preview", { case: c });
    body.innerHTML = "";
    if (resp.preview_url) {
      body.appendChild(el("iframe", { src: resp.preview_url + "?t=" + Date.now(), style: "width:100%; height:100%; min-height:500px; border:none; flex:1;" }));
    } else {
      body.innerHTML = '<div class="preview-placeholder">No preview available.</div>';
    }
  } catch (e) {
    body.innerHTML = '<div class="preview-placeholder">Preview error.</div>';
  }
}

async function generateBulk(selectedOnly) {
  const indices = selectedOnly ? Array.from(state.bulkSelected) : state.bulkCases.map((_, i) => i);
  if (!indices.length) { showToast("No cases to generate.", "error"); return; }
  const cases = indices.map(i => state.bulkCases[i]);
  const outputDir = val(document.getElementById("bulkOutputInput"));
  const withLogo = checked(document.getElementById("bulkLogoChk"));
  const stamp = checked(document.getElementById("globalStampChk"));

  const progWrap = document.getElementById("bulkProgressWrap");
  const progBar = document.getElementById("bulkProgressBar");
  progWrap.classList.remove("hidden");
  progBar.style.width = "10%";

  try {
    const resp = await apiPost("/hla/generate-bulk", { cases, output_dir: outputDir || undefined, with_logo: withLogo, signature_stamp: stamp });
    progBar.style.width = "100%";
    showToast(`Generated ${resp.success.length} report(s), ${resp.failed.length} failed.`, resp.failed.length ? "error" : "success");
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
});
