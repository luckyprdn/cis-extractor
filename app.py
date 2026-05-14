import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import time
import io
import json
import plotly.express as px
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple

# =============================================================================
# 1. ENHANCED CORE ENGINE: TITAN PRO 5.3 (INTELLIGENCE & AUDIT FOCUS)
# =============================================================================

@dataclass
class ParseResult:
    rule_id: str
    title: str = ""
    level: str = ""
    priority: str = "Medium"  # Informative Feature
    description: str = ""
    rationale: str = ""
    impact: str = ""
    audit: str = ""
    remediation: str = ""
    default_value: str = ""
    references: str = ""
    found_on_page: int = -1

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

    def _get_priority(self, title: str, description: str) -> str:
        """Informative Logic: Menentukan prioritas keamanan berdasarkan keyword."""
        combined = (title + " " + description).lower()
        if any(x in combined for x in ["password", "credential", "private key", "encryption", "admin", "root"]):
            return "Critical"
        if any(x in combined for x in ["remote access", "ssh", "rdp", "firewall", "network", "access control"]):
            return "High"
        if any(x in combined for x in ["audit", "logging", "monitoring", "banner", "message"]):
            return "Medium"
        return "Low"

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
                    final_rules[current_id] = ParseResult(
                        rule_id=current_id, 
                        **{k: (self._extract_level(v) if k=="level" else self._clean_text(v)) for k,v in tmp.items()}, 
                        found_on_page=toc_pages.get(current_id, -1)
                    )
                    # Update priority semantik
                    final_rules[current_id].priority = self._get_priority(final_rules[current_id].title, final_rules[current_id].description)
                
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
            final_rules[current_id].priority = self._get_priority(final_rules[current_id].title, final_rules[current_id].description)

        doc.close()
        ids = sorted(final_rules.keys(), key=self._sort_key)
        return [asdict(final_rules[rid]) for rid in ids], {"toc_count": len(master_ids)}

# =============================================================================
# 2. UI FRAMEWORK & DASHBOARD
# =============================================================================

st.set_page_config(page_title="Titan CIS Extractor Pro", page_icon="🛡️", layout="wide")

if "theme" not in st.session_state: st.session_state.theme = "Dark"
if "db" not in st.session_state: st.session_state.db = {}
if "logs" not in st.session_state: st.session_state.logs = []

def toggle_theme():
    st.session_state.theme = "Light" if st.session_state.theme == "Dark" else "Dark"

st.markdown(f"""
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
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🛡️ TITAN CORE")
    nav = st.sidebar.radio("COMMAND CENTER", ["DASHBOARD", "UPLOAD CENTER", "RULES VIEWER", "EXPORT CENTER", "LOGS"])
    st.markdown("---")
    st.button(f"🌓 THEME: {st.session_state.theme.upper()}", on_click=toggle_theme, use_container_width=True)

# =============================================================================
# 3. PAGES LOGIC
# =============================================================================

if nav == "DASHBOARD":
    st.title("📊 AUDIT INTELLIGENCE DASHBOARD")
    if not st.session_state.db:
        st.info("System Standby. Silakan upload file di Upload Center.")
    else:
        total_rules = sum(len(f['data']) for f in st.session_state.db.values())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("LOADED FILES", len(st.session_state.db))
        c2.metric("RULES EXTRACTED", total_rules)
        c3.metric("INTEGRITY", "HIGH")
        c4.metric("SYSTEM READY", "YES")
        
        st.markdown("---")
        col_left, col_right = st.columns(2)
        
        # Gabungkan data untuk visualisasi
        all_data = []
        for f in st.session_state.db.values(): all_data.extend(f['data'])
        combined_df = pd.DataFrame(all_data)
        
        with col_left:
            st.subheader("Security Priority Distribution")
            fig_prio = px.pie(combined_df, names='priority', color='priority', 
                             color_discrete_map={'Critical':'#FF0000', 'High':'#FF8C00', 'Medium':'#FFFF00', 'Low':'#00FF00'})
            st.plotly_chart(fig_prio, use_container_width=True)
            
        with col_right:
            st.subheader("CIS Level Distribution")
            fig_lv = px.histogram(combined_df, x='level', color='level', template="plotly_dark" if st.session_state.theme=="Dark" else "plotly")
            st.plotly_chart(fig_lv, use_container_width=True)

elif nav == "UPLOAD CENTER":
    st.title("☁️ SECURE INGESTION")
    files = st.file_uploader("Upload CIS Benchmark PDF", type="pdf", accept_multiple_files=True)
    if files and st.button("🚀 EXECUTE TITAN ENGINE", type="primary", use_container_width=True):
        engine = TitanBackend()
        for f in files:
            with st.spinner(f"Processing {f.name}..."):
                res, report = engine.process_pdf(f.read())
                st.session_state.db[f.name] = {"data": res, "report": report}
                st.session_state.logs.append(f"SUCCESS: {f.name} extracted.")
        st.rerun()

elif nav == "RULES VIEWER":
    st.title("🛡️ RULE EXPLORER")
    if not st.session_state.db: st.warning("Upload file terlebih dahulu.")
    else:
        target = st.selectbox("Select Target", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        
        # Informative Coloring & Filtering
        search = st.text_input("Search ID, Title, or Priority...")
        if search: df = df[df.apply(lambda r: search.lower() in str(r.values).lower(), axis=1)]
        
        st.dataframe(df, use_container_width=True, height=500)

elif nav == "EXPORT CENTER":
    st.title("💾 MULTI-FORMAT EXPORT")
    if not st.session_state.db: st.warning("Belum ada data untuk diekspor.")
    else:
        target = st.selectbox("Pilih File untuk Ekspor", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        
        # Pembersihan limit Excel
        for col in df.columns: df[col] = df[col].apply(lambda x: str(x)[:32000] if isinstance(x, str) else x)
        
        st.markdown("### Select Format")
        c1, c2, c3 = st.columns(3)
        
        with c1:
            buffer_xlsx = io.BytesIO()
            with pd.ExcelWriter(buffer_xlsx, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}}) as writer:
                df.to_excel(writer, index=False, sheet_name='CIS_Rules')
            st.download_button("📂 Download EXCEL (.xlsx)", buffer_xlsx.getvalue(), f"Titan_{target}.xlsx", use_container_width=True)
            
        with c2:
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button("📄 Download CSV (.csv)", csv_data, f"Titan_{target}.csv", "text/csv", use_container_width=True)
            
        with c3:
            json_data = df.to_json(orient='records', indent=4)
            st.download_button("📦 Download JSON (.json)", json_data, f"Titan_{target}.json", "application/json", use_container_width=True)

elif nav == "LOGS":
    st.title("💻 SYSTEM CONSOLE")
    log_str = "\n".join(st.session_state.logs[::-1]) if st.session_state.logs else "Idle..."
    st.code(log_str, language="bash")

st.markdown('<div style="position: fixed; bottom: 10px; right: 20px; opacity: 0.4; font-size: 12px; font-weight: bold;">TITAN PRO 5.3 | BY LUCKY PRADANA</div>', unsafe_allow_html=True)
