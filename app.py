import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import time
import io
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple

# =============================================================================
# 1. CORE ENGINE: TITAN PRO 5.2 (DEEP-SEQUENCE & ANTI-BLEED)
# =============================================================================

@dataclass
class ParseResult:
    rule_id: str
    title: str = ""
    level: str = ""
    description: str = ""
    rationale: str = ""
    impact: str = ""
    audit: str = ""
    remediation: str = ""
    default_value: str = ""
    references: str = ""
    found_on_page: int = -1
    recovery_method: str = "exact"

class TitanBackend:
    def __init__(self):
        self.RE_RULE_EXACT = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)', re.IGNORECASE)
        self.RE_SECTION = re.compile(
            r'^(Profile\s+Applicability|Level\s*[123]|Description|Rationale(?:\s+Statement)?'
            r'|Impact(?:\s+Statement)?|Audit(?:\s+Procedure)?'
            r'|Remediation(?:\s+Procedure)?|Default\s+Value|References):?\s*', re.IGNORECASE)
        self.RE_TOC = re.compile(r'^(\d+(?:\.\d+)+).*?(?:\.+)\s*(\d+)\s*$')
        self.RE_NOISE = re.compile(r'(Page\s+\d+|Internal\s+Only[^\n]*|P\s+a\s+g\s+e\s*\|\s*\d+)', re.IGNORECASE)
        self.RE_LEVEL = re.compile(r'Level\s*(\d+)', re.IGNORECASE)
        self.RE_APPENDIX_START = re.compile(r'^(?:Appendix:\s*)?(?:Summary\s+Table|Recommendation\s+Summary|CIS\s+Controls\s+v\d+\s+IG\s+\d+\s+Mapped\s+Recommendations)', re.IGNORECASE)
        self.RE_APPENDIX_STOP = re.compile(r'^(?:Appendix:\s*)?Change History', re.IGNORECASE)
        
        self.SECTION_MAP = {
            "profile applicability": "level", "level 1": "level", "level 2": "level", "level 3": "level",
            "description": "description", "rationale": "rationale", "impact": "impact",
            "audit": "audit", "remediation": "remediation", "default value": "default_value", "references": "references"
        }

    def _clean_text(self, parts: List[str]) -> str:
        joined = self.RE_NOISE.sub("", " ".join(parts))
        return " ".join(joined.split()).strip() or "N/A"

    def _extract_level(self, parts: List[str]) -> str:
        joined = " ".join(parts)
        m = self.RE_LEVEL.search(joined)
        return f"Level {m.group(1)}" if m else (joined.strip() or "N/A")

    def _sort_key(self, rule_id: str) -> list:
        try: return [int(p) for p in rule_id.split(".")]
        except: return [0]

    def get_deep_recursive_jumps(self, ids: List[str]) -> List[str]:
        from collections import defaultdict
        hierarchy_tree = defaultdict(list)
        for rid in ids:
            parts = rid.split('.')
            if len(parts) < 2: continue
            parent_path = ".".join(parts[:-1])
            try: hierarchy_tree[parent_path].append(int(parts[-1]))
            except: continue
        jumps = []
        for parent, children in hierarchy_tree.items():
            children.sort()
            for i in range(len(children) - 1):
                curr, nxt = children[i], children[i+1]
                if nxt > curr + 1:
                    for m in range(curr + 1, nxt): jumps.append(f"{parent}.{m}")
        return jumps

    def process_pdf(self, pdf_bytes: bytes) -> Tuple[List[dict], dict]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        cache = [self.RE_NOISE.sub("", page.get_text("text")) for page in doc]
        
        toc_pages = {}
        master_ids = []
        in_app = False
        for pg in cache:
            for line in pg.split("\n"):
                line = line.strip()
                m_toc = self.RE_TOC.match(line)
                if m_toc: toc_pages[m_toc.group(1)] = int(m_toc.group(2))
                if self.RE_APPENDIX_START.search(line): in_app = True
                if in_app and self.RE_APPENDIX_STOP.search(line): in_app = False
                if in_app:
                    m_rid = re.match(r'^(\d+(?:\.\d+)+)', line)
                    if m_rid: master_ids.append(m_rid.group(1))

        master_ids = list(dict.fromkeys(master_ids))
        if not master_ids: master_ids = sorted(list(toc_pages.keys()), key=self._sort_key)

        final_rules = {}
        full_content = "\n".join(cache)
        current_id, current_sec = None, "title"
        tmp = {k: [] for k in ["title", "level", "description", "rationale", "impact", "audit", "remediation", "default_value", "references"]}

        for line in full_content.split("\n"):
            line = line.strip()
            m_rule = self.RE_RULE_EXACT.match(line)
            if m_rule and m_rule.group(1) in master_ids:
                if current_id:
                    final_rules[current_id] = ParseResult(current_id, **{k: (self._extract_level(v) if k=="level" else self._clean_text(v)) for k,v in tmp.items()}, found_on_page=toc_pages.get(current_id, -1))
                current_id, current_sec = m_rule.group(1), "title"
                tmp = {k: [] for k in tmp.keys()}; tmp["title"] = [m_rule.group(2)]
                continue
            if not current_id: continue
            m_sec = self.RE_SECTION.match(line)
            if m_sec:
                for k,v in self.SECTION_MAP.items():
                    if m_sec.group(1).lower().startswith(k): current_sec = v; break
                rem = self.RE_SECTION.sub("", line).strip()
                if rem: tmp[current_sec].append(rem)
            else: tmp[current_sec].append(line)

        if current_id:
            final_rules[current_id] = ParseResult(current_id, **{k: (self._extract_level(v) if k=="level" else self._clean_text(v)) for k,v in tmp.items()}, found_on_page=toc_pages.get(current_id, -1))

        # Deep QC Sweep
        jumps = self.get_deep_recursive_jumps(list(final_rules.keys()))
        verified_skipped = []
        for gap_id in jumps:
            found_gap = False
            for idx, pg_text in enumerate(cache):
                if re.search(rf'^{re.escape(gap_id)}\s+', pg_text, re.MULTILINE):
                    verified_skipped.append(f"{gap_id} (Detected but incomplete)")
                    found_gap = True; break
            if not found_gap: verified_skipped.append(gap_id)

        # Anti-Bleed
        ids = sorted(final_rules.keys(), key=self._sort_key)
        for i in range(len(ids)-1):
            curr, nxt = final_rules[ids[i]], ids[i+1]
            p = re.compile(rf'(?:\s|^){re.escape(nxt)}\s+(?:Ensure|Do\s+not|Review|Keep|Use|Audit)\b', re.IGNORECASE)
            for attr in ["references", "default_value", "audit"]:
                val = getattr(curr, attr)
                m = p.search(val)
                if m: setattr(curr, attr, val[:m.start()].strip()); break

        doc.close()
        return [asdict(final_rules[rid]) for rid in ids], {"skipped": verified_skipped, "toc_count": len(master_ids)}

# =============================================================================
# 2. UI FRAMEWORK (THEMES & CUSTOM CSS)
# =============================================================================

st.set_page_config(page_title="Titan CIS Extractor", page_icon="🛡️", layout="wide")

if "theme" not in st.session_state: st.session_state.theme = "Dark"
if "db" not in st.session_state: st.session_state.db = {}
if "logs" not in st.session_state: st.session_state.logs = []

def toggle_theme():
    st.session_state.theme = "Light" if st.session_state.theme == "Dark" else "Dark"

theme_css = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Fira+Code&display=swap');
    :root {{
        --primary: {"#00F0FF" if st.session_state.theme == "Dark" else "#1D4ED8"};
        --bg: {"#0B0F19" if st.session_state.theme == "Dark" else "#F9FAFB"};
        --card: {"rgba(17, 24, 39, 0.8)" if st.session_state.theme == "Dark" else "#FFFFFF"};
        --text: {"#E5E7EB" if st.session_state.theme == "Dark" else "#111827"};
    }}
    .stApp {{ background-color: var(--bg); color: var(--text); font-family: 'Rajdhani', sans-serif; }}
    [data-testid="stMetricContainer"] {{
        background: var(--card); border: 1px solid var(--primary);
        border-radius: 10px; padding: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }}
    .console {{
        background: #050505; color: #00FF41; font-family: 'Fira Code', monospace;
        padding: 15px; border-radius: 5px; border-left: 4px solid var(--primary);
        height: 200px; overflow-y: auto; font-size: 0.8rem;
    }}
    .titan-branding {{ position: fixed; bottom: 10px; right: 20px; opacity: 0.4; font-size: 12px; }}
</style>
"""
st.markdown(theme_css, unsafe_allow_html=True)

# =============================================================================
# 3. SIDEBAR & NAVIGATION
# =============================================================================

with st.sidebar:
    st.title("🛡️ TITAN CORE")
    nav = st.radio("NAVIGASI", ["DASHBOARD", "UPLOAD CENTER", "RULES VIEWER", "COMPARISON", "VALIDATOR", "LOGS & SETTINGS"])
    st.markdown("---")
    st.button(f"🌓 MODE: {st.session_state.theme.upper()}", on_click=toggle_theme, use_container_width=True)

# =============================================================================
# 4. PAGES ROUTING
# =============================================================================

if nav == "DASHBOARD":
    st.title("📊 COMMAND CENTER DASHBOARD")
    c1, c2, c3 = st.columns(3)
    total_rules = sum(len(f['data']) for f in st.session_state.db.values())
    c1.metric("TOTAL FILES", len(st.session_state.db))
    c2.metric("RULES EXTRACTED", total_rules)
    c3.metric("ENGINE STATUS", "READY" if total_rules >= 0 else "IDLE")
    if st.session_state.db:
        st.bar_chart(pd.DataFrame({k: [len(v['data'])] for k,v in st.session_state.db.items()}).T)

elif nav == "UPLOAD CENTER":
    st.title("☁️ SECURE INGESTION")
    files = st.file_uploader("Upload CIS Benchmark PDF", type="pdf", accept_multiple_files=True)
    if files and st.button("🚀 EXECUTE TITAN ENGINE", type="primary", use_container_width=True):
        engine = TitanBackend()
        for f in files:
            with st.spinner(f"Analizing {f.name}..."):
                res, report = engine.process_pdf(f.read())
                st.session_state.db[f.name] = {"data": res, "report": report}
                st.session_state.logs.append(f"SUCCESS: {f.name} - {len(res)} rules found.")
        st.success("Extraction Complete.")

elif nav == "RULES VIEWER":
    st.title("🛡️ RULE DATABASE")
    if not st.session_state.db: st.warning("Database Kosong.")
    else:
        target = st.selectbox("Pilih File", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        search = st.text_input("Cari Rule ID atau Judul...")
        if search: df = df[df.apply(lambda r: search.lower() in str(r.values).lower(), axis=1)]
        st.dataframe(df, use_container_width=True)
        
        # Export
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 DOWNLOAD CSV", csv, f"Titan_{target}.csv", "text/csv")

elif nav == "COMPARISON":
    st.title("⚖️ COMPARISON ENGINE")
    if len(st.session_state.db) < 2: st.error("Upload minimal 2 file.")
    else:
        f1 = st.selectbox("Baseline (A)", list(st.session_state.db.keys()), index=0)
        f2 = st.selectbox("Target (B)", list(st.session_state.db.keys()), index=1)
        ids_a = set(pd.DataFrame(st.session_state.db[f1]["data"])["rule_id"])
        ids_b = set(pd.DataFrame(st.session_state.db[f2]["data"])["rule_id"])
        st.write(f"Common: {len(ids_a & ids_b)} | New in B: {len(ids_b - ids_a)} | Missing in B: {len(ids_a - ids_b)}")

elif nav == "VALIDATOR":
    st.title("🔍 INTEGRITY VALIDATOR")
    if not st.session_state.db: st.warning("No Data.")
    else:
        for k, v in st.session_state.db.items():
            with st.expander(f"Report: {k}"):
                st.write(f"Deep Jump Detection: {v['report']['skipped']}")

elif nav == "LOGS & SETTINGS":
    st.title("💻 SYSTEM LOGS")
    log_str = "\n".join(st.session_state.logs[::-1])
    st.markdown(f'<div class="console">{log_str.replace("\n", "<br>")}</div>', unsafe_allow_html=True)
    if st.button("🚨 PURGE DATABASE"):
        st.session_state.db = {}; st.session_state.logs = []; st.rerun()

st.markdown('<div class="titan-branding">TITAN EXTRACTOR 5.2 | BY LUCKY PRADANA</div>', unsafe_allow_html=True)
