import streamlit as st
import pandas as pd
import fitz  # ⚡ Menggunakan PyMuPDF (Performa Maksimal)
import re
import time
import io
import json
import gc
import plotly.express as px
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

# Initialize Session State
if "theme" not in st.session_state: st.session_state.theme = "Dark"
if "animations" not in st.session_state: st.session_state.animations = True
if "compact_mode" not in st.session_state: st.session_state.compact_mode = False
if "perf_mode" not in st.session_state: st.session_state.perf_mode = "Balanced"
if "db" not in st.session_state: st.session_state.db = {}  # CIS DB
if "baseline_db" not in st.session_state: st.session_state.baseline_db = {}  # Company Baseline DB
if "logs" not in st.session_state: st.session_state.logs = []

def log_event(module: str, msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    color = {"INFO": "cyan", "WARN": "yellow", "ERROR": "red", "SUCCESS": "lime"}.get(level, "white")
    st.session_state.logs.append(f"<span style='color: #888;'>[{timestamp}]</span> <span style='color: {color};'>[{level}]</span> <b>[{module}]</b> {msg}")

# =============================================================================
# 2. UI/UX AESTHETICS (FUTURISTIC SOC DASHBOARD)
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
        
        .watermark {{
            position: fixed;
            bottom: 12px;
            right: 24px;
            font-family: 'Fira Code', monospace;
            font-size: 10px;
            color: {primary_glow};
            opacity: 0.6;
            pointer-events: none;
            z-index: 1000;
            letter-spacing: 1.5px;
            text-align: right;
            line-height: 1.5;
        }}
        
        [data-testid="stDataFrame"] {{ font-family: 'Fira Code', monospace; font-size: 0.9rem; }}
        
    </style>
    
    <div class="watermark">
        <b>TITAN CIS EXTRACTOR // ENGINE 5.7</b><br>
        &copy; 2026 LUCKY PRADANA. ALL RIGHTS RESERVED.
    </div>
    """
    st.markdown(custom_css, unsafe_allow_html=True)

# =============================================================================
# 3. HYPER-EFFICIENT CORE ENGINES
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
    """ Engine khusus untuk dokumen official CIS Benchmark (Struktur baku) """
    def __init__(self):
        self.RE_RULE_EXACT = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)', re.IGNORECASE)
        self.RE_SECTION = re.compile(
            r'^(Profile\s+Applicability|Level\s*[123]|Description|Rationale(?:\s+Statement)?'
            r'|Impact(?:\s+Statement)?|Audit(?:\s+Procedure)?'
            r'|Remediation(?:\s+Procedure)?|Default\s+Value|References):?\s*', re.IGNORECASE)
        self.RE_TOC = re.compile(r'^(\d+(?:\.\d+)+).*?(?:\.+)\s*(\d+)\s*$')
        self.RE_NOISE = re.compile(r'(Page\s+\d+|Internal\s+Only[^\n]*|P\s+a\s+g\s+e\s*\|\s*\d+)', re.IGNORECASE)
        self.RE_APPENDIX_START = re.compile(r'^(?:Appendix:\s*)?(?:Summary\s+Table|Recommendation\s+Summary|CIS\s+Controls\s+v\d+\s+IG\s+\d+\s+Mapped\s+Recommendations)', re.IGNORECASE)
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
                        **{k: self._clean_text(v, k) for k,v in tmp.items()}, 
                        found_on_page=toc_pages.get(current_id, -1)
                    )
                    final_rules[current_id].priority = self._get_priority(final_rules[current_id].title, final_rules[current_id].description)
                
                current_id, current_sec = m_rule.group(1), "title"
                tmp = {k: [] for k in tmp.keys()}; tmp["title"] = [m_rule.group(2)]
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
            final_rules[current_id] = ParseResult(current_id, **{k: self._clean_text(v, k) for k,v in tmp.items()}, found_on_page=toc_pages.get(current_id, -1))
            final_rules[current_id].priority = self._get_priority(final_rules[current_id].title, final_rules[current_id].description)

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
    """ Engine khusus untuk Dokumen Standar Internal Perusahaan (Mengekstrak ID Referensi CIS) """
    def __init__(self):
        # Mencari pola angka yang mirip referensi CIS (contoh: 1.1, 1.2.3) di awal baris/teks
        self.RE_RULE = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)', re.IGNORECASE)
        self.RE_NOISE = re.compile(r'(Page\s+\d+|Internal\s+Only[^\n]*|P\s+a\s+g\s+e\s*\|\s*\d+|DOKUMEN\s+STANDAR|Halaman.*)', re.IGNORECASE)

    def process_pdf(self, pdf_bytes: bytes, filename: str) -> Tuple[List[dict], dict]:
        start_time = time.time()
        log_event("BASELINE_ENGINE", f"Initializing Company Baseline Parser for {filename}")
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        num_pages = len(doc)
        
        baseline_rules = {}
        
        for page in doc:
            # Gunakan mode 'blocks' untuk mempertahankan logika baris tabel
            blocks = page.get_text("blocks")
            for b in blocks:
                text = b[4].strip()
                text = self.RE_NOISE.sub("", text).strip()
                if not text: continue
                
                # Coba pecah per baris jika block gabungan
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    line = line.strip()
                    m = self.RE_RULE.match(line)
                    if m:
                        rule_id = m.group(1)
                        # Sisa baris atau block bisa jadi nama parameternya
                        # Ambil teks setelah ID sebagai title sementara
                        title_raw = m.group(2).strip()
                        # Jika tidak ada di baris yang sama, coba baris berikutnya
                        if not title_raw and (i + 1) < len(lines):
                            title_raw = lines[i+1].strip()
                        
                        # Simpan ke baseline rules
                        if rule_id not in baseline_rules:
                            baseline_rules[rule_id] = {
                                "rule_id": rule_id,
                                "baseline_title": title_raw,
                                "status": "Implemented in Baseline"
                            }

        doc.close()
        gc.collect()
        
        exec_time = time.time() - start_time
        log_event("SUCCESS", f"Baseline Extraction completed. Found {len(baseline_rules)} standard controls.", "SUCCESS")
        
        sorted_ids = sorted(baseline_rules.keys(), key=lambda x: [int(p) for p in x.split(".") if p.isdigit()] )
        return [baseline_rules[rid] for rid in sorted_ids], {"pages": num_pages, "extracted": len(baseline_rules), "exec_time": exec_time}

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
# 4. NAVIGATION & SIDEBAR
# =============================================================================
apply_theme()

with st.sidebar:
    st.markdown("""
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="font-size: 28px; margin: 0; color: #00E5FF; text-shadow: 0 0 15px #00E5FF;">🛡️ TITAN CORE</h1>
            <p style="font-size: 12px; color: #888; font-family: 'Fira Code', monospace; letter-spacing: 2px;">V 5.7 ENTERPRISE</p>
        </div>
    """, unsafe_allow_html=True)
    
    menus = [
        "📊 Dashboard Analytics",
        "☁️ Upload Center", 
        "🔍 Extracted Rules", 
        "⚖️ Comparison Engine",
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
    
    # Sidebar Copyright Footer
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.markdown("""
        <div style="text-align: center; font-size: 10px; color: rgba(226, 232, 240, 0.4); font-family: 'Fira Code', monospace; letter-spacing: 1px;">
            &copy; 2026 LUCKY PRADANA<br>ALL RIGHTS RESERVED.
        </div>
    """, unsafe_allow_html=True)

nav = selected_nav.split(" ", 1)[1]

# =============================================================================
# 5. VIEW ROUTING
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
            fig1 = px.pie(
                severity_counts, values='Count', names='Severity', hole=0.6,
                color='Severity', color_discrete_map={"Critical": "#FF0033", "High": "#FF9900", "Medium": "#00E5FF", "Low": "#00FF66"}
            )
            fig1.update_layout(
                title="Rule Severity Distribution",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Rajdhani", color="#E2E8F0"), margin=dict(t=40, b=0, l=0, r=0)
            )
            st.plotly_chart(fig1, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_chart2:
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            merged_df['level_short'] = merged_df['level'].apply(lambda x: str(x)[:40] + '...' if len(str(x)) > 40 else str(x))
            level_counts = merged_df['level_short'].value_counts().reset_index()
            level_counts.columns = ['Level', 'Count']
            fig2 = px.bar(
                level_counts.head(10), x='Level', y='Count',
                color_discrete_sequence=["#00E5FF"]
            )
            fig2.update_layout(
                title="Top Profile Applicability",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Rajdhani", color="#E2E8F0"), margin=dict(t=40, b=0, l=0, r=0)
            )
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
        st.markdown("<div class='glass-panel'><h3>🏢 COMPANY BASELINE DOC</h3>Upload Dokumen Standar Internal (PDF). Ekstraktor akan memetakan kontrol ke CIS ID.</div><br>", unsafe_allow_html=True)
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
            st.metric("Extracted Baseline Controls", len(df_base))
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
                unique_ids = set(all_ids) - common_ids
                
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("Total Unique Rules Assessed", len(all_ids))
                cc2.metric("Common Intersections", len(common_ids))
                cc3.metric("Divergence Factor", f"{((len(all_ids) - len(common_ids)) / len(all_ids) * 100):.1f}%")
                
                # --- MATRICES ---
                st.markdown("### MATRIX DIFF (ALL ASSESSED RULES)")
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
            col_sel1, col_sel2 = st.columns(2)
            sel_cis = col_sel1.selectbox("Select Target CIS Benchmark", list(st.session_state.db.keys()))
            sel_base = col_sel2.selectbox("Select Company Baseline", list(st.session_state.baseline_db.keys()))
            
            cis_data = st.session_state.db[sel_cis]["data"]
            base_data = st.session_state.baseline_db[sel_base]["data"]
            
            cis_ids = [r['rule_id'] for r in cis_data]
            base_ids = [r['rule_id'] for r in base_data]
            
            covered = set(cis_ids).intersection(set(base_ids))
            missing = set(cis_ids) - covered
            coverage_pct = (len(covered) / len(cis_ids) * 100) if cis_ids else 0
            
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            ac1, ac2, ac3 = st.columns(3)
            ac1.metric("CIS Controls Target", len(cis_ids))
            ac2.metric("Company Controls Mapped", len(covered))
            ac3.metric("Baseline Compliance Coverage", f"{coverage_pct:.1f}%")
            
            st.markdown("### 📊 AUDIT GAP ANALYSIS")
            audit_rows = []
            for r in cis_data:
                rid = r['rule_id']
                base_match = next((b for b in base_data if b['rule_id'] == rid), None)
                audit_rows.append({
                    "CIS ID": rid,
                    "CIS Requirement": r['title'],
                    "Severity": r['priority'],
                    "Baseline Status": "✅ COVERED" if base_match else "❌ MISSING IN BASELINE",
                    "Baseline Parameter": base_match['baseline_title'] if base_match else "N/A"
                })
            
            df_audit = pd.DataFrame(audit_rows)
            def color_audit(val): return f"color: {'#00FF66' if '✅' in str(val) else '#FF0033' if '❌' in str(val) else 'inherit'}"
            
            st.dataframe(df_audit.style.map(color_audit, subset=['Baseline Status']), use_container_width=True, hide_index=True)
            
            xb_audit = io.BytesIO()
            with pd.ExcelWriter(xb_audit, engine='xlsxwriter') as writer: df_audit.to_excel(writer, index=False)
            st.download_button("📥 DOWNLOAD GAP ANALYSIS REPORT (EXCEL)", xb_audit.getvalue(), "Titan_Gap_Analysis.xlsx", use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

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
                for i in range(len(leaves)-1):
                    if leaves[i+1] - leaves[i] > 1:
                        gaps.append(f"Gap detected in {prefix}.* : missing after {prefix}.{leaves[i]}")
            return gaps

        gaps = check_numbering_gaps(df['rule_id'].tolist())
        
        integrity_score = 100 - (len(duplicates)*2) - (len(gaps)*1)
        integrity_score = max(0, min(100, integrity_score))
        
        st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("Integrity Score", f"{integrity_score}%", f"{integrity_score-100}%" if integrity_score < 100 else "Perfect")
        ic2.metric("Parser Confidence", f"{report['success_rate']}%")
        ic3.metric("Duplicate Anomalies", len(duplicates))
        
        st.markdown("### ⚠️ ANOMALY DETECTIONS")
        if len(duplicates) > 0:
            st.error(f"Found {len(duplicates)} duplicate Rule IDs:")
            st.dataframe(duplicates[['rule_id', 'title']], use_container_width=True)
        
        if gaps:
            st.warning(f"Detected {len(gaps)} potential sequential gaps in document structure:")
            with st.expander("View Gaps"):
                for g in gaps: st.write(f"- {g}")
                
        if not duplicates.empty and not gaps:
            st.success("Structure verified. No major structural anomalies detected.")
            
        st.markdown("</div>", unsafe_allow_html=True)

# --- EXPORT CENTER ---
elif nav == "Export Center":
    st.title("💾 OMNI-CHANNEL EXPORT")
    if not st.session_state.db: st.warning("No data mapped.")
    else:
        target = st.selectbox("SELECT EXPORT PAYLOAD", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        
        for col in df.columns: 
            df[col] = df[col].apply(lambda x: str(x)[:32000] if isinstance(x, str) else x)
            
        st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
        st.markdown("### GENERATE AUDIT-READY ARTIFACTS")
        
        ec1, ec2, ec3, ec4 = st.columns(4)
        
        csv_data = df.to_csv(index=False).encode('utf-8')
        ec1.download_button("📄 EXPORT CSV", csv_data, f"Titan_{target}.csv", "text/csv", use_container_width=True)
        
        json_data = df.to_json(orient='records', indent=4)
        ec2.download_button("📦 EXPORT JSON", json_data, f"Titan_{target}.json", "application/json", use_container_width=True)
        
        xb = io.BytesIO()
        with pd.ExcelWriter(xb, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}}) as writer:
            df.to_excel(writer, index=False, sheet_name='CIS_Rules')
        ec3.download_button("📊 EXPORT EXCEL", xb.getvalue(), f"Titan_{target}.xlsx", "application/vnd.ms-excel", use_container_width=True)
        
        md_data = generate_markdown(df).encode('utf-8')
        ec4.download_button("📝 EXPORT MARKDOWN", md_data, f"Titan_{target}.md", "text/markdown", use_container_width=True)
        
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
        st.toggle("Hardware Acceleration (GPU)", value=True, disabled=True, help="Automatically managed by Titan Core")
        st.toggle("Aggressive Garbage Collection", value=True, disabled=True)
        
    st.markdown("</div>", unsafe_allow_html=True)
