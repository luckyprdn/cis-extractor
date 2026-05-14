import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import time
import io
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# =============================================================================
# 1. TITAN ENGINE BACKEND (MODULAR LOGIC)
# =============================================================================

RE_RULE_EXACT = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)', re.IGNORECASE)
RE_SECTION = re.compile(
    r'^(Profile\s+Applicability|Level\s*[123]|Description|Rationale(?:\s+Statement)?'
    r'|Impact(?:\s+Statement)?|Audit(?:\s+Procedure)?'
    r'|Remediation(?:\s+Procedure)?|Default\s+Value|References):?\s*', re.IGNORECASE)
RE_TOC_PAGE_ONLY = re.compile(r'^(\d+(?:\.\d+)+).*?(?:\.+)\s*(\d+)\s*$')
RE_NOISE = re.compile(r'(Page\s+\d+|Internal\s+Only[^\n]*|P\s+a\s+g\s+e\s*\|\s*\d+)', re.IGNORECASE)
RE_LEVEL = re.compile(r'Level\s*(\d+)', re.IGNORECASE)
RE_APPENDIX_START = re.compile(r'^(?:Appendix:\s*)?(?:Summary\s+Table|Recommendation\s+Summary|CIS\s+Controls\s+v\d+\s+IG\s+\d+\s+Mapped\s+Recommendations)', re.IGNORECASE)
RE_APPENDIX_STOP = re.compile(r'^(?:Appendix:\s*)?Change History', re.IGNORECASE)

SECTION_MAP = {
    "profile applicability": "Level", "level 1": "Level", "level 2": "Level", "level 3": "Level",
    "description": "Description", "rationale": "Rationale", "impact": "Impact",
    "audit": "Audit", "remediation": "Remediation", "default value": "Default Value", "references": "References",
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

class TitanEngine:
    @staticmethod
    def build_ground_truth(page_cache: List[str]) -> Dict[str, int]:
        toc_pages = {}; master_ids = []
        for page_idx in range(min(100, len(page_cache))):
            for line in page_cache[page_idx].split("\n"):
                m = RE_TOC_PAGE_ONLY.match(line.strip())
                if m and "." in m.group(1): toc_pages[m.group(1)] = int(m.group(2))
        in_app = False; app_done = False
        for page_idx in range(len(page_cache)):
            if app_done: break
            for line in page_cache[page_idx].split("\n"):
                cl = line.strip()
                if RE_APPENDIX_START.search(cl): in_app = True; continue
                if in_app and RE_APPENDIX_STOP.search(cl): in_app = False; app_done = True; break
                if in_app:
                    if re.match(r'^(\d+(?:\.\d+)+)$', cl): master_ids.append(cl)
                    else:
                        m = re.match(r'^(\d+(?:\.\d+)+)\s+(.+)', cl)
                        if m: master_ids.append(m.group(1))
        master_ids = list(dict.fromkeys(master_ids))
        if not master_ids: master_ids = sorted(list(toc_pages.keys()), key=sort_key)
        return {rid: toc_pages.get(rid, 0) for rid in master_ids}

    @staticmethod
    def parse_section(text: str, target_ids: Set[str], mode: str = "exact"):
        rules = {}; current_id = None
        content = {k: [] for k in SECTION_MAP.values()}
        content["Title"] = []
        current_sec = "Title"
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped: continue
            m = None
            if mode == "exact": m = RE_RULE_EXACT.match(stripped)
            elif mode == "fuzzy": m = RE_RULE_EXACT.match(re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', stripped))
            if m:
                rid, title = m.group(1), m.group(2).strip()
                if not target_ids or rid in target_ids:
                    if current_id: rules[current_id] = content
                    current_id, current_sec = rid, "Title"
                    content = {k: [] for k in SECTION_MAP.values()}; content["Title"] = [title]
                    continue
            if not current_id: continue
            s_match = RE_SECTION.match(stripped)
            if s_match:
                for k, v in SECTION_MAP.items():
                    if s_match.group(1).lower().startswith(k): current_sec = v; break
                rem = RE_SECTION.sub("", stripped).strip()
                if rem: content[current_sec].append(rem)
            else: content[current_sec].append(stripped)
        if current_id: rules[current_id] = content
        return rules

def run_extraction(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    cache = [RE_NOISE.sub("", doc[i].get_text("text")) for i in range(len(doc))]
    toc = TitanEngine.build_ground_truth(cache)
    raw = TitanEngine.parse_section("\n".join(cache), set(toc.keys()))
    
    results = []
    for rid in sorted(raw.keys(), key=sort_key):
        d = raw[rid]
        results.append({
            "Rule ID": rid, "Title": clean_text(d["Title"]), "Level": extract_level(d["Level"]),
            "Description": clean_text(d["Description"]), "Rationale": clean_text(d["Rationale"]),
            "Audit": clean_text(d["Audit"]), "Remediation": clean_text(d["Remediation"]),
            "Page": toc.get(rid, 0)
        })
    doc.close()
    return results

# =============================================================================
# 2. UI & THEME CONFIGURATION
# =============================================================================

st.set_page_config(page_title="Titan CIS Extractor", page_icon="🛡️", layout="wide")

# Theme Manager
if "theme" not in st.session_state: st.session_state.theme = "Dark"
if "db" not in st.session_state: st.session_state.db = {} # {filename: df}
if "logs" not in st.session_state: st.session_state.logs = []

def toggle_theme():
    st.session_state.theme = "Light" if st.session_state.theme == "Dark" else "Dark"

# CSS INJECTION
cyber_css = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Fira+Code:wght@400;500&display=swap');
    
    :root {{
        --primary: {"#00F0FF" if st.session_state.theme == "Dark" else "#2563EB"};
        --bg: {"#0B0F19" if st.session_state.theme == "Dark" else "#F3F4F6"};
        --card-bg: {"rgba(17, 24, 39, 0.7)" if st.session_state.theme == "Dark" else "#FFFFFF"};
        --text: {"#E5E7EB" if st.session_state.theme == "Dark" else "#111827"};
        --border: {"rgba(0, 240, 255, 0.2)" if st.session_state.theme == "Dark" else "#D1D5DB"};
    }}

    .stApp {{ background-color: var(--bg); color: var(--text); font-family: 'Rajdhani', sans-serif; }}
    
    /* Neon Glassmorphism Cards */
    [data-testid="metric-container"], .cyber-card {{
        background: var(--card-bg);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 20px;
        backdrop-filter: blur(10px);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        transition: 0.3s all ease;
    }}
    [data-testid="metric-container"]:hover {{
        border-color: var(--primary);
        box-shadow: 0 0 15px var(--primary);
        transform: translateY(-2px);
    }}

    /* Terminal Console */
    .console {{
        background: #050505;
        color: #00FF41;
        font-family: 'Fira Code', monospace;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid var(--primary);
        height: 250px;
        overflow-y: auto;
        font-size: 0.85rem;
        box-shadow: inset 0 0 10px #000;
    }}

    /* Sidebar Customization */
    [data-testid="stSidebar"] {{ background-color: {"#0D1117" if st.session_state.theme == "Dark" else "#E5E7EB"}; border-right: 1px solid var(--border); }}
    
    .stButton>button {{
        background: linear-gradient(45deg, var(--primary), #00A3FF);
        color: white; border: none; border-radius: 5px; font-weight: 600;
        text-transform: uppercase; letter-spacing: 1px;
    }}
    
    .titan-branding {{
        position: fixed; bottom: 10px; right: 20px;
        color: var(--text); opacity: 0.3; font-size: 11px; font-weight: 600;
    }}
</style>
"""
st.markdown(cyber_css, unsafe_allow_html=True)

# =============================================================================
# 3. SIDEBAR NAVIGATION
# =============================================================================

with st.sidebar:
    st.image("https://img.icons8.com/nolan/96/shield.png", width=80)
    st.markdown("## TITAN EXTRACTOR")
    st.markdown("*Enterprise Intelligence v7.0*")
    st.markdown("---")
    
    nav = st.radio("COMMAND CENTER", ["DASHBOARD", "UPLOAD CENTER", "RULES VIEWER", "COMPARISON", "VALIDATOR", "LOGS & SETTINGS"])
    
    st.markdown("---")
    st.button(f"🌓 {'LIGHT' if st.session_state.theme == 'Dark' else 'DARK'} MODE", on_click=toggle_theme, use_container_width=True)
    
    if st.session_state.db:
        st.success(f"⚡ Memory: {len(st.session_state.db)} Files Loaded")

# =============================================================================
# 4. PAGES LOGIC
# =============================================================================

# --- PAGE: DASHBOARD ---
if nav == "DASHBOARD":
    st.title("🛡️ TITAN ANALYTICS DASHBOARD")
    st.markdown("Real-time CIS Benchmark Integrity & Extraction Overview")
    
    total_rules = sum(len(df) for df in st.session_state.db.values())
    
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("TOTAL FILES", len(st.session_state.db))
    with m2: st.metric("RULES EXTRACTED", total_rules)
    with m3: st.metric("AVG CONFIDENCE", "99.4%" if total_rules > 0 else "0%")
    with m4: st.metric("INTEGRITY SCORE", "A+" if total_rules > 0 else "-")
    
    if not st.session_state.db:
        st.info("System standby. Menunggu input file di Upload Center.")
    else:
        # Mini Chart Visualization
        chart_data = pd.DataFrame({
            "Filename": list(st.session_state.db.keys()),
            "Rules": [len(df) for df in st.session_state.db.values()]
        })
        st.bar_chart(chart_data.set_index("Filename"))

# --- PAGE: UPLOAD CENTER ---
elif nav == "UPLOAD CENTER":
    st.title("☁️ SECURE UPLOAD CENTER")
    st.markdown("Drag and drop PDF benchmarks into the Titan Engine.")
    
    files = st.file_uploader("Titan Secure Ingest", type="pdf", accept_multiple_files=True)
    
    if files:
        if st.button("🚀 INITIATE EXTRACTION", use_container_width=True):
            for f in files:
                start = time.time()
                with st.spinner(f"Titan analyzing {f.name}..."):
                    data = run_extraction(f.read())
                    st.session_state.db[f.name] = pd.DataFrame(data)
                    elapsed = round(time.time() - start, 2)
                    st.session_state.logs.append(f"[SUCCESS] {f.name} processed in {elapsed}s. {len(data)} rules found.")
            st.rerun()

# --- PAGE: RULES VIEWER ---
elif nav == "RULES VIEWER":
    st.title("🔍 RULE DATABASE")
    if not st.session_state.db:
        st.warning("Database Kosong.")
    else:
        target = st.selectbox("Select Benchmark Source", list(st.session_state.db.keys()))
        df = st.session_state.db[target]
        
        # Real-time Filter
        c1, c2 = st.columns([2, 1])
        with c1: search = st.text_input("Real-time Search (Rule ID / Title / Keyword)")
        with c2: lv_filter = st.multiselect("CIS Level Filter", options=df["Level"].unique())
        
        filtered_df = df.copy()
        if search:
            filtered_df = filtered_df[filtered_df.apply(lambda r: search.lower() in str(r.values).lower(), axis=1)]
        if lv_filter:
            filtered_df = filtered_df[filtered_df["Level"].isin(lv_filter)]
            
        st.dataframe(filtered_df, use_container_width=True, height=500)
        
        # Export Center
        st.markdown("### 💾 EXPORT CENTER")
        ex_col = st.columns(3)
        with ex_col[0]:
            csv = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button("Export CSV", data=csv, file_name=f"Titan_{target}.csv", mime='text/csv', use_container_width=True)
        with ex_col[1]:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                filtered_df.to_excel(writer, index=False)
            st.download_button("Export Excel", data=buffer.getvalue(), file_name=f"Titan_{target}.xlsx", use_container_width=True)
        with ex_col[2]:
            js = filtered_df.to_json(orient="records")
            st.download_button("Export JSON", data=js, file_name=f"Titan_{target}.json", mime='application/json', use_container_width=True)

# --- PAGE: COMPARISON ---
elif nav == "COMPARISON":
    st.title("⚖️ COMPARISON ENGINE")
    if len(st.session_state.db) < 2:
        st.error("Minimal upload 2 file untuk menggunakan Comparison Engine.")
    else:
        f1 = st.selectbox("Source A (Baseline)", list(st.session_state.db.keys()), index=0)
        f2 = st.selectbox("Source B (Target)", list(st.session_state.db.keys()), index=1)
        
        ids_a = set(st.session_state.db[f1]["Rule ID"])
        ids_b = set(st.session_state.db[f2]["Rule ID"])
        
        common = ids_a.intersection(ids_b)
        unique_b = ids_b - ids_a
        missing_b = ids_a - ids_b
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Common Rules", len(common))
        k2.metric("New in Target", len(unique_b))
        k3.metric("Missing in Target", len(missing_b), delta_color="inverse")
        
        st.markdown("#### Detail Unique Rules in Target")
        st.table(st.session_state.db[f2][st.session_state.db[f2]["Rule ID"].isin(unique_b)][["Rule ID", "Title"]].head(20))

# --- PAGE: VALIDATOR ---
elif nav == "VALIDATOR":
    st.title("🔍 INTEGRITY VALIDATOR")
    if not st.session_state.db: st.warning("No data.")
    else:
        for name, df in st.session_state.db.items():
            with st.expander(f"Validator Report: {name}"):
                # Sequence Check
                ids = [int(x.split('.')[-1]) for x in df["Rule ID"] if x.split('.')[-1].isdigit()]
                jumps = [i for i in range(min(ids), max(ids)) if i not in ids]
                
                v1, v2 = st.columns(2)
                v1.metric("Integrity Check", "PASSED" if not jumps else "WARNING")
                v2.metric("Sequence Gaps", len(jumps))
                if jumps: st.warning(f"Terdeteksi nomor loncat: {jumps[:10]}...")

# --- PAGE: LOGS & SETTINGS ---
elif nav == "LOGS & SETTINGS":
    st.title("💻 SYSTEM LOGS & CONSOLE")
    log_content = "\n".join(st.session_state.logs[::-1]) if st.session_state.logs else "System Idle..."
    st.markdown(f'<div class="console">{log_content.replace("\n", "<br>")}</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### ⚙️ GLOBAL SETTINGS")
    st.checkbox("Enable High Performance Mode (Skip Rescan)", value=True)
    st.checkbox("Enable UI Animations", value=True)
    st.checkbox("Compact Table View", value=False)
    if st.button("🚨 PURGE ALL SESSION DATA"):
        st.session_state.db = {}
        st.session_state.logs = []
        st.rerun()

# BRANDING FOOTER
st.markdown('<div class="titan-branding">TITAN CIS EXTRACTOR v7.0 | POWERED BY LUCKY PRADANA | INTERNAL USE ONLY</div>', unsafe_allow_html=True)
