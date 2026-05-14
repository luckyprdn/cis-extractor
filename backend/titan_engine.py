import fitz
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

RE_RULE_EXACT   = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)', re.IGNORECASE)
RE_RULE_FUZZY   = re.compile(r'([lI1\d][\s\.\d]*\d)\s+(Ensure|Do\s+not|Review|Keep|Use)\s+', re.IGNORECASE)
RE_RULE_HEADING = re.compile(r'^(\d+(?:\.\d+)+)\b')

RE_SECTION = re.compile(
    r'^(Profile\s+Applicability|Level\s*[123]|Description|Rationale(?:\s+Statement)?'
    r'|Impact(?:\s+Statement)?|Audit(?:\s+Procedure)?'
    r'|Remediation(?:\s+Procedure)?|Default\s+Value|References):?\s*', re.IGNORECASE)

RE_TOC_PAGE_ONLY = re.compile(r'^(\d+(?:\.\d+)+).*?(?:\.+)\s*(\d+)\s*$')
RE_NOISE = re.compile(r'(Page\s+\d+|Internal\s+Only[^\n]*|P\s+a\s+g\s+e\s*\|\s*\d+)', re.IGNORECASE)
RE_LEVEL = re.compile(r'Level\s*(\d+)', re.IGNORECASE)

RE_APPENDIX_START = re.compile(r'^(?:Appendix:\s*)?(?:Summary\s+Table|Recommendation\s+Summary|CIS\s+Controls\s+v\d+\s+IG\s+\d+\s+Mapped\s+Recommendations)', re.IGNORECASE)
RE_APPENDIX_STOP  = re.compile(r'^(?:Appendix:\s*)?Change History', re.IGNORECASE)

SECTION_MAP = {
    "profile applicability": "Level", "level 1": "Level", "level 2": "Level", "level 3": "Level",
    "description": "Description", "rationale": "Rationale", "rationale statement": "Rationale", 
    "impact": "Impact", "impact statement": "Impact", "audit": "Audit", "audit procedure": "Audit", 
    "remediation": "Remediation", "remediation procedure": "Remediation", 
    "default value": "Default Value", "references": "References",
}

@dataclass
class ParseResult:
    rule_id: str; title: str = ""; level: str = ""; description: str = ""; rationale: str = ""
    impact: str = ""; audit: str = ""; remediation: str = ""; default_value: str = ""; references: str = ""
    found_on_page: int = -1; recovery_method: str = "exact"; confidence: float = 1.0

def clean_text(parts: List[str]) -> str:
    return " ".join(RE_NOISE.sub("", " ".join(parts)).split()).strip() or "N/A"

def extract_level(parts: List[str]) -> str:
    joined = " ".join(parts)
    m = RE_LEVEL.search(joined)
    return f"Level {m.group(1)}" if m else (joined.strip() or "N/A")

def sort_key(rule_id: str) -> list:
    try: return [int(p) for p in rule_id.split(".")]
    except ValueError: return [0]

def build_ground_truth(page_cache: List[str]) -> Dict[str, int]:
    toc_pages = {}; master_ids = []
    total_pages = len(page_cache)
    
    for page_idx in range(min(100, total_pages)):
        for line in page_cache[page_idx].split("\n"):
            m = RE_TOC_PAGE_ONLY.match(line.strip())
            if m and "." in m.group(1):
                try: toc_pages[m.group(1)] = int(m.group(2))
                except ValueError: pass

    in_appendix = False; appendix_done = False
    for page_idx in range(total_pages):
        if appendix_done: break
        for line in page_cache[page_idx].split("\n"):
            clean_line = line.strip()
            if not clean_line: continue
            if RE_APPENDIX_START.search(clean_line): in_appendix = True; continue
            if in_appendix and RE_APPENDIX_STOP.search(clean_line):
                in_appendix = False; appendix_done = True; break
            
            if in_appendix:
                if re.match(r'^(\d+(?:\.\d+)+)$', clean_line): master_ids.append(clean_line)
                else:
                    m = re.match(r'^(\d+(?:\.\d+)+)\s+(.+)', clean_line)
                    if m: master_ids.append(m.group(1))

    master_ids = list(dict.fromkeys(master_ids))
    if not master_ids: master_ids = sorted(list(toc_pages.keys()), key=sort_key)
    return {rid: toc_pages.get(rid, 0) for rid in master_ids}

def parse_rules_from_text(text: str, target_ids: Set[str], mode: str = "exact") -> Dict[str, dict]:
    rules = {}; current_id = None
    content = {"Title": [], "Level": [], "Description": [], "Rationale": [], "Impact": [], "Audit": [], "Remediation": [], "Default Value": [], "References": []}
    current_section = "Title"

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped: continue

        m = None
        if mode == "exact": m = RE_RULE_EXACT.match(stripped)
        elif mode == "fuzzy":
            norm = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', stripped)
            norm = re.sub(r'^[lIi]\.', '1.', norm)
            m = RE_RULE_EXACT.match(norm)
        elif mode == "heading": m = RE_RULE_HEADING.match(stripped)

        if m and ("." in m.group(1) or mode != "heading"):
            rid = m.group(1)
            title = m.group(2).strip() if len(m.groups()) > 1 else stripped[m.end():].strip()
            
            if not target_ids or rid in target_ids:
                if current_id: rules[current_id] = content
                current_id = rid
                content = {"Title": [title], "Level": [], "Description": [], "Rationale": [], "Impact": [], "Audit": [], "Remediation": [], "Default Value": [], "References": []}
                current_section = "Title"
                continue

        if not current_id: continue

        if current_section == "Title":
            m_inline = re.search(r'(.*?)\s*(Profile\s+Applicability|Level\s*[123])\s*:?\s*(.*)', stripped, re.IGNORECASE)
            if m_inline and re.search(r'\((?:Automated|Manual)\)$', m_inline.group(1).strip(), re.IGNORECASE):
                content["Title"].append(m_inline.group(1).strip())
                current_section = "Level"
                content[current_section].append((m_inline.group(2) + " " + m_inline.group(3)).strip())
                continue

        s_match = RE_SECTION.match(stripped)
        if s_match:
            raw_key = s_match.group(1).lower()
            for k, v in SECTION_MAP.items():
                if raw_key.startswith(k): current_section = v; break
            remainder = RE_SECTION.sub("", stripped).strip()
            if remainder: content[current_section].append(remainder)
        else:
            content[current_section].append(stripped)

    if current_id: rules[current_id] = content
    return rules

def qc_sweep(page_cache: List[str], found: Dict[str, ParseResult]) -> Tuple[Dict[str, ParseResult], List[str]]:
    sorted_ids = sorted(found.keys(), key=sort_key)
    jumps = []
    for i in range(len(sorted_ids) - 1):
        c, n = sorted_ids[i].split('.'), sorted_ids[i+1].split('.')
        if len(c) == len(n) and c[:-1] == n[:-1] and int(n[-1]) > int(c[-1]) + 1:
            for missing in range(int(c[-1]) + 1, int(n[-1])): jumps.append('.'.join(c[:-1] + [str(missing)]))

    verified_skipped = []; rescued_by_qc = {}

    if jumps:
        for gap_id in jumps:
            temp_list = sorted(list(found.keys()) + [gap_id], key=sort_key)
            idx = temp_list.index(gap_id)
            start_pg = found[temp_list[idx-1]].found_on_page if idx > 0 else 0
            end_pg = found[temp_list[idx+1]].found_on_page if idx < len(temp_list)-1 else len(page_cache)-1
            
            is_in_pdf = False
            for pg in range(max(0, start_pg - 2), min(len(page_cache), end_pg + 2)):
                if re.search(rf'^{gap_id}\s+[A-Z]', page_cache[pg], re.MULTILINE):
                    raw = parse_rules_from_text(page_cache[pg], {gap_id}, mode="exact")
                    if gap_id in raw:
                        r = raw[gap_id]
                        rescued_by_qc[gap_id] = ParseResult(
                            gap_id, clean_text(r["Title"]), extract_level(r["Level"]), clean_text(r["Description"]),
                            clean_text(r["Rationale"]), clean_text(r["Impact"]), clean_text(r["Audit"]),
                            clean_text(r["Remediation"]), clean_text(r["Default Value"]), clean_text(r["References"]),
                            pg+1, "qc_rescue", 0.95
                        )
                        is_in_pdf = True
                        break
            if not is_in_pdf: verified_skipped.append(gap_id)

    found.update(rescued_by_qc)
    return found, verified_skipped

def cleanse_rule_bleeding(found_rules_dict: Dict[str, ParseResult]) -> Dict[str, ParseResult]:
    all_ids = sorted(found_rules_dict.keys(), key=sort_key)
    fields_to_check = ['references', 'default_value', 'remediation', 'audit', 'impact', 'rationale', 'description', 'level', 'title']
    
    for i in range(len(all_ids) - 1):
        curr_rule = found_rules_dict[all_ids[i]]
        next_id = all_ids[i+1]
        bleed_pattern = re.compile(rf'(?:\s|^){re.escape(next_id)}\s+(?:Ensure|Do\s+not|Review|Keep|Use|Configure|Turn\s+off|Disable|Enable|Allow|Deny|Restrict|Set|Require|Prevent|Limit|Block|Force|Audit)\b', re.IGNORECASE)
        
        for field in fields_to_check:
            val = getattr(curr_rule, field)
            if val and next_id in val:
                m = bleed_pattern.search(val)
                if m:
                    setattr(curr_rule, field, val[:m.start()].strip() or "N/A")
                    break 
    return found_rules_dict

def extract_cis_data(pdf_path_or_bytes) -> dict:
    doc = fitz.open(stream=pdf_path_or_bytes, filetype="pdf") if isinstance(pdf_path_or_bytes, bytes) else fitz.open(pdf_path_or_bytes)
    PAGE_CACHE = [RE_NOISE.sub("", doc[i].get_text("text")) for i in range(len(doc))]
    toc = build_ground_truth(PAGE_CACHE)

    raw = parse_rules_from_text("\n".join(PAGE_CACHE), set(toc.keys()))
    found = {rid: ParseResult(
        rid, clean_text(d["Title"]), extract_level(d["Level"]), clean_text(d["Description"]),
        clean_text(d["Rationale"]), clean_text(d["Impact"]), clean_text(d["Audit"]),
        clean_text(d["Remediation"]), clean_text(d["Default Value"]), clean_text(d["References"]),
        toc.get(rid, -1), "exact"
    ) for rid, d in raw.items()}

    gaps = [rid for rid in toc if rid not in found]
    all_ids = sorted(toc.keys(), key=sort_key)
    for gap_id in gaps:
        try: idx = all_ids.index(gap_id)
        except ValueError: continue
        start_pg = toc.get(all_ids[max(0, idx-1)], 1) - 2
        end_pg = toc.get(all_ids[min(len(all_ids)-1, idx+1)], len(PAGE_CACHE)) + 2
        
        for mode in ["fuzzy", "heading"]:
            for pg in range(max(0, start_pg), min(len(PAGE_CACHE), end_pg)):
                raw = parse_rules_from_text(PAGE_CACHE[pg], {gap_id}, mode=mode)
                if gap_id in raw:
                    r = raw[gap_id]
                    found[gap_id] = ParseResult(
                        gap_id, clean_text(r["Title"]), extract_level(r["Level"]), clean_text(r["Description"]),
                        clean_text(r["Rationale"]), clean_text(r["Impact"]), clean_text(r["Audit"]),
                        clean_text(r["Remediation"]), clean_text(r["Default Value"]), clean_text(r["References"]),
                        pg + 1, mode, 0.8
                    )
                    break

    found, verified_skipped = qc_sweep(PAGE_CACHE, found)
    found = cleanse_rule_bleeding(found)
    final_found = {k: v for k, v in found.items() if (v.audit != "N/A" or v.remediation != "N/A" or v.description != "N/A")}
    doc.close()

    records = [vars(final_found[rid]) for rid in sorted(final_found.keys(), key=sort_key)]
    return {
        "data": records, 
        "report": {
            "status": "SUCCESS", "total_toc": len(toc), "total_extracted": len(final_found),
            "verified_skipped_by_cis": verified_skipped,
            "missing_but_in_toc": [rid for rid in toc if rid not in final_found and rid not in verified_skipped]
        }
    }
