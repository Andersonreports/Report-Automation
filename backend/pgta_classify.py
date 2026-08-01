
import re

EUPLOID        = "EUPLOID"
ANEUPLOID      = "ANEUPLOID"
SEGMENTAL      = "SEGMENTAL"
LOW_MOSAIC     = "LOW_MOSAIC"
HIGH_MOSAIC    = "HIGH_MOSAIC"
COMPLEX_MOSAIC = "COMPLEX_MOSAIC"
FAILED         = "FAILED"
INCONCLUSIVE   = "INCONCLUSIVE"
LOW_DNA        = "LOW_DNA"

SUMMARY_TEXT = {
    EUPLOID:        "Normal chromosome complement",
    ANEUPLOID:      "Abnormal chromosome complement",
    SEGMENTAL:      "Multiple chromosomal abnormalities",
    LOW_MOSAIC:     "Mosaic chromosome complement",
    HIGH_MOSAIC:    "Mosaic chromosome complement",
    COMPLEX_MOSAIC: "Mosaic chromosome complement",
    FAILED:         "No result obtained",
    INCONCLUSIVE:   "Inconclusive",
    LOW_DNA:        "Low DNA concentration",
}

RESULT_TEXT = {
    EUPLOID:        "The embryo contains normal chromosome complement",
    ANEUPLOID:      "The embryo contains abnormal chromosome complement",
    SEGMENTAL:      "The embryo contains multiple chromosomal abnormalities",
    LOW_MOSAIC:     "The embryo contains mosaic chromosome complement",
    HIGH_MOSAIC:    "The embryo contains mosaic chromosome complement",
    COMPLEX_MOSAIC: "The embryo contains mosaic chromosome complement",
    FAILED:         "No result obtained",
    INCONCLUSIVE:   "Inconclusive",
    LOW_DNA:        "Low DNA concentration",
}

_KEYWORD_MAP = {
    "EUPLOID":                     EUPLOID,
    "NORMAL":                      EUPLOID,
    "NORMAL CHROMOSOME COMPLEMENT":EUPLOID,
    "ANEUPLOID":                   ANEUPLOID,
    "MULTIPLE CHROMOSOMAL ABNORMALITIES": SEGMENTAL,
    "SEGMENTAL":                   SEGMENTAL,
    "LOW LEVEL MOSAIC":            LOW_MOSAIC,
    "LOW MOSAIC":                  LOW_MOSAIC,
    "HIGH LEVEL MOSAIC":           HIGH_MOSAIC,
    "HIGH MOSAIC":                 HIGH_MOSAIC,
    "COMPLEX MOSAIC":              COMPLEX_MOSAIC,
    "FAILED":                      FAILED,
    "NO RESULT":                   FAILED,
    "NO RESULT OBTAINED":          FAILED,
    "INCONCLUSIVE":                INCONCLUSIVE,
    "LOW DNA CONCENTRATION":       LOW_DNA,
    "LOW DNA":                     LOW_DNA,
    "NO DNA":                      LOW_DNA,
}


def _extract_pct(text):
    m = re.search(r'~?\s*(\d+(?:\.\d+)?)\s*%', text)
    return float(m.group(1)) if m else None


def classify_embryo(raw_result):
    if not raw_result:
        return _make(EUPLOID)

    s = str(raw_result).strip()
    su = s.upper()

    if su in _KEYWORD_MAP:
        return _make(_KEYWORD_MAP[su])

    if "INCONCLUSIVE" in su:
        return _make(INCONCLUSIVE)

    if "LOW DNA" in su or "NO DNA" in su:
        return _make(LOW_DNA)

    if any(k in su for k in ("FAILED", "NO RESULT")):
        return _make(FAILED)

    pcts = [_extract_pct(t) for t in re.findall(r'[~\d.%]+', s) if _extract_pct(t) is not None]
    has_mosaic_kw = bool(re.search(r'\bmosaic\b', s, re.IGNORECASE))

    if has_mosaic_kw or pcts:
        pct = max(pcts) if pcts else None

        mosaic_chr_nums = set(re.findall(
            r'(?:mosaic\s+)?(?:[+-]\s*)(1[0-9]|2[0-2]|[1-9])\b',
            s, re.IGNORECASE
        ))
        mosaic_chr_nums |= set(re.findall(
            r'\bmosaic\s+(?:del|dup)\s*\(\s*(1[0-9]|2[0-2]|[1-9])',
            s, re.IGNORECASE
        ))
        if not mosaic_chr_nums:
            mosaic_chr_nums = {str(i) for i in range(len(re.split(r'[,;]', s)))}

        n_mosaic_chrs = max(1, len(mosaic_chr_nums))

        if n_mosaic_chrs >= 3:
            return _make(COMPLEX_MOSAIC)

        if pct is not None:
            if pct < 30:
                return _make(EUPLOID)
            if pct > 80:
                return _make(ANEUPLOID)
            if 30 <= pct <= 50:
                return _make(LOW_MOSAIC)
            if 51 <= pct <= 80:
                return _make(HIGH_MOSAIC)

        return _make(LOW_MOSAIC)

    if re.search(r'\b(del|dup)\s*\(|segmental\s+(loss|gain)\b', s, re.IGNORECASE):
        return _make(SEGMENTAL)

    if re.search(
        r'([+-]\s*(?:1[0-9]|2[0-2]|[1-9])\b'
        r'|monosomy|trisomy|nullisomy|tetrasomy'
        r'|\baneuploid\b|\babnormal\b'
        r'|\bloss\b|\bgain\b)',
        s, re.IGNORECASE
    ):
        return _make(ANEUPLOID)

    return _make(EUPLOID)


def is_ambiguous_or_normal_interp(interp_text):
    s = (interp_text or "").strip().upper()
    if s in ("", "NA", "N/A"):
        return True
    return bool(re.search(r'\bNORMAL\b', s) or re.search(r'\bEUPLOID\b', s))


def _make(cls):
    return {
        "classification": cls,
        "summary_text":   SUMMARY_TEXT[cls],
        "result_text":    RESULT_TEXT[cls],
        "is_abnormal":    cls in (ANEUPLOID, SEGMENTAL, LOW_MOSAIC, HIGH_MOSAIC, COMPLEX_MOSAIC),
        "is_mosaic":      cls in (LOW_MOSAIC, HIGH_MOSAIC, COMPLEX_MOSAIC),
    }



def _split_findings(s):
    """
    Split a Result string into one token per finding, on commas/semicolons/"and"
    that are OUTSIDE parentheses. A plain re.split on "," tore
    "dup(9)(p22.33p21.1)(~30.50Mb,~32%)" in half, which separated the mosaic
    percentage from its dup() and silently downgraded SMG to SG.
    """
    parts, depth, cur = [], 0, ''
    for ch in str(s or ''):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        if ch in ',;' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    parts.append(cur)

    tokens = []
    for p in parts:
        tokens.extend(re.split(r'\band\b', p, flags=re.IGNORECASE))
    return tokens


def derive_chromosome_statuses(raw_result):
    statuses = {str(i): 'N' for i in range(1, 23)}

    if not raw_result:
        return statuses

    s = str(raw_result).strip()
    su = s.upper()

    if any(k in su for k in ("FAILED", "NO RESULT")):
        return {str(i): 'NR' for i in range(1, 23)}

    if su in ("EUPLOID", "NORMAL", "NORMAL CHROMOSOME COMPLEMENT"):
        return statuses

    for token in _split_findings(s):
        tok = token.strip()
        # A percentage marks the finding as mosaic just as the word does:
        # "+15(~30%)" is MG, "dup(9)(p22.33p21.1)(~30.50Mb,~32%)" is SMG. Only
        # a "~NN%" fraction counts -- "(~69.35Mb)" is a size, not a level.
        is_mos = bool(re.search(r'\bmosaic\b', tok, re.IGNORECASE)) or \
            bool(re.search(r'~?\s*\d+(?:\.\d+)?\s*%', tok))
        is_seg = bool(re.search(r'\bsegmental\b', tok, re.IGNORECASE))

        for m in re.finditer(r'([+-])\s*(1[0-9]|2[0-2]|[1-9])\b', tok):
            sign, num = m.group(1), m.group(2)
            if is_mos and is_seg:
                statuses[num] = 'SMG' if sign == '+' else 'SML'
            elif is_mos:
                statuses[num] = 'MG' if sign == '+' else 'ML'
            elif is_seg:
                statuses[num] = 'SG' if sign == '+' else 'SL'
            else:
                statuses[num] = 'G' if sign == '+' else 'L'

        for m in re.finditer(r'\b(del|dup)\s*\(\s*(1[0-9]|2[0-2]|[1-9])\s*[pq]?', tok, re.IGNORECASE):
            op, num = m.group(1).lower(), m.group(2)
            statuses[num] = ('SMG' if op == 'dup' else 'SML') if is_mos else ('SG' if op == 'dup' else 'SL')

        for m in re.finditer(r'\b(monosomy|nullisomy)\s+(1[0-9]|2[0-2]|[1-9])\b', tok, re.IGNORECASE):
            statuses[m.group(2)] = 'ML' if is_mos else 'L'
        for m in re.finditer(r'\b(trisomy|tetrasomy)\s+(1[0-9]|2[0-2]|[1-9])\b', tok, re.IGNORECASE):
            statuses[m.group(2)] = 'MG' if is_mos else 'G'

        for m in re.finditer(r'\bloss\s+(?:chr)?\s*(1[0-9]|2[0-2]|[1-9])\b', tok, re.IGNORECASE):
            num = m.group(1)
            statuses[num] = ('SML' if is_seg else 'ML') if is_mos else ('SL' if is_seg else 'L')
        for m in re.finditer(r'\bgain\s+(?:chr)?\s*(1[0-9]|2[0-2]|[1-9])\b', tok, re.IGNORECASE):
            num = m.group(1)
            statuses[num] = ('SMG' if is_seg else 'MG') if is_mos else ('SG' if is_seg else 'G')

    return statuses


def validate_statuses(statuses, raw_result):
    if not raw_result:
        return statuses
    derived = derive_chromosome_statuses(raw_result)
    for num, st in derived.items():
        if st != 'N' and statuses.get(num, 'N') == 'N':
            statuses[num] = st
    return statuses



def derive_autosomes(raw_result, chromosome_statuses, existing_autosomes=""):
    cls = classify_embryo(raw_result)["classification"]

    existing = (existing_autosomes or "").strip()
    # Only the frontend's own untouched-placeholder text -- "Normal", the
    # default it fills into every new/blank Autosomes field (pgta.html) -- is
    # treated as "nothing supplied yet" and eligible for auto-derivation from
    # the Result text. Everything else the user actually typed is honored
    # VERBATIM, exactly as Result Summary/Description already are.
    #
    # This used to be a substring word-list (euploid|aneuploid|mosaic|normal|
    # "multiple chromosomal"|...), which matched INSIDE genuine typed text and
    # silently discarded it: typing "Multiple Chromosomal Abnormalities" --
    # some labs' own AUTOSOMES column reads exactly that when there are too
    # many findings to list -- matched "multiple chromosomal" and was thrown
    # away, falling back to "Normal" whenever the Result text held no
    # explicit per-chromosome codes to re-derive from instead.
    has_custom_existing = existing.upper() not in ("", "NORMAL", "-", "NA", "N/A")
    if has_custom_existing:
        cleaned_existing = re.sub(r'\b(XX|XY)\b', '', existing, flags=re.IGNORECASE).strip(', ')
        has_custom_existing = bool(cleaned_existing)

    if cls == EUPLOID:
        return cleaned_existing if has_custom_existing else "Normal"
    if cls == FAILED:
        return cleaned_existing if has_custom_existing else "No result"
    if cls == INCONCLUSIVE:
        return cleaned_existing if has_custom_existing else "Inconclusive"
    if cls == LOW_DNA:
        return cleaned_existing if has_custom_existing else "Low DNA concentration"

    if has_custom_existing:
        return cleaned_existing

    parts = []
    for i in range(1, 23):
        st = chromosome_statuses.get(str(i), 'N')
        if st == 'N':
            continue
        pct = _find_pct(raw_result, i)
        arm = ''
        if st == 'L':
            parts.append(f"-{i}")
        elif st == 'G':
            parts.append(f"+{i}")
        elif st == 'SL':
            arm = _find_arm(raw_result, i, 'del')
            parts.append(f"del({i}{arm})" if arm else f"del({i})")
        elif st == 'SG':
            arm = _find_arm(raw_result, i, 'dup')
            parts.append(f"dup({i}{arm})" if arm else f"dup({i})")
        elif st == 'ML':
            parts.append(f"Mosaic -{i}" + (f"(~{pct}%)" if pct else ""))
        elif st == 'MG':
            parts.append(f"Mosaic +{i}" + (f"(~{pct}%)" if pct else ""))
        elif st == 'SML':
            arm = _find_arm(raw_result, i, 'del')
            parts.append(f"Mosaic del({i}{arm})" + (f"(~{pct}%)" if pct else ""))
        elif st == 'SMG':
            arm = _find_arm(raw_result, i, 'dup')
            parts.append(f"Mosaic dup({i}{arm})" + (f"(~{pct}%)" if pct else ""))
        elif st == 'NR':
            parts.append(f"Chr{i}: No result")

    return ", ".join(parts) if parts else "Normal"


def sex_chromosomes_color_role(sex_text):
    """
    'black' | 'red' | 'blue' for the Sex Chromosomes value:
      - blank / Normal / No result / NA / N/A -> black (NA is not itself an
        abnormal finding, same treatment as Autosomes/Interpretation)
      - Mosaic ... -> blue
      - anything else (an actual abnormal finding) -> red
    Shared by the PDF template, the DOCX generator, and the editor's JS
    getSexChrColor() so the three cannot drift.
    """
    s = str(sex_text or '').upper().strip()
    if 'MOSAIC' in s:
        return 'blue'
    if not s or s in ('NA', 'N/A', 'NORMAL', 'NO RESULT'):
        return 'black'
    return 'red'


def sanitize_sex_chromosomes(sex_text, raw_result="", classification=None):
    s = str(sex_text or "").strip()
    su = s.upper()

    s_clean = re.sub(r'\b(XX|XY)\b', '', s, flags=re.IGNORECASE).strip(', ')

    if s_clean and s_clean.upper() not in ('NORMAL', ''):
        return s_clean

    cls = (classification or classify_embryo(raw_result or "")["classification"])

    if cls in (EUPLOID, FAILED):
        return s_clean if s_clean else ("Normal" if cls == EUPLOID else "No result")

    r = str(raw_result or "")
    has_mosaic = bool(re.search(r'\bmosaic\b', r, re.IGNORECASE))

    if re.search(r'[-]\s*X\b|\bmonosomy\s+x\b', r, re.IGNORECASE):
        return "Mosaic -X" if has_mosaic else "-X"
    if re.search(r'[+]\s*X\b|\btrisomy\s+x\b', r, re.IGNORECASE):
        return "Mosaic +X" if has_mosaic else "+X"
    if re.search(r'[-]\s*Y\b|\bmonosomy\s+y\b', r, re.IGNORECASE):
        return "Mosaic -Y" if has_mosaic else "-Y"
    if re.search(r'[+]\s*Y\b|\btrisomy\s+y\b', r, re.IGNORECASE):
        return "Mosaic +Y" if has_mosaic else "+Y"

    return s_clean if s_clean else "Normal"


# --- Autosomes text colour -------------------------------------------------
# Anything that is not an actual finding is ALWAYS black. "Normal" is not an
# abnormality to flag, so it stays black whatever the Result line or the
# Interpretation says -- which is what used to go wrong: the interpretation
# override ran last and unconditionally, painting a "Normal" Autosomes value
# blue on every mosaic embryo. \b keeps "Abnormal" out of this set.
_AUTO_PLAIN_RE   = re.compile(r'\b(NORMAL|EUPLOID|NO RESULT|INCONCLUSIVE|LOW DNA|NO DNA)\b')
_AUTO_FINDING_RE = re.compile(r'(?:DEL|DUP)\s*\(|[+-]\s*\d')


def autosomes_is_plain(autosomes_text):
    """True when the Autosomes value carries no finding, so it must render black."""
    t = str(autosomes_text or '').strip().upper()
    if t in ('', '-', 'NA', 'N/A'):
        return True
    if _AUTO_FINDING_RE.search(t):
        return False
    return bool(_AUTO_PLAIN_RE.search(t))


def autosomes_color_role(autosomes_text, interp_text='', result_text=''):
    """
    'black' | 'red' | 'blue' for the Autosomes value, per PGTA conditions:
      - no finding (Normal / blank / No result / Inconclusive / Low DNA) -> black
      - Multiple chromosomal abnormalities                               -> red
      - Interpretation Aneuploid / Chaotic embryo / (-)                  -> red
      - Interpretation Low level / High level / Complex mosaic           -> blue
      - Interpretation Inconclusive                                      -> black
      - no interpretation to go by: a mosaic percentage -> blue, else red
    Shared by the PDF template and the DOCX generator so the two cannot drift.
    """
    if autosomes_is_plain(autosomes_text):
        return 'black'
    t = str(autosomes_text or '').upper()
    i = str(interp_text or '').upper().strip()
    if 'MULTIPLE CHROMOSOMAL ABNORMALITIES' in t or \
       'MULTIPLE CHROMOSOMAL ABNORMALITIES' in str(result_text or '').upper():
        return 'red'
    if 'ANEUPLOID' in i or 'CHAOTIC' in i or i == '(-)':
        return 'red'
    if 'MOSAIC' in i:
        return 'blue'
    if 'INCONCLUSIVE' in i:
        return 'black'
    return 'blue' if '%' in t else 'red'


def _find_arm(raw, chr_num, op):
    m = re.search(rf'\b{op}\s*\(\s*{chr_num}\s*([pq])', raw, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def _find_pct(raw, chr_num):
    m = re.search(
        rf'(?:[+-]\s*{chr_num}|monosomy\s+{chr_num}|trisomy\s+{chr_num}|chr\s*{chr_num})'
        rf'\s*\(?\s*~?\s*(\d+(?:\.\d+)?)\s*%',
        raw, re.IGNORECASE
    )
    if m:
        return int(float(m.group(1)))
    m = re.search(r'~?\s*(\d+(?:\.\d+)?)\s*%', raw)
    return int(float(m.group(1))) if m else None


def any_mosaic(embryos_data):
    for emb in (embryos_data or []):
        raw = (emb.get('result_summary') or emb.get('result_description') or '')
        if classify_embryo(raw)["is_mosaic"]:
            return True
    return False


def auto_map_cnvs(embryos, image_filenames):
    if not embryos or not image_filenames:
        return 0
        
    mapped_count = 0
    available_imgs = {f.lower(): f for f in image_filenames}
    unmapped_embryos = list(embryos)
    
    def alpha_norm(s):
        return re.sub(r'[^a-z0-9]', '', str(s).lower())

    def extract_num(s):
        m = re.search(r'\d+', str(s))
        return int(m.group()) if m else None

    for emb in list(unmapped_embryos):
        eid = str(emb.get("embryo_id") or "").strip().lower()
        if not eid: continue
        
        matched_filename = None
        for low_name, orig_name in available_imgs.items():
            name_no_ext = os.path.splitext(low_name)[0]
            if name_no_ext == eid:
                matched_filename = orig_name
                break
        
        if matched_filename:
            emb["cnv_image_name"] = matched_filename
            available_imgs.pop(matched_filename.lower(), None)
            unmapped_embryos.remove(emb)
            mapped_count += 1

    for emb in list(unmapped_embryos):
        eid = str(emb.get("embryo_id") or "").strip().lower()
        if not eid: continue
        
        matched_filename = None
        eid_esc = re.escape(eid)
        for low_name, orig_name in available_imgs.items():
            if re.search(rf"(^|[^a-z0-9]){eid_esc}([^a-z0-9]|$)", low_name):
                matched_filename = orig_name
                break
        
        if matched_filename:
            emb["cnv_image_name"] = matched_filename
            available_imgs.pop(matched_filename.lower(), None)
            unmapped_embryos.remove(emb)
            mapped_count += 1
            
    for emb in list(unmapped_embryos):
        eid = str(emb.get("embryo_id") or "").strip().lower()
        if not eid: continue
        
        target_norm = alpha_norm(eid)
        target_num = extract_num(eid)
        matched_filename = None
        
        for low_name, orig_name in available_imgs.items():
            if target_norm in alpha_norm(low_name):
                if target_num is not None:
                    file_num = extract_num(low_name)
                    if file_num is not None and file_num != target_num:
                        continue
                matched_filename = orig_name
                break
        
        if matched_filename:
            emb["cnv_image_name"] = matched_filename
            available_imgs.pop(matched_filename.lower(), None)
            unmapped_embryos.remove(emb)
            mapped_count += 1

    if unmapped_embryos and len(unmapped_embryos) == len(available_imgs):
        def sort_key_num(s):
            m = re.search(r'\d+', str(s))
            return int(m.group()) if m else 999
            
        unmapped_sorted = sorted(unmapped_embryos, key=lambda e: sort_key_num(e.get("embryo_id", "")))
        imgs_sorted = sorted(available_imgs.values(), key=lambda f: sort_key_num(f))
        
        for i, emb in enumerate(unmapped_sorted):
            emb["cnv_image_name"] = imgs_sorted[i]
            mapped_count += 1
            
    return mapped_count
