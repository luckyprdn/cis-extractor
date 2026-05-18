import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import time
import io
import json
import gc
import plotly.express as px
import plotly.graph_objects as go
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime

# =============================================================================
# 1. CORE CONFIGURATION & SESSION STATE
# =============================================================================
st.set_page_config(
    page_title="Titan CIS Benchmark Extractor",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "theme" not in st.session_state: st.session_state.theme = "Dark"
if "animations" not in st.session_state: st.session_state.animations = True
if "compact_mode" not in st.session_state: st.session_state.compact_mode = False
if "perf_mode" not in st.session_state: st.session_state.perf_mode = "Balanced"
if "db" not in st.session_state: st.session_state.db = {}
if "baseline_db" not in st.session_state: st.session_state.baseline_db = {}
if "logs" not in st.session_state: st.session_state.logs = []

def log_event(module: str, msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    color = {"INFO": "cyan", "WARN": "yellow", "ERROR": "red", "SUCCESS": "lime"}.get(level, "white")
    st.session_state.logs.append(
        f"<span style='color: #888;'>[{timestamp}]</span> "
        f"<span style='color: {color};'>[{level}]</span> "
        f"<b>[{module}]</b> {msg}"
    )

# =============================================================================
# 2. UI/UX AESTHETICS
# =============================================================================
def apply_theme():
    is_dark = st.session_state.theme == "Dark"
    is_compact = st.session_state.compact_mode

    bg_color = "#070B14" if is_dark else "#F1F5F9"
    panel_bg = "rgba(13, 20, 36, 0.7)" if is_dark else "rgba(255, 255, 255, 0.8)"
    text_color = "#E2E8F0" if is_dark else "#1E293B"
    primary_glow = "#00E5FF" if is_dark else "#2563EB"
    border_color = f"rgba({'0, 229, 255' if is_dark else '37, 99, 235'}, 0.25)"
    compact_padding = "10px" if is_compact else "20px"

    custom_css = f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');
        .stApp {{
            background-color: {bg_color};
            background-image:
                radial-gradient(circle at 15% 50%, rgba(0, 229, 255, 0.03), transparent 25%),
                radial-gradient(circle at 85% 30%, rgba(0, 229, 255, 0.04), transparent 25%);
            color: {text_color};
            font-family: 'Rajdhani', sans-serif;
        }}
        h1, h2, h3 {{ font-family: 'Rajdhani', sans-serif; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: {primary_glow}; text-shadow: 0 0 10px rgba(0,229,255,0.3); }}
        p, span, div, li {{ font-family: 'Rajdhani', sans-serif; font-size: 1.05rem; }}
        .glass-panel {{
            background: {panel_bg};
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid {border_color};
            border-radius: 8px;
            padding: {compact_padding};
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
        }}
        .glass-panel:hover {{ border-color: rgba(0, 229, 255, 0.5); box-shadow: 0 0 15px rgba(0,229,255,0.15); }}
        [data-testid="stSidebar"] {{
            background: rgba(7, 11, 20, 0.95) !important;
            border-right: 1px solid {border_color};
            backdrop-filter: blur(10px);
        }}
        [data-testid="stMetricContainer"] {{
            background: {panel_bg};
            border: 1px solid {border_color};
            border-left: 4px solid {primary_glow};
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        }}
        [data-testid="stMetricValue"] {{ font-family: 'Fira Code', monospace; color: {primary_glow}; text-shadow: 0 0 8px rgba(0,229,255,0.4); }}
        .terminal-box {{
            background-color: #05080F;
            border: 1px solid #1E2D4A;
            border-radius: 6px;
            padding: 15px;
            font-family: 'Fira Code', monospace !important;
            font-size: 0.85rem;
            height: 500px;
            overflow-y: auto;
            color: #A0AEC0;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.8);
        }}
        .terminal-box b {{ color: #00E5FF; }}
        .stButton>button {{
            background: transparent;
            border: 1px solid {primary_glow};
            color: {primary_glow};
            font-family: 'Rajdhani', sans-serif;
            font-weight: 600;
            letter-spacing: 1px;
            text-transform: uppercase;
            transition: all 0.3s ease;
        }}
        .stButton>button:hover {{
            background: rgba(0, 229, 255, 0.1);
            box-shadow: 0 0 15px rgba(0, 229, 255, 0.4);
            border-color: #00ffff;
            color: #fff;
        }}
        .gap-critical {{ background: rgba(255,0,51,0.15); border-left: 3px solid #FF0033; padding: 8px; border-radius: 4px; margin: 4px 0; }}
        .gap-high {{ background: rgba(255,153,0,0.15); border-left: 3px solid #FF9900; padding: 8px; border-radius: 4px; margin: 4px 0; }}
        .gap-medium {{ background: rgba(0,229,255,0.10); border-left: 3px solid #00E5FF; padding: 8px; border-radius: 4px; margin: 4px 0; }}
        .gap-low {{ background: rgba(0,255,102,0.08); border-left: 3px solid #00FF66; padding: 8px; border-radius: 4px; margin: 4px 0; }}
        .covered-row {{ background: rgba(0,255,102,0.08); }}
        .watermark {{
            position: fixed; bottom: 12px; right: 24px;
            font-family: 'Fira Code', monospace; font-size: 10px;
            color: {primary_glow}; opacity: 0.6; pointer-events: none;
            z-index: 1000; letter-spacing: 1.5px; text-align: right; line-height: 1.5;
        }}
        [data-testid="stDataFrame"] {{ font-family: 'Fira Code', monospace; font-size: 0.9rem; }}
    </style>
    <div class="watermark"><b>TITAN CIS EXTRACTOR // ENGINE 5.8</b><br>&copy; 2026 LUCKY PRADANA. ALL RIGHTS RESERVED.</div>
    """
    st.markdown(custom_css, unsafe_allow_html=True)


# =============================================================================
# 3. CORE ENGINES
# =============================================================================
@dataclass
class ParseResult:
    rule_id: str
    title: str = ""
    level: str = ""
    priority: str = "Medium"
    description: str = ""
    rationale: str = ""
    impact: str = ""
    audit: str = ""
    remediation: str = ""
    default_value: str = ""
    references: str = ""
    found_on_page: int = -1


class TitanBackend:
    """Engine for official CIS Benchmark PDFs"""
    def __init__(self):
        self.RE_RULE_EXACT = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)', re.IGNORECASE)
        self.RE_SECTION = re.compile(
            r'^(Profile\s+Applicability|Level\s*[123]|Description|Rationale(?:\s+Statement)?'
            r'|Impact(?:\s+Statement)?|Audit(?:\s+Procedure)?'
            r'|Remediation(?:\s+Procedure)?|Default\s+Value|References):?\s*', re.IGNORECASE)
        self.RE_TOC = re.compile(r'^(\d+(?:\.\d+)+).*?(?:\.+)\s*(\d+)\s*$')
        self.RE_NOISE = re.compile(r'(Page\s+\d+|Internal\s+Only[^\n]*|P\s+a\s+g\s+e\s*\|\s*\d+)', re.IGNORECASE)
        self.RE_APPENDIX_START = re.compile(
            r'^(?:Appendix:\s*)?(?:Summary\s+Table|Recommendation\s+Summary|CIS\s+Controls\s+v\d+\s+IG\s+\d+\s+Mapped\s+Recommendations)',
            re.IGNORECASE)
        self.RE_APPENDIX_STOP = re.compile(r'^(?:Appendix:\s*)?Change History', re.IGNORECASE)
        self.RE_WHITESPACE = re.compile(r'\s+')
        self.SECTION_MAP = {
            "profile applicability": "level", "level 1": "level", "level 2": "level", "level 3": "level",
            "description": "description", "rationale": "rationale", "impact": "impact",
            "audit": "audit", "remediation": "remediation", "default value": "default_value", "references": "references"
        }
        self._SECTION_LOOKUP = {k: v for k, v in self.SECTION_MAP.items()}

    def _get_priority(self, title: str, description: str) -> str:
        t, d = title.lower(), description.lower()
        if any(x in t or x in d for x in ["password", "credential", "private key", "encryption", "admin", "root"]): return "Critical"
        if any(x in t or x in d for x in ["remote access", "ssh", "rdp", "firewall", "network", "access control"]): return "High"
        if any(x in t or x in d for x in ["audit", "logging", "monitoring", "banner", "message"]): return "Medium"
        return "Low"

    def _clean_text(self, parts: List[str], section_key: str = "") -> str:
        if not parts: return "N/A"
        seen = set()
        unique_parts = []
        for p in parts:
            p_clean = p.strip()
            if p_clean and p_clean.lower() not in seen:
                seen.add(p_clean.lower())
                unique_parts.append(p_clean)
        raw = self.RE_NOISE.sub("", " ".join(unique_parts))
        if section_key == "references":
            raw = re.split(r'(?i)(?:Additional\s+Information|CIS\s+Controls?)', raw)[0]
        text = self.RE_WHITESPACE.sub(" ", raw).strip()
        half = len(text) // 2
        if text and len(text) > 4 and text[:half].strip().lower() == text[half:].strip().lower():
            text = text[:half].strip()
        return text or "N/A"

    def _sort_key(self, rule_id: str) -> list:
        try: return [int(p) for p in rule_id.split(".")]
        except: return [0]

    def process_pdf(self, pdf_bytes: bytes, filename: str) -> Tuple[List[dict], dict]:
        start_time = time.time()
        log_event("CIS_ENGINE", f"Initializing Titan Parser for {filename}")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        num_pages = len(doc)
        log_event("OCR_CORE", f"Loaded document with {num_pages} pages")
        cache = []
        for page in doc:
            text = page.get_text()
            cache.append(self.RE_NOISE.sub("", text) if text else "")
        toc_pages = {}
        master_ids = []
        in_app = False
        for pg in cache:
            for line in pg.split("\n"):
                line = line.strip()
                if not line: continue
                m_toc = self.RE_TOC.match(line)
                if m_toc: toc_pages[m_toc.group(1)] = int(m_toc.group(2))
                if self.RE_APPENDIX_START.search(line): in_app = True
                if in_app and self.RE_APPENDIX_STOP.search(line): in_app = False
                if in_app:
                    m_rid = re.match(r'^(\d+(?:\.\d+)+)', line)
                    if m_rid: master_ids.append(m_rid.group(1))
        master_ids = list(dict.fromkeys(master_ids))
        if not master_ids:
            master_ids = [rid for rid in toc_pages if rid.count(".") >= 1]
        master_set = set(master_ids)
        final_rules = {}
        current_id, current_sec = None, "title"
        tmp = {k: [] for k in ["title", "level", "description", "rationale", "impact", "audit", "remediation", "default_value", "references"]}

        def _iter_lines(text_cache):
            for page_text in text_cache: yield from page_text.split("\n")

        for line in _iter_lines(cache):
            line = line.strip()
            if not line: continue
            m_rule = self.RE_RULE_EXACT.match(line)
            if m_rule and m_rule.group(1) in master_set:
                if current_id:
                    final_rules[current_id] = ParseResult(
                        rule_id=current_id,
                        **{k: self._clean_text(v, k) for k, v in tmp.items()},
                        found_on_page=toc_pages.get(current_id, -1)
                    )
                    final_rules[current_id].priority = self._get_priority(
                        final_rules[current_id].title, final_rules[current_id].description)
                current_id, current_sec = m_rule.group(1), "title"
                tmp = {k: [] for k in tmp.keys()}
                tmp["title"] = [m_rule.group(2)]
                continue
            if not current_id: continue
            m_sec = self.RE_SECTION.match(line)
            if m_sec:
                key = m_sec.group(1).lower().strip()
                current_sec = next((v for k, v in self._SECTION_LOOKUP.items() if key.startswith(k)), current_sec)
                rem = self.RE_SECTION.sub("", line).strip()
                if rem: tmp[current_sec].append(rem)
            else:
                tmp[current_sec].append(line)
        if current_id:
            final_rules[current_id] = ParseResult(
                current_id,
                **{k: self._clean_text(v, k) for k, v in tmp.items()},
                found_on_page=toc_pages.get(current_id, -1)
            )
            final_rules[current_id].priority = self._get_priority(
                final_rules[current_id].title, final_rules[current_id].description)
        doc.close()
        gc.collect()
        exec_time = time.time() - start_time
        log_event("SUCCESS", f"CIS Extraction completed in {exec_time:.2f}s. Found {len(final_rules)} rules.", "SUCCESS")
        ids = sorted(final_rules.keys(), key=self._sort_key)
        report = {
            "toc_count": len(master_ids),
            "extracted_count": len(final_rules),
            "pages": num_pages,
            "exec_time": exec_time,
            "success_rate": round((len(final_rules) / len(master_ids) * 100) if master_ids else 100, 2)
        }
        return [asdict(final_rules[rid]) for rid in ids], report


class BaselineBackend:
    """
    State-machine parser for Company Internal Standard Documents (e.g. PNM Web Server
    Hardening Checklist). Correctly handles PDF table structure where:
      - Rule ID sits alone on its own line  ("1.1  ")
      - Parameter name follows on next line(s), ends when line has trailing double-space
      - Standard value follows until a blank/compliance line
      - Compliance (Y/N/NA) or empty comes after value
    """
    # Rule ID is the ONLY content on its line (digits.digits, all whitespace around)
    RE_RULE_ID   = re.compile(r'^(\d+(?:\.\d+)+)\s*$')
    # Single digit alone = category section number ("1", "2" ...)
    RE_CAT_NUM   = re.compile(r'^(\d+)\s*$')
    # Compliance cell values
    RE_COMP_CELL = re.compile(r'^(Y|N|NA|N/A|YES|NO)\s*$', re.IGNORECASE)
    # Server type header like "b. Nginx" or "a. Microsoft IIS"
    RE_SERVER_HDR = re.compile(
        r'^[a-c]\.\s*(Microsoft\s+IIS|IIS|Nginx|NGINX|Apache)', re.IGNORECASE)
    # Lines to skip (headers, footers, signatures)
    RE_NOISE = re.compile(
        r'^(Dokumen Terbatas|DOKUMEN STANDAR|\(Dokumen Security|Divisi\s*$|'
        r'Tanggal Efektif|No\. Revisi|No\. Dokumen|Halaman\s*:|Halaman\s*$|'
        r'KSD\s*$|RBZ\s*$|MUL\s*$|HYO\s*$|DHD\s*$|ORE\s*$|SPJ\s*$|'
        r'Pelaksana\s*$|Kabag\s*$|Wakadiv\s*$|Kadiv\s*$|'
        r'Reff\.|Nama Parameter|Standart Value|Complia|nce\s*$|'
        r'Comment|Commen|ts\s*$|\(Y/N\)|\(Y/N/N|RIWAYAT|Revisi Oleh|'
        r'Keterangan|Penyesuaian|Penambahan|Kholidah|Syadiah|'
        r'Operasional\s*$|Security\s*$|Teknologi\s*$|Informasi\s*$|'
        r'dan\s*$|:\s*$|:\s*0\.|:\s*PNM|:\s*\d)', re.IGNORECASE
    )

    @staticmethod
    def _ends_with_double_space(line: str) -> bool:
        """PDF table column boundary: line ends with 2+ trailing spaces."""
        return len(line) - len(line.rstrip()) >= 2

    @staticmethod
    def _is_blank(line: str) -> bool:
        return line.strip() == ""

    def _sort_key(self, rule_id: str) -> list:
        try: return [int(p) for p in rule_id.split(".")]
        except: return [0]

    def process_pdf(self, pdf_bytes: bytes, filename: str) -> Tuple[List[dict], dict]:
        start_time = time.time()
        log_event("BASELINE_ENGINE", f"Initializing State-Machine Baseline Parser for {filename}")

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        num_pages = len(doc)

        # Collect all lines across the whole document
        all_lines: List[str] = []
        for page in doc:
            for ln in page.get_text().split('\n'):
                all_lines.append(ln)
        doc.close()
        gc.collect()

        # ---- State machine ----
        results_dict: Dict[str, dict] = {}
        current_server   = "IIS"
        current_category = ""
        pending_cat_name = False   # next non-noise line = category name
        current_id       = None
        state            = "IDLE"  # IDLE → PARAM → VALUE → COMP → IDLE
        param_lines:  List[str] = []
        value_lines:  List[str] = []
        compliance_val = ""

        def flush():
            nonlocal current_id, param_lines, value_lines, compliance_val
            if not current_id: return
            # Skip revision-history fake IDs (0.0, 0.1 etc.)
            if current_id.startswith("0."): return
            param = " ".join(param_lines).strip()
            # Fix PDF hyphen line-wraps: "non-↵system" → "non-system"
            param = re.sub(r'-\s+', '-', param)
            value = " ".join(value_lines).strip()
            key = f"{current_server}:{current_id}"
            if key not in results_dict:
                results_dict[key] = {
                    "rule_id"       : current_id,
                    "server_type"   : current_server,
                    "category"      : current_category,
                    "baseline_title": param if param else "N/A",
                    "standard_value": value if value else "N/A",
                    "compliance"    : compliance_val.strip() if compliance_val.strip() else "N/A",
                    "status"        : "Implemented in Baseline"
                }

        stop_parsing = False
        for raw in all_lines:
            line     = raw.rstrip('\n')
            stripped = line.strip()

            # Stop at revision history section (end of standards content)
            if re.match(r'^RIWAYAT\s+REVISI', stripped, re.IGNORECASE):
                stop_parsing = True
            if stop_parsing:
                continue

            # -- Noise filter --
            if not stripped or self.RE_NOISE.match(stripped):
                continue

            # -- Server type header ("b. Nginx", "a. Microsoft IIS") --
            srv_m = self.RE_SERVER_HDR.match(stripped)
            if srv_m:
                flush(); current_id = None; state = "IDLE"
                s = srv_m.group(1).upper()
                if "IIS" in s:   current_server = "IIS"
                elif "NGINX" in s: current_server = "Nginx"
                else:              current_server = "Apache"
                current_category = ""
                pending_cat_name = False
                continue

            # -- Category number ("1", "2", "3" alone on a line) --
            if self.RE_CAT_NUM.match(stripped):
                pending_cat_name = True
                continue

            # -- Category name (line immediately after category number) --
            if pending_cat_name:
                if not self.RE_RULE_ID.match(stripped):
                    flush(); current_id = None; state = "IDLE"
                    current_category = stripped
                    pending_cat_name = False
                    continue
                else:
                    pending_cat_name = False
                    # fall through to rule ID handling below

            # -- Rule ID line ("1.1  ", "2.3.4 ") --
            if self.RE_RULE_ID.match(stripped):
                flush()
                current_id    = stripped
                param_lines   = []
                value_lines   = []
                compliance_val = ""
                state         = "PARAM"
                continue

            # ---- State transitions ----
            if state == "PARAM":
                if self._is_blank(line):
                    state = "VALUE"
                elif self._ends_with_double_space(line):
                    if stripped: param_lines.append(stripped)
                    state = "VALUE"
                else:
                    if stripped: param_lines.append(stripped)

            elif state == "VALUE":
                if self._is_blank(line):
                    compliance_val = ""
                    state = "COMP"
                elif self.RE_COMP_CELL.match(stripped):
                    compliance_val = stripped
                    state = "COMP"
                else:
                    if stripped: value_lines.append(stripped)

            elif state == "COMP":
                # Comments column — skip, go back to idle
                state = "IDLE"

        flush()

        exec_time = time.time() - start_time
        total = len(results_dict)
        log_event("SUCCESS",
                  f"Baseline Extraction complete in {exec_time:.2f}s — "
                  f"{total} controls extracted across "
                  f"{len(set(v['server_type'] for v in results_dict.values()))} server types.",
                  "SUCCESS")

        # Sort by rule_id numerically, then by server type
        sorted_keys = sorted(results_dict.keys(),
                             key=lambda k: self._sort_key(results_dict[k]["rule_id"]))
        result = [results_dict[k] for k in sorted_keys]
        report = {
            "pages"       : num_pages,
            "extracted"   : total,
            "exec_time"   : exec_time,
            "server_types": list(set(r["server_type"] for r in result)),
        }
        return result, report


# =============================================================================
# 4. GAP ANALYSIS ENGINE
# =============================================================================
class GapAnalysisEngine:
    """
    Performs deep gap analysis between a CIS Benchmark and a Company Baseline document.
    Supports per-server-type filtering.
    """
    PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

    @staticmethod
    def _infer_priority(title: str) -> str:
        t = title.lower()
        if any(x in t for x in ["ssl", "tls", "encrypt", "password", "credential", "cipher", "cert"]): return "Critical"
        if any(x in t for x in ["auth", "access", "firewall", "remote", "network", "permission"]): return "High"
        if any(x in t for x in ["log", "audit", "monitor", "timeout", "header", "token"]): return "Medium"
        return "Low"

    @staticmethod
    def run(cis_data: List[dict], base_data: List[dict], server_filter: str = "All") -> dict:
        """
        Returns comprehensive gap analysis result dict.
        """
        # Build lookup: rule_id -> baseline record
        base_lookup: Dict[str, dict] = {}
        for b in base_data:
            rid = b["rule_id"]
            srv = b.get("server_type", "General")
            # Allow both exact match and server-filtered match
            base_lookup.setdefault(rid, []).append(b)

        cis_ids = [r["rule_id"] for r in cis_data]
        cis_lookup = {r["rule_id"]: r for r in cis_data}

        rows = []
        for r in cis_data:
            rid = r["rule_id"]
            matches = base_lookup.get(rid, [])

            # Filter by server type if requested
            if server_filter != "All" and matches:
                matches = [m for m in matches if m.get("server_type", "General") == server_filter]

            is_covered = len(matches) > 0
            best_match = matches[0] if matches else None

            priority = r.get("priority") or GapAnalysisEngine._infer_priority(r.get("title", ""))
            category_parts = rid.split(".")
            category_id = ".".join(category_parts[:1]) if len(category_parts) >= 1 else rid

            rows.append({
                "CIS ID": rid,
                "CIS Requirement": r.get("title", "N/A"),
                "Category": r.get("level", category_id),
                "Severity": priority,
                "Covered in Baseline": is_covered,
                "Status": "✅ COVERED" if is_covered else "❌ MISSING",
                "Baseline Server Type": best_match.get("server_type", "N/A") if best_match else "N/A",
                "Baseline Parameter": best_match.get("baseline_title", "N/A") if best_match else "N/A",
                "Baseline Std Value": best_match.get("standard_value", "N/A") if best_match else "N/A",
                "Compliance Declared": best_match.get("compliance", "N/A") if best_match else "N/A",
                "Baseline Category": best_match.get("category", "N/A") if best_match else "N/A",
            })

        df = pd.DataFrame(rows)
        covered_df = df[df["Covered in Baseline"]]
        missing_df = df[~df["Covered in Baseline"]]

        # Gap breakdown by severity
        gap_by_severity = missing_df["Severity"].value_counts().to_dict()

        # Coverage by category (first number of CIS ID)
        df["Section"] = df["CIS ID"].apply(lambda x: x.split(".")[0])
        section_cov = df.groupby("Section").apply(
            lambda g: round(g["Covered in Baseline"].sum() / len(g) * 100, 1)
        ).reset_index()
        section_cov.columns = ["Section", "Coverage %"]

        total = len(df)
        covered_count = len(covered_df)
        missing_count = len(missing_df)
        coverage_pct = round(covered_count / total * 100, 1) if total > 0 else 0

        return {
            "df": df,
            "covered_df": covered_df,
            "missing_df": missing_df,
            "total": total,
            "covered_count": covered_count,
            "missing_count": missing_count,
            "coverage_pct": coverage_pct,
            "gap_by_severity": gap_by_severity,
            "section_coverage": section_cov,
        }

    @staticmethod
    def export_excel(result: dict, cis_name: str, base_name: str) -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            wb = writer.book

            # --- Formats ---
            fmt_title = wb.add_format({"bold": True, "font_size": 14, "bg_color": "#0D1424", "font_color": "#00E5FF", "border": 1})
            fmt_header = wb.add_format({"bold": True, "bg_color": "#1E2D4A", "font_color": "#FFFFFF", "border": 1, "align": "center"})
            fmt_covered = wb.add_format({"bg_color": "#063B0D", "font_color": "#00FF66", "border": 1})
            fmt_missing_crit = wb.add_format({"bg_color": "#3B0606", "font_color": "#FF0033", "bold": True, "border": 1})
            fmt_missing_high = wb.add_format({"bg_color": "#3B1F06", "font_color": "#FF9900", "border": 1})
            fmt_missing_med = wb.add_format({"bg_color": "#0D2B3B", "font_color": "#00E5FF", "border": 1})
            fmt_missing_low = wb.add_format({"bg_color": "#1A1A1A", "font_color": "#A0AEC0", "border": 1})
            fmt_normal = wb.add_format({"border": 1})
            fmt_pct_good = wb.add_format({"bg_color": "#063B0D", "font_color": "#00FF66", "border": 1, "num_format": "0.0%"})
            fmt_pct_bad = wb.add_format({"bg_color": "#3B0606", "font_color": "#FF0033", "border": 1, "num_format": "0.0%"})

            # ---- Sheet 1: Executive Summary ----
            ws_sum = wb.add_worksheet("Executive Summary")
            ws_sum.set_column("A:A", 35)
            ws_sum.set_column("B:B", 20)
            ws_sum.merge_range("A1:B1", "TITAN GAP ANALYSIS — EXECUTIVE SUMMARY", fmt_title)
            summary_rows = [
                ("CIS Benchmark Source", cis_name),
                ("Company Baseline Source", base_name),
                ("Total CIS Controls", result["total"]),
                ("Controls Covered in Baseline", result["covered_count"]),
                ("Controls MISSING in Baseline", result["missing_count"]),
                ("Overall Coverage %", f"{result['coverage_pct']}%"),
            ]
            for idx, (k, v) in enumerate(summary_rows, start=1):
                ws_sum.write(idx, 0, k, fmt_header)
                ws_sum.write(idx, 1, str(v), fmt_normal)

            row_off = len(summary_rows) + 3
            ws_sum.write(row_off, 0, "GAP BREAKDOWN BY SEVERITY", fmt_header)
            ws_sum.write(row_off, 1, "COUNT", fmt_header)
            for sev, cnt in result["gap_by_severity"].items():
                row_off += 1
                ws_sum.write(row_off, 0, sev, fmt_normal)
                ws_sum.write(row_off, 1, cnt, fmt_normal)

            # ---- Sheet 2: Full Audit Matrix ----
            df_export = result["df"].copy()
            df_export.to_excel(writer, sheet_name="Full Audit Matrix", index=False, startrow=1)
            ws_full = writer.sheets["Full Audit Matrix"]
            ws_full.merge_range(0, 0, 0, len(df_export.columns) - 1, "FULL CIS vs BASELINE AUDIT MATRIX", fmt_title)
            for col_num, col_name in enumerate(df_export.columns):
                ws_full.write(1, col_num, col_name, fmt_header)
            col_widths = [max(len(str(c)), df_export[c].astype(str).map(len).max()) for c in df_export.columns]
            for i, w in enumerate(col_widths):
                ws_full.set_column(i, i, min(w + 4, 60))
            # Color rows
            status_col = list(df_export.columns).index("Status")
            sev_col = list(df_export.columns).index("Severity")
            for row_idx, row in enumerate(df_export.itertuples(index=False), start=2):
                status = row[status_col]
                sev = row[sev_col]
                if "✅" in str(status):
                    row_fmt = fmt_covered
                elif sev == "Critical":
                    row_fmt = fmt_missing_crit
                elif sev == "High":
                    row_fmt = fmt_missing_high
                elif sev == "Medium":
                    row_fmt = fmt_missing_med
                else:
                    row_fmt = fmt_missing_low
                for col_idx, val in enumerate(row):
                    ws_full.write(row_idx, col_idx, str(val), row_fmt)

            # ---- Sheet 3: Missing Controls Only ----
            miss_df = result["missing_df"][["CIS ID", "CIS Requirement", "Severity", "Category"]].copy()
            miss_df = miss_df.sort_values("Severity", key=lambda s: s.map(GapAnalysisEngine.PRIORITY_ORDER))
            miss_df.to_excel(writer, sheet_name="Missing Controls", index=False, startrow=1)
            ws_miss = writer.sheets["Missing Controls"]
            ws_miss.merge_range(0, 0, 0, len(miss_df.columns) - 1, "⚠ MISSING CONTROLS — ACTION REQUIRED", fmt_title)
            for col_num, col_name in enumerate(miss_df.columns):
                ws_miss.write(1, col_num, col_name, fmt_header)
            for i, w in enumerate([15, 60, 15, 30]):
                ws_miss.set_column(i, i, w)
            for row_idx, row in enumerate(miss_df.itertuples(index=False), start=2):
                sev = row[2]
                row_fmt = (fmt_missing_crit if sev == "Critical" else
                           fmt_missing_high if sev == "High" else
                           fmt_missing_med if sev == "Medium" else fmt_missing_low)
                for col_idx, val in enumerate(row):
                    ws_miss.write(row_idx, col_idx, str(val), row_fmt)

            # ---- Sheet 4: Section Coverage ----
            sec_df = result["section_coverage"].copy()
            sec_df.to_excel(writer, sheet_name="Section Coverage", index=False, startrow=1)
            ws_sec = writer.sheets["Section Coverage"]
            ws_sec.merge_range(0, 0, 0, 1, "COVERAGE % BY CIS SECTION", fmt_title)
            ws_sec.write(1, 0, "Section", fmt_header)
            ws_sec.write(1, 1, "Coverage %", fmt_header)
            ws_sec.set_column("A:A", 15)
            ws_sec.set_column("B:B", 20)
            for row_idx, row in enumerate(sec_df.itertuples(index=False), start=2):
                pct = float(row[1]) / 100
                pct_fmt = fmt_pct_good if pct >= 0.7 else fmt_pct_bad
                ws_sec.write(row_idx, 0, str(row[0]), fmt_normal)
                ws_sec.write(row_idx, 1, pct, pct_fmt)

        return buf.getvalue()


# =============================================================================
# 5. CACHED WRAPPERS
# =============================================================================
@st.cache_data(show_spinner=False)
def execute_titan_cacheable(file_bytes, filename):
    engine = TitanBackend()
    return engine.process_pdf(file_bytes, filename)

@st.cache_data(show_spinner=False)
def execute_baseline_cacheable(file_bytes, filename):
    engine = BaselineBackend()
    return engine.process_pdf(file_bytes, filename)

def generate_markdown(df: pd.DataFrame) -> str:
    md = "# CIS Benchmark Extraction Report\n\nGenerated by **Titan CIS Benchmark Extractor**\n\n"
    for _, row in df.iterrows():
        md += f"## {row['rule_id']} - {row['title']}\n"
        md += f"**Priority:** {row['priority']} | **Level:** {row['level']}\n\n"
        md += f"### Description\n{row['description']}\n\n"
        md += f"### Audit\n{row['audit']}\n\n"
        md += f"### Remediation\n{row['remediation']}\n\n"
        md += "---\n\n"
    return md


# =============================================================================
# 6. NAVIGATION & SIDEBAR
# =============================================================================
apply_theme()

with st.sidebar:
    st.markdown("""
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="font-size: 28px; margin: 0; color: #00E5FF; text-shadow: 0 0 15px #00E5FF;">🛡️ TITAN CORE</h1>
            <p style="font-size: 12px; color: #888; font-family: 'Fira Code', monospace; letter-spacing: 2px;">V 5.8 ENTERPRISE</p>
        </div>
    """, unsafe_allow_html=True)

    menus = [
        "📊 Dashboard Analytics",
        "☁️ Upload Center",
        "🔍 Extracted Rules",
        "⚖️ Comparison Engine",
        "🔴 Gap Analysis",           # NEW
        "🚨 Integrity Validator",
        "💾 Export Center",
        "💻 System Logs",
        "⚙️ Settings"
    ]
    selected_nav = st.radio("COMMAND PROTOCOLS", menus, label_visibility="collapsed")
    st.markdown("---")
    st.markdown("<div style='font-family: Fira Code; font-size: 11px; color: #00E5FF;'>SYSTEM STATUS: ONLINE</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-family: Fira Code; font-size: 11px; color: #A0AEC0;'>CIS DB LOADED: {len(st.session_state.db)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-family: Fira Code; font-size: 11px; color: #A0AEC0;'>BASELINE DB: {len(st.session_state.baseline_db)}</div>", unsafe_allow_html=True)
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.markdown("""
        <div style="text-align: center; font-size: 10px; color: rgba(226, 232, 240, 0.4); font-family: 'Fira Code', monospace; letter-spacing: 1px;">
            &copy; 2026 LUCKY PRADANA<br>ALL RIGHTS RESERVED.
        </div>
    """, unsafe_allow_html=True)

nav = selected_nav.split(" ", 1)[1]


# =============================================================================
# 7. VIEW ROUTING
# =============================================================================

# --- DASHBOARD ANALYTICS ---
if nav == "Dashboard Analytics":
    st.title("📊 COMMAND CENTER ANALYTICS")
    if not st.session_state.db:
        st.info("⚡ System Standby. Proceed to Upload Center to ingest benchmark frameworks.")
    else:
        total_files = len(st.session_state.db)
        total_rules = sum(len(f['data']) for f in st.session_state.db.values())
        total_pages = sum(f['report']['pages'] for f in st.session_state.db.values())
        avg_success = sum(f['report']['success_rate'] for f in st.session_state.db.values()) / total_files
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("CIS FRAMEWORKS", total_files)
        c2.metric("RULES EXTRACTED", f"{total_rules:,}")
        c3.metric("BASELINE DOCS", len(st.session_state.baseline_db))
        c4.metric("EXTRACTION CONFIDENCE", f"{avg_success:.1f}%")
        st.markdown("### 📈 INTELLIGENCE OVERVIEW")
        all_data = []
        for db_name, db_content in st.session_state.db.items():
            df_temp = pd.DataFrame(db_content['data'])
            df_temp['Source'] = db_name
            all_data.append(df_temp)
        merged_df = pd.concat(all_data, ignore_index=True)
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            severity_counts = merged_df['priority'].value_counts().reset_index()
            severity_counts.columns = ['Severity', 'Count']
            fig1 = px.pie(severity_counts, values='Count', names='Severity', hole=0.6,
                color='Severity', color_discrete_map={"Critical": "#FF0033", "High": "#FF9900", "Medium": "#00E5FF", "Low": "#00FF66"})
            fig1.update_layout(title="Rule Severity Distribution", paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)', font=dict(family="Rajdhani", color="#E2E8F0"), margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig1, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with col_chart2:
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            merged_df['level_short'] = merged_df['level'].apply(lambda x: str(x)[:40] + '...' if len(str(x)) > 40 else str(x))
            level_counts = merged_df['level_short'].value_counts().reset_index()
            level_counts.columns = ['Level', 'Count']
            fig2 = px.bar(level_counts.head(10), x='Level', y='Count', color_discrete_sequence=["#00E5FF"])
            fig2.update_layout(title="Top Profile Applicability", paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)', font=dict(family="Rajdhani", color="#E2E8F0"), margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig2, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

# --- UPLOAD CENTER ---
elif nav == "Upload Center":
    st.title("☁️ SECURE INGESTION GATEWAY")
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        st.markdown("<div class='glass-panel'><h3>🛡️ OFFICIAL CIS BENCHMARK</h3>Upload CIS PDF framework documents. Format standar global.</div><br>", unsafe_allow_html=True)
        cis_files = st.file_uploader("Upload CIS Benchmark (PDF)", type="pdf", accept_multiple_files=True, key="cis_up")
        if cis_files and st.button("🚀 EXECUTE CIS ENGINE", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            for idx, f in enumerate(cis_files):
                with st.spinner(f"Extracting CIS: {f.name}..."):
                    res, report = execute_titan_cacheable(f.read(), f.name)
                    st.session_state.db[f.name] = {"data": res, "report": report}
                    progress_bar.progress((idx + 1) / len(cis_files))
            st.toast("CIS Extraction Complete!", icon="✅")
            st.rerun()
    with col_up2:
        st.markdown("<div class='glass-panel'><h3>🏢 COMPANY BASELINE DOC</h3>Upload Dokumen Standar Internal (PDF). Engine akan memetakan kontrol ke CIS ID dan mengekstrak nilai standar + compliance status.</div><br>", unsafe_allow_html=True)
        base_files = st.file_uploader("Upload Internal Standard (PDF)", type="pdf", accept_multiple_files=True, key="base_up")
        if base_files and st.button("🚀 EXECUTE BASELINE EXTRACTOR", use_container_width=True):
            progress_bar = st.progress(0)
            for idx, f in enumerate(base_files):
                with st.spinner(f"Extracting Baseline: {f.name}..."):
                    res, report = execute_baseline_cacheable(f.read(), f.name)
                    st.session_state.baseline_db[f.name] = {"data": res, "report": report}
                    progress_bar.progress((idx + 1) / len(base_files))
            st.toast("Baseline Extraction Complete!", icon="✅")
            st.rerun()

# --- EXTRACTED RULES ---
elif nav == "Extracted Rules":
    st.title("🔍 RULE EXPLORER")
    tab1, tab2 = st.tabs(["🛡️ CIS BENCHMARKS", "🏢 COMPANY BASELINES"])
    with tab1:
        if not st.session_state.db:
            st.warning("CIS Database empty.")
        else:
            target = st.selectbox("SELECT CIS DATABASE", list(st.session_state.db.keys()))
            df = pd.DataFrame(st.session_state.db[target]["data"])
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            fc1, fc2, fc3, fc4 = st.columns(4)
            search_q = fc1.text_input("🔍 Quick Search", placeholder="Regex / Text...")
            lvl_filter = fc2.multiselect("Filter by Level", options=df['level'].unique())
            pri_filter = fc3.multiselect("Filter by Severity", options=["Critical", "High", "Medium", "Low"])
            if search_q: df = df[df.apply(lambda r: search_q.lower() in str(r.values).lower(), axis=1)]
            if lvl_filter: df = df[df['level'].isin(lvl_filter)]
            if pri_filter: df = df[df['priority'].isin(pri_filter)]
            fc4.metric("Displaying Rules", len(df))
            st.markdown("</div><br>", unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True, height=600, hide_index=True)
    with tab2:
        if not st.session_state.baseline_db:
            st.warning("Baseline Database empty.")
        else:
            target_base = st.selectbox("SELECT BASELINE DATABASE", list(st.session_state.baseline_db.keys()))
            df_base = pd.DataFrame(st.session_state.baseline_db[target_base]["data"])
            report_base = st.session_state.baseline_db[target_base]["report"]
            bc1, bc2, bc3 = st.columns(3)
            bc1.metric("Extracted Controls", len(df_base))
            bc2.metric("Pages Scanned", report_base.get("pages", "N/A"))
            bc3.metric("Server Types Found", ", ".join(report_base.get("server_types", [])))
            if "server_type" in df_base.columns:
                srv_filter = st.multiselect("Filter by Server Type", df_base["server_type"].unique())
                if srv_filter:
                    df_base = df_base[df_base["server_type"].isin(srv_filter)]
            st.dataframe(df_base, use_container_width=True, height=600, hide_index=True)

# --- COMPARISON ENGINE ---
elif nav == "Comparison Engine":
    st.title("⚖️ CROSS-FRAMEWORK & AUDIT ENGINE")
    comp_tab1, comp_tab2 = st.tabs(["🔄 MULTI-CIS COMPARISON", "🚨 CIS vs COMPANY BASELINE AUDIT"])
    with comp_tab1:
        if len(st.session_state.db) < 2:
            st.warning("Requires at least 2 CIS frameworks for comparison.")
        else:
            targets = st.multiselect("SELECT CIS FRAMEWORKS", list(st.session_state.db.keys()), default=list(st.session_state.db.keys())[:2])
            if len(targets) >= 2:
                st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
                sets = {name: set(rule['rule_id'] for rule in st.session_state.db[name]['data']) for name in targets}
                common_ids = set.intersection(*sets.values())
                all_ids = sorted(list(set.union(*sets.values())), key=lambda x: [int(p) for p in x.split(".")] if re.match(r'^\d', x) else [0])
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("Total Unique Rules Assessed", len(all_ids))
                cc2.metric("Common Intersections", len(common_ids))
                cc3.metric("Divergence Factor", f"{((len(all_ids) - len(common_ids)) / len(all_ids) * 100):.1f}%")
                st.markdown("### MATRIX DIFF")
                comp_rows = []
                for rid in all_ids:
                    row = {"Rule ID": rid}
                    for name in targets:
                        rule = next((r for r in st.session_state.db[name]['data'] if r['rule_id'] == rid), None)
                        row[name] = rule['title'] if rule else "❌ MISSING"
                    comp_rows.append(row)
                comp_df = pd.DataFrame(comp_rows)
                def color_missing(val): return f"color: {'#FF0033' if val == '❌ MISSING' else 'inherit'}"
                st.dataframe(comp_df.style.map(color_missing), use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)

    with comp_tab2:
        if not st.session_state.db or not st.session_state.baseline_db:
            st.warning("Audit requires at least 1 CIS Benchmark AND 1 Company Baseline.")
        else:
            col_sel1, col_sel2, col_sel3 = st.columns(3)
            sel_cis = col_sel1.selectbox("Target CIS Benchmark", list(st.session_state.db.keys()))
            sel_base = col_sel2.selectbox("Company Baseline", list(st.session_state.baseline_db.keys()))
            base_data = st.session_state.baseline_db[sel_base]["data"]
            srv_types = ["All"] + list(set(r.get("server_type", "General") for r in base_data))
            srv_filter = col_sel3.selectbox("Filter by Server Type", srv_types)

            cis_data = st.session_state.db[sel_cis]["data"]
            result = GapAnalysisEngine.run(cis_data, base_data, srv_filter)
            df_audit = result["df"]

            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            ac1, ac2, ac3, ac4 = st.columns(4)
            ac1.metric("CIS Controls Target", result["total"])
            ac2.metric("✅ Covered in Baseline", result["covered_count"])
            ac3.metric("❌ Missing in Baseline", result["missing_count"])
            ac4.metric("Coverage %", f"{result['coverage_pct']}%")

            # Progress bar
            coverage_ratio = result["coverage_pct"] / 100
            bar_color = "#00FF66" if coverage_ratio >= 0.8 else "#FF9900" if coverage_ratio >= 0.5 else "#FF0033"
            st.markdown(f"""
                <div style="margin:10px 0;">
                    <div style="background:#1E2D4A; border-radius:4px; height:18px; width:100%;">
                        <div style="background:{bar_color}; width:{result['coverage_pct']}%; height:18px; border-radius:4px;
                             display:flex; align-items:center; justify-content:center;">
                            <span style="font-family:Fira Code; font-size:11px; color:#000; font-weight:bold;">
                                {result['coverage_pct']}% Covered
                            </span>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            st.markdown("### 📋 AUDIT GAP MATRIX")
            def color_audit(val):
                if "✅" in str(val): return "color: #00FF66"
                if "❌" in str(val): return "color: #FF0033; font-weight: bold"
                return ""
            def color_sev(val):
                if val == "Critical": return "color: #FF0033; font-weight: bold"
                if val == "High": return "color: #FF9900"
                if val == "Medium": return "color: #00E5FF"
                return "color: #A0AEC0"

            display_df = df_audit[["CIS ID", "CIS Requirement", "Severity", "Status",
                                    "Baseline Server Type", "Baseline Parameter", "Baseline Std Value", "Compliance Declared"]]
            st.dataframe(
                display_df.style.map(color_audit, subset=["Status"]).map(color_sev, subset=["Severity"]),
                use_container_width=True, height=500, hide_index=True
            )

            xls_bytes = GapAnalysisEngine.export_excel(result, sel_cis, sel_base)
            st.download_button(
                "📥 DOWNLOAD FULL AUDIT REPORT (EXCEL)",
                xls_bytes, "Titan_Audit_Report.xlsx",
                "application/vnd.ms-excel", use_container_width=True
            )
            st.markdown("</div>", unsafe_allow_html=True)


# --- GAP ANALYSIS (NEW DEDICATED PAGE) ---
elif nav == "Gap Analysis":
    st.title("🔴 DEEP GAP ANALYSIS ENGINE")
    st.markdown("*Comprehensive breakdown of what your company baseline is missing vs. the CIS standard.*")

    if not st.session_state.db or not st.session_state.baseline_db:
        st.warning("⚡ Requires at least 1 CIS Benchmark AND 1 Company Baseline document. Go to Upload Center first.")
    else:
        col_g1, col_g2, col_g3 = st.columns(3)
        sel_cis_g = col_g1.selectbox("CIS Benchmark", list(st.session_state.db.keys()), key="gap_cis")
        sel_base_g = col_g2.selectbox("Company Baseline", list(st.session_state.baseline_db.keys()), key="gap_base")
        base_data_g = st.session_state.baseline_db[sel_base_g]["data"]
        srv_types_g = ["All"] + list(set(r.get("server_type", "General") for r in base_data_g))
        srv_filter_g = col_g3.selectbox("Server Type Filter", srv_types_g, key="gap_srv")

        cis_data_g = st.session_state.db[sel_cis_g]["data"]
        result_g = GapAnalysisEngine.run(cis_data_g, base_data_g, srv_filter_g)

        # ---- METRICS ROW ----
        st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total CIS Controls", result_g["total"])
        m2.metric("Covered ✅", result_g["covered_count"])
        m3.metric("Missing ❌", result_g["missing_count"])
        m4.metric("Coverage", f"{result_g['coverage_pct']}%")
        gap_sev = result_g["gap_by_severity"]
        m5.metric("Critical Gaps 🔴", gap_sev.get("Critical", 0))
        st.markdown("</div><br>", unsafe_allow_html=True)

        # ---- CHART ROW ----
        chart1, chart2, chart3 = st.columns(3)

        with chart1:
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            labels = ["Covered", "Missing"]
            values = [result_g["covered_count"], result_g["missing_count"]]
            fig_cov = go.Figure(go.Pie(
                labels=labels, values=values, hole=0.65,
                marker_colors=["#00FF66", "#FF0033"],
                textinfo="percent+label",
                hoverinfo="label+value"
            ))
            fig_cov.add_annotation(text=f"{result_g['coverage_pct']}%", x=0.5, y=0.5,
                font_size=22, font_color="#00E5FF", showarrow=False)
            fig_cov.update_layout(title="Coverage Overview", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Rajdhani", color="#E2E8F0"), margin=dict(t=40, b=0, l=0, r=0),
                showlegend=True)
            st.plotly_chart(fig_cov, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with chart2:
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            if gap_sev:
                sev_order = ["Critical", "High", "Medium", "Low"]
                sev_labels = [s for s in sev_order if s in gap_sev]
                sev_values = [gap_sev[s] for s in sev_labels]
                sev_colors = {"Critical": "#FF0033", "High": "#FF9900", "Medium": "#00E5FF", "Low": "#A0AEC0"}
                fig_sev = go.Figure(go.Bar(
                    x=sev_labels, y=sev_values,
                    marker_color=[sev_colors.get(s, "#888") for s in sev_labels],
                    text=sev_values, textposition="outside"
                ))
                fig_sev.update_layout(title="Missing Controls by Severity", paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Rajdhani", color="#E2E8F0"),
                    margin=dict(t=40, b=20, l=0, r=0), yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
                st.plotly_chart(fig_sev, use_container_width=True)
            else:
                st.success("🎯 No gaps found — all CIS controls are covered in the baseline!")
            st.markdown("</div>", unsafe_allow_html=True)

        with chart3:
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            sec_df = result_g["section_coverage"]
            fig_sec = go.Figure(go.Bar(
                x=sec_df["Coverage %"], y=sec_df["Section"],
                orientation="h",
                marker_color=[
                    "#00FF66" if v >= 80 else "#FF9900" if v >= 50 else "#FF0033"
                    for v in sec_df["Coverage %"]
                ],
                text=[f"{v}%" for v in sec_df["Coverage %"]],
                textposition="inside"
            ))
            fig_sec.add_vline(x=80, line_dash="dash", line_color="#00E5FF", annotation_text="80% target")
            fig_sec.update_layout(title="Coverage % by CIS Section", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Rajdhani", color="#E2E8F0"),
                margin=dict(t=40, b=20, l=0, r=0), xaxis=dict(range=[0, 105]),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
            st.plotly_chart(fig_sec, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")

        # ---- MISSING CONTROLS DETAILED VIEW ----
        st.markdown("### ❌ MISSING CONTROLS DETAIL")
        missing_df = result_g["missing_df"].copy()

        if missing_df.empty:
            st.success("🎯 No missing controls! Your baseline covers all CIS requirements.")
        else:
            # Filters
            filt1, filt2, filt3 = st.columns(3)
            sev_opts = ["All"] + [s for s in ["Critical", "High", "Medium", "Low"] if s in missing_df["Severity"].values]
            sel_sev = filt1.selectbox("Filter Severity", sev_opts, key="gap_sev_filt")
            search_gap = filt2.text_input("🔍 Search", placeholder="Keyword...", key="gap_search")
            sort_by = filt3.selectbox("Sort by", ["Severity (Critical First)", "CIS ID", "Category"], key="gap_sort")

            filtered = missing_df.copy()
            if sel_sev != "All":
                filtered = filtered[filtered["Severity"] == sel_sev]
            if search_gap:
                filtered = filtered[filtered.apply(lambda r: search_gap.lower() in str(r.values).lower(), axis=1)]
            if sort_by == "Severity (Critical First)":
                filtered = filtered.sort_values("Severity", key=lambda s: s.map(GapAnalysisEngine.PRIORITY_ORDER))
            elif sort_by == "CIS ID":
                filtered = filtered.sort_values("CIS ID")
            else:
                filtered = filtered.sort_values("Category")

            st.markdown(f"**Showing {len(filtered)} missing control(s)**")

            # Render per-severity colored cards
            sev_colors_map = {"Critical": "#FF0033", "High": "#FF9900", "Medium": "#00E5FF", "Low": "#A0AEC0"}
            sev_bg_map = {"Critical": "rgba(255,0,51,0.12)", "High": "rgba(255,153,0,0.10)",
                          "Medium": "rgba(0,229,255,0.08)", "Low": "rgba(160,174,192,0.06)"}

            for _, row in filtered.iterrows():
                sev = row.get("Severity", "Low")
                color = sev_colors_map.get(sev, "#A0AEC0")
                bg = sev_bg_map.get(sev, "rgba(0,0,0,0.05)")
                st.markdown(f"""
                <div style="background:{bg}; border-left: 4px solid {color}; border-radius:6px; padding:12px 16px; margin:6px 0;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-family:Fira Code; color:{color}; font-weight:bold; font-size:1rem;">
                            [{row['CIS ID']}] {row['CIS Requirement']}
                        </span>
                        <span style="background:{color}; color:#000; border-radius:4px; padding:2px 10px;
                                     font-family:Fira Code; font-size:0.8rem; font-weight:bold;">
                            {sev}
                        </span>
                    </div>
                    <div style="margin-top:6px; font-size:0.9rem; color:#A0AEC0;">
                        <b style="color:#E2E8F0;">Category:</b> {row.get('Category','N/A')}
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")

        # ---- COVERED CONTROLS (expandable) ----
        with st.expander(f"✅ VIEW COVERED CONTROLS ({result_g['covered_count']} items)", expanded=False):
            covered_display = result_g["covered_df"][["CIS ID", "CIS Requirement", "Severity",
                                                        "Baseline Server Type", "Baseline Parameter",
                                                        "Baseline Std Value", "Compliance Declared"]]
            st.dataframe(covered_display, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ---- EXPORT ----
        st.markdown("### 💾 EXPORT GAP ANALYSIS")
        ex1, ex2 = st.columns(2)
        xls_g = GapAnalysisEngine.export_excel(result_g, sel_cis_g, sel_base_g)
        ex1.download_button("📊 EXPORT FULL EXCEL REPORT", xls_g, "Titan_GapAnalysis.xlsx",
                             "application/vnd.ms-excel", use_container_width=True)
        csv_miss = result_g["missing_df"][["CIS ID", "CIS Requirement", "Severity", "Category"]].to_csv(index=False).encode()
        ex2.download_button("📄 EXPORT MISSING CONTROLS CSV", csv_miss, "Titan_MissingControls.csv",
                             "text/csv", use_container_width=True)


# --- INTEGRITY VALIDATOR ---
elif nav == "Integrity Validator":
    st.title("🚨 INTEGRITY & CONFIDENCE SCORING")
    if not st.session_state.db:
        st.warning("Database empty.")
    else:
        target = st.selectbox("Target Benchmark", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        report = st.session_state.db[target]["report"]
        duplicates = df[df.duplicated(subset=['rule_id'], keep=False)]

        def check_numbering_gaps(ids):
            gaps = []
            grouped = {}
            for rid in ids:
                parts = rid.split(".")
                if len(parts) > 1:
                    prefix = ".".join(parts[:-1])
                    try:
                        leaf = int(parts[-1])
                        grouped.setdefault(prefix, []).append(leaf)
                    except: pass
            for prefix, leaves in grouped.items():
                leaves = sorted(leaves)
                for i in range(len(leaves) - 1):
                    if leaves[i + 1] - leaves[i] > 1:
                        gaps.append(f"Gap detected in {prefix}.* : missing after {prefix}.{leaves[i]}")
            return gaps

        gaps = check_numbering_gaps(df['rule_id'].tolist())
        integrity_score = max(0, min(100, 100 - (len(duplicates) * 2) - (len(gaps) * 1)))
        st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("Integrity Score", f"{integrity_score}%", f"{integrity_score - 100}%" if integrity_score < 100 else "Perfect")
        ic2.metric("Parser Confidence", f"{report['success_rate']}%")
        ic3.metric("Duplicate Anomalies", len(duplicates))
        st.markdown("### ⚠️ ANOMALY DETECTIONS")
        if len(duplicates) > 0:
            st.error(f"Found {len(duplicates)} duplicate Rule IDs:")
            st.dataframe(duplicates[['rule_id', 'title']], use_container_width=True)
        if gaps:
            st.warning(f"Detected {len(gaps)} potential sequential gaps:")
            with st.expander("View Gaps"):
                for g in gaps: st.write(f"- {g}")
        if duplicates.empty and not gaps:
            st.success("Structure verified. No major structural anomalies detected.")
        st.markdown("</div>", unsafe_allow_html=True)

# --- EXPORT CENTER ---
elif nav == "Export Center":
    st.title("💾 OMNI-CHANNEL EXPORT")
    if not st.session_state.db:
        st.warning("No data mapped.")
    else:
        target = st.selectbox("SELECT EXPORT PAYLOAD", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        for col in df.columns:
            df[col] = df[col].apply(lambda x: str(x)[:32000] if isinstance(x, str) else x)
        st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
        st.markdown("### GENERATE AUDIT-READY ARTIFACTS")
        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.download_button("📄 CSV", df.to_csv(index=False).encode(), f"Titan_{target}.csv", "text/csv", use_container_width=True)
        ec2.download_button("📦 JSON", df.to_json(orient='records', indent=4), f"Titan_{target}.json", "application/json", use_container_width=True)
        xb = io.BytesIO()
        with pd.ExcelWriter(xb, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}}) as writer:
            df.to_excel(writer, index=False, sheet_name='CIS_Rules')
        ec3.download_button("📊 EXCEL", xb.getvalue(), f"Titan_{target}.xlsx", "application/vnd.ms-excel", use_container_width=True)
        ec4.download_button("📝 MARKDOWN", generate_markdown(df).encode(), f"Titan_{target}.md", "text/markdown", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

# --- SYSTEM LOGS ---
elif nav == "System Logs":
    st.title("💻 NEURAL TERMINAL")
    st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
    if not st.session_state.logs:
        st.markdown("<i>Engine idling... waiting for instructions.</i>", unsafe_allow_html=True)
    else:
        for log in st.session_state.logs:
            st.markdown(log, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("CLEAR TERMINAL"):
        st.session_state.logs = []
        st.rerun()

# --- SETTINGS ---
elif nav == "Settings":
    st.title("⚙️ CONFIGURATION PROTOCOLS")
    st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown("### UI PREFERENCES")
        new_theme = st.selectbox("UI Theme", ["Dark", "Light"], index=0 if st.session_state.theme == "Dark" else 1)
        if new_theme != st.session_state.theme:
            st.session_state.theme = new_theme
            st.rerun()
        new_compact = st.toggle("Compact Mode", value=st.session_state.compact_mode)
        if new_compact != st.session_state.compact_mode:
            st.session_state.compact_mode = new_compact
            st.rerun()
    with col_s2:
        st.markdown("### ENGINE SETTINGS")
        st.session_state.perf_mode = st.selectbox("Performance Profile", ["Balanced", "Aggressive (Max CPU)", "Safe (Low Memory)"])
        st.toggle("Hardware Acceleration (GPU)", value=True, disabled=True)
        st.toggle("Aggressive Garbage Collection", value=True, disabled=True)
    st.markdown("</div>", unsafe_allow_html=True)
