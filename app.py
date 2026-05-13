import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import re

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CIS Benchmark Extractor Pro",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── GLOBAL CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

  /* ── Base ── */
  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: #0f1117;
    color: #e2e8f0;
  }
  .block-container { padding: 2rem 2.5rem 3rem; max-width: 1400px; }

  /* ── Hide default streamlit chrome ── */
  #MainMenu, footer, header { visibility: hidden; }

  /* ── Top banner ── */
  .top-banner {
    display: flex; align-items: center; gap: 1rem; padding: 1.5rem 2rem;
    background: linear-gradient(135deg, #1a1f2e 0%, #141824 100%);
    border: 1px solid #2a3147; border-radius: 12px; margin-bottom: 1.8rem;
  }
  .banner-icon { font-size: 2.4rem; line-height: 1; }
  .banner-title { font-size: 1.6rem; font-weight: 700; color: #f1f5f9; margin: 0; }
  .banner-sub { font-size: 0.82rem; color: #64748b; margin: 0; margin-top: 0.15rem; }

  /* ── Stat cards ── */
  .stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.8rem; }
  .stat-card { background: #1a1f2e; border: 1px solid #2a3147; border-radius: 10px; padding: 1.2rem 1.4rem; position: relative; overflow: hidden; }
  .stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
  .stat-card.blue::before  { background: #3b82f6; }
  .stat-card.green::before { background: #10b981; }
  .stat-card.amber::before { background: #f59e0b; }
  .stat-card.purple::before{ background: #8b5cf6; }
  .stat-label { font-size: 0.72rem; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 0.4rem; }
  .stat-value { font-size: 2rem; font-weight: 700; color: #f1f5f9; font-family: 'JetBrains Mono', monospace; line-height: 1; }
  .stat-detail { font-size: 0.75rem; color: #475569; margin-top: 0.3rem; }

  /* ── Buttons & Upload ── */
  .stButton > button {
    background: linear-gradient(135deg, #3b82f6, #6366f1) !important; color: #fff !important;
    border: none !important; border-radius: 8px !important; font-weight: 600 !important;
  }
  .stDownloadButton > button { background: #10b981 !important; }
  [data-testid="stFileUploader"] { background: #1a1f2e !important; border: 2px dashed #2a3147 !important; border-radius: 10px !important; }

  /* ── Custom UI Elements ── */
  .section-head { font-size: 0.72rem; font-weight: 700; color: #3b82f6; text-transform: uppercase; margin-bottom: 0.6rem; display: flex; align-items: center; gap: 0.5rem; }
  .section-head::after { content: ''; flex: 1; height: 1px; background: #2a3147; }
  .log-box { background: #0d1117; border: 1px solid #2a3147; border-radius: 8px; padding: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #94a3b8; max-height: 200px; overflow-y: auto; }
  .rule-card { background: #1a1f2e; border: 1px solid #2a3147; border-radius: 10px; padding: 1.4rem; margin-bottom: 1rem; }
  .rule-title { font-size: 1rem; font-weight: 700; color: #f1f5f9; margin-bottom: 0.6rem; }
  .rule-id { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: #3b82f6; margin-bottom: 0.8rem; }
  .field-label { font-size: 0.68rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-top: 0.8rem; margin-bottom: 0.2rem; }
  .field-value { font-size: 0.84rem; color: #cbd5e1; line-height: 1.6; }
  .empty-state { text-align: center; padding: 4rem 2rem; color: #475569; }
</style>
""", unsafe_allow_html=True)


# ─── CORE EXTRACTION LOGIC (PYMUPDF) ──────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'Page \d+', '', text)
    text = re.sub(r'Internal Only - General', '', text)
    text = re.sub(r'© \d{4}.+?International', '', text)
    text = re.sub(r'CIS.+?Benchmark', '', text)
    return re.sub(r'\s+', ' ', text).strip()

@st.cache_data(show_spinner=False)
def extract_rules(pdf_bytes: bytes, filename: str) -> list[dict]:
    """Ekstrak aturan CIS Benchmark menggunakan PyMuPDF agar bebas OOM."""
    sections = ["Profile Applicability", "Description", "Rationale", "Audit", "Remediation"]
    rules = []
    current_rule = None
    
    # Membaca dari memori (bytes) menggunakan fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    for page in doc:
        text = page.get_text("text")
        if not text:
            continue

        for line in text.split('\n'):
            # Detect rule header
            header_match = re.search(r'^(\d+\.\d+(?:\.\d+)+)\s+(.*)', line.strip())
            
            if header_match:
                if current_rule and current_rule['Description'] != "N/A":
                    rules.append(current_rule)

                rule_id = header_match.group(1)
                title_full = header_match.group(2)

                if "...." in title_full or len(title_full) < 5:
                    current_rule = None
                    continue

                level = "N/A"
                if "(L1)" in title_full: level = "Level 1"
                elif "(L2)" in title_full: level = "Level 2"
                elif "(BL)" in title_full: level = "BitLocker"
                elif "(NG)" in title_full: level = "Next Gen"

                title_clean = re.sub(r'\(L\d\)\s*|\(BL\)\s*|\(NG\)\s*', '', title_full)
                current_rule = {
                    "Rule ID": rule_id,
                    "Title": clean_text(title_clean),
                    "Level": level,
                    "Description": "N/A", "Rationale": "N/A", "Audit": "N/A", "Remediation": "N/A",
                    "Source File": filename,
                    "_section": None
                }
                continue

            # Bypass jika current_rule belum terbentuk
            if current_rule is None:
                continue

            # Detect section transitions
            switched = False
            for sec in sections:
                if line.strip().startswith(sec):
                    current_rule["_section"] = sec
                    content = line.replace(sec, "").replace(":", "").strip()
                    key = "Level" if sec == "Profile Applicability" else sec
                    if content:
                        current_rule[key] = clean_text(content)
                    switched = True
                    break

            if switched:
                continue

            # Accumulate text
            active_sec = current_rule["_section"]
            if active_sec:
                key = "Level" if active_sec == "Profile Applicability" else active_sec
                existing = "" if current_rule[key] == "N/A" else current_rule[key]
                current_rule[key] = clean_text(existing + " " + line)

    if current_rule and current_rule['Description'] != "N/A":
        rules.append(current_rule)

    doc.close()
    return rules


# ─── SESSION STATE ─────────────────────────────────────────────────────────────
if "all_rules" not in st.session_state:
    st.session_state.all_rules = []
if "processed_files" not in st.session_state:
    st.session_state.processed_files = []


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="section-head">⚙️ Filter & Konfigurasi</div>', unsafe_allow_html=True)

    level_filter = st.multiselect(
        "Level",
        options=["Level 1", "Level 2", "BitLocker", "Next Gen", "N/A"],
        default=["Level 1", "Level 2"]
    )

    keyword = st.text_input("🔍 Cari Judul / ID", placeholder="contoh: password, firewall")

    st.markdown("---")
    st.markdown('<div class="section-head">📊 Export CSV</div>', unsafe_allow_html=True)
    export_cols = st.multiselect(
        "Kolom yang diekspor",
        options=["Rule ID", "Title", "Level", "Description", "Rationale", "Audit", "Remediation", "Source File"],
        default=["Rule ID", "Title", "Level", "Description", "Rationale", "Audit", "Remediation", "Source File"],
    )

    st.markdown("---")
    if st.button("🗑️ Reset Semua Data"):
        st.session_state.all_rules = []
        st.session_state.processed_files = []
        st.rerun()


# ─── MAIN CONTENT ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="top-banner">
  <div class="banner-icon">🛡️</div>
  <div>
    <p class="banner-title">CIS Benchmark Extractor Pro</p>
    <p class="banner-sub">Optimized Engine · CSV Output · Memory Safe</p>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="section-head">📤 Upload PDF</div>', unsafe_allow_html=True)
uploaded_files = st.file_uploader("Seret & lepas file PDF", type=["pdf"], accept_multiple_files=True, label_visibility="collapsed")

if st.button("⚡ Mulai Ekstraksi", disabled=not uploaded_files):
    for uf in uploaded_files:
        if uf.name in st.session_state.processed_files:
            continue
            
        with st.spinner(f"Mengekstrak {uf.name} (PyMuPDF Engine)..."):
            try:
                rules = extract_rules(uf.read(), uf.name)
                st.session_state.all_rules.extend(rules)
                st.session_state.processed_files.append(uf.name)
            except Exception as e:
                st.error(f"Error pada {uf.name}: {e}")
    st.rerun()

# ─── DATA & VISUALIZATION ─────────────────────────────────────────────────────
# Filter Logic
    df = df_raw.copy()
    
    if level_filter:
        # Ubah list level menjadi pola regex, misal: 'Level 1|Level 2'
        pattern = '|'.join([re.escape(lvl) for lvl in level_filter])
        # Gunakan str.contains agar "Level 1 - Server" tetap terdeteksi sebagai Level 1
        df = df[df["Level"].str.contains(pattern, case=False, na=False)]
        
    if keyword.strip():
        kw = keyword.strip().lower()
        mask = (
            df["Title"].str.lower().str.contains(kw, na=False) |
            df["Rule ID"].str.lower().str.contains(kw, na=False) |
            df["Description"].str.lower().str.contains(kw, na=False)
        )
        df = df[mask]

    # Stats
    total_raw = len(df_raw)
    total_filt = len(df)
    # Perbaiki juga penghitungan stat card agar menggunakan str.contains
    l1_count = len(df[df["Level"].str.contains("Level 1", case=False, na=False)])
    files_count = df_raw["Source File"].nunique() if "Source File" in df_raw.columns else 0
    # ─── EXPORT CSV ─────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-head">💾 Export ke CSV (Hemat Memori)</div>', unsafe_allow_html=True)
    
    export_scope = st.radio("Cakupan Export:", ["Hasil filter saja", "Semua data (tanpa filter)"], horizontal=True)
    df_export = df if export_scope == "Hasil filter saja" else df_raw
    export_cols_valid = [c for c in export_cols if c in df_export.columns]

    # Drop helper column sebelum di-export
    df_final = df_export[export_cols_valid].copy()
    if "_section" in df_final.columns:
        df_final = df_final.drop(columns=["_section"])

    csv_data = df_final.to_csv(index=False).encode('utf-8')
    
    st.download_button(
        label=f"⬇️ Download CSV ({len(df_final):,} baris)",
        data=csv_data,
        file_name="CIS_Benchmark_Report.csv",
        mime="text/csv",
        use_container_width=True
    )
