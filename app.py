import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import re
import concurrent.futures
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, ColumnsAutoSizeMode

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CIS Benchmark Extractor Pro",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── GLOBAL CSS (Mobile-Friendly & Aesthetics) ────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background-color: #0f1117; color: #e2e8f0; }
  .block-container { padding: 2rem 2.5rem 3rem; max-width: 1400px; }
  #MainMenu, footer, header { visibility: hidden; }

  .top-banner { display: flex; align-items: center; gap: 1rem; padding: 1.5rem 2rem; background: linear-gradient(135deg, #1a1f2e 0%, #141824 100%); border: 1px solid #2a3147; border-radius: 12px; margin-bottom: 1.8rem; }
  .banner-icon { font-size: 2.4rem; line-height: 1; }
  .banner-title { font-size: 1.6rem; font-weight: 700; color: #f1f5f9; margin: 0; }
  .banner-sub { font-size: 0.82rem; color: #64748b; margin: 0; margin-top: 0.15rem; }

  .stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.8rem; }
  /* Mobile responsiveness */
  @media (max-width: 768px) { .stat-grid { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 480px) { .stat-grid { grid-template-columns: 1fr; } }
  
  .stat-card { background: #1a1f2e; border: 1px solid #2a3147; border-radius: 10px; padding: 1.2rem 1.4rem; position: relative; overflow: hidden; }
  .stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
  .stat-card.blue::before  { background: #3b82f6; } .stat-card.green::before { background: #10b981; }
  .stat-card.amber::before { background: #f59e0b; } .stat-card.purple::before{ background: #8b5cf6; }
  .stat-label { font-size: 0.72rem; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 0.4rem; }
  .stat-value { font-size: 2rem; font-weight: 700; color: #f1f5f9; font-family: 'JetBrains Mono', monospace; line-height: 1; }
  .stat-detail { font-size: 0.75rem; color: #475569; margin-top: 0.3rem; }

  .stButton > button { background: linear-gradient(135deg, #3b82f6, #6366f1) !important; color: #fff !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; }
  [data-testid="stFileUploader"] { background: #1a1f2e !important; border: 2px dashed #2a3147 !important; border-radius: 10px !important; }
  .section-head { font-size: 0.72rem; font-weight: 700; color: #3b82f6; text-transform: uppercase; margin-bottom: 0.6rem; display: flex; align-items: center; gap: 0.5rem; }
  .section-head::after { content: ''; flex: 1; height: 1px; background: #2a3147; }
</style>
""", unsafe_allow_html=True)

# ─── NLP & ML FUNCTIONS ───────────────────────────────────────────────────────

def assign_framework_tags(title: str) -> str:
    """Auto-tagging kontrol CIS ke Framework IT Governance."""
    tags = []
    t = title.lower()
    if any(k in t for k in ['password', 'credential', 'auth', 'login']): tags.append('ISO 27001: A.9.4.3')
    if any(k in t for k in ['firewall', 'network', 'port', 'ssh']): tags.append('NIST: PR.AC-5')
    if any(k in t for k in ['log', 'audit', 'monitor']): tags.append('COBIT 2019: MEA02')
    if any(k in t for k in ['access', 'user', 'admin']): tags.append('ITIL: Access Management')
    return " | ".join(tags) if tags else "General IT Control"

def apply_ml_clustering(df: pd.DataFrame) -> pd.DataFrame:
    """Clustering otomatis menggunakan K-Means (Machine Learning)."""
    if len(df) < 5:
        df['AI_Domain_Cluster'] = 'Cluster 0'
        return df
    
    vectorizer = TfidfVectorizer(stop_words='english', max_features=100)
    X = vectorizer.fit_transform(df['Title'].fillna(''))
    n_clusters = min(6, len(df) // 5) # Maksimal 6 domain area
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    
    cluster_labels = kmeans.fit_predict(X)
    df['AI_Domain_Cluster'] = [f"Domain Area {c+1}" for c in cluster_labels]
    return df

# ─── CORE EXTRACTION LOGIC (PYMUPDF) ──────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r'Page \d+', '', text)
    text = re.sub(r'Internal Only - General', '', text)
    text = re.sub(r'© \d{4}.+?International', '', text)
    text = re.sub(r'CIS.+?Benchmark', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_single_pdf(pdf_bytes: bytes, filename: str) -> list[dict]:
    """Ekstrak aturan dari satu PDF (dirancang untuk Multiprocessing)."""
    sections = ["Profile Applicability", "Description", "Rationale", "Audit", "Remediation"]
    sections_lower = [s.lower() for s in sections]
    rules = []
    current_rule = None
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        text = page.get_text("text")
        if not text: continue

        for line in text.split('\n'):
            line_clean = line.strip()
            if not line_clean: continue

            header_match = re.search(r'^(\d+\.\d+(?:\.\d+)+)[\s\t]*(.*)', line_clean)
            if header_match:
                if current_rule: rules.append(current_rule)

                rule_id = header_match.group(1)
                title_full = header_match.group(2)

                if "...." in title_full or len(title_full) < 5:
                    current_rule = None; continue

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
                    "Framework Map": assign_framework_tags(clean_text(title_clean)),
                    "Description": "N/A", "Rationale": "N/A", "Audit": "N/A", "Remediation": "N/A",
                    "Source File": filename, "_section": None
                }
                continue

            if current_rule is None: continue

            line_lower = line_clean.lower()
            switched = False
            for idx, sec_lower in enumerate(sections_lower):
                if line_lower.startswith(sec_lower):
                    sec_real_name = sections[idx]
                    current_rule["_section"] = sec_real_name
                    content = line_clean[len(sec_real_name):].replace(":", "").strip()
                    key = "Level" if sec_real_name == "Profile Applicability" else sec_real_name
                    if content: current_rule[key] = clean_text(content)
                    switched = True
                    break

            if switched: continue

            active_sec = current_rule["_section"]
            if active_sec:
                key = "Level" if active_sec == "Profile Applicability" else active_sec
                existing = "" if current_rule[key] == "N/A" else current_rule[key]
                current_rule[key] = clean_text(existing + " " + line_clean)

    if current_rule: rules.append(current_rule)
    doc.close()
    return rules

# ─── SESSION STATE ─────────────────────────────────────────────────────────────
if "all_rules" not in st.session_state: st.session_state.all_rules = []
if "processed_files" not in st.session_state: st.session_state.processed_files = []

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="section-head">⚙️ Filter & Konfigurasi</div>', unsafe_allow_html=True)
    level_filter = st.multiselect("Level", ["Level 1", "Level 2", "BitLocker", "Next Gen"], default=["Level 1", "Level 2"])
    keyword = st.text_input("🔍 Cari Judul / ID")

    st.markdown("---")
    st.markdown('<div class="section-head">🚀 Aksi Global</div>', unsafe_allow_html=True)
    if st.button("🧠 Run ML Clustering Ulang", use_container_width=True):
        if st.session_state.all_rules:
            df_temp = pd.DataFrame(st.session_state.all_rules)
            df_temp = apply_ml_clustering(df_temp)
            st.session_state.all_rules = df_temp.to_dict('records')
            st.rerun()
            
    if st.button("🗑️ Reset Semua Data", use_container_width=True):
        st.session_state.all_rules = []; st.session_state.processed_files = []
        st.rerun()

# ─── MAIN CONTENT ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="top-banner">
  <div class="banner-icon">🛡️</div>
  <div>
    <p class="banner-title">CIS Benchmark Extractor Pro</p>
    <p class="banner-sub">Multiprocessing · AI Clustering · Juklak Generator · Jira Ready</p>
  </div>
</div>
""", unsafe_allow_html=True)

uploaded_files = st.file_uploader("Seret & lepas file PDF", type=["pdf"], accept_multiple_files=True, label_visibility="collapsed")

if st.button("⚡ Ekstrak Paralel (Multiprocessing)", disabled=not uploaded_files):
    new_files = [uf for uf in uploaded_files if uf.name not in st.session_state.processed_files]
    if new_files:
        with st.spinner(f"Memproses {len(new_files)} dokumen secara paralel..."):
            # Multiprocessing untuk ekstraksi secepat kilat
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {executor.submit(extract_single_pdf, uf.read(), uf.name): uf for uf in new_files}
                for future in concurrent.futures.as_completed(futures):
                    st.session_state.all_rules.extend(future.result())
                    st.session_state.processed_files.append(futures[future].name)
            
            # Jalankan ML Clustering Otomatis
            if st.session_state.all_rules:
                df_temp = pd.DataFrame(st.session_state.all_rules)
                df_temp = apply_ml_clustering(df_temp)
                st.session_state.all_rules = df_temp.to_dict('records')
    st.rerun()

# ─── DATA & VISUALIZATION ─────────────────────────────────────────────────────
if st.session_state.all_rules:
    df_raw = pd.DataFrame(st.session_state.all_rules)

    df = df_raw.copy()
    if level_filter:
        pattern = '|'.join([re.escape(lvl) for lvl in level_filter])
        df = df[df["Level"].str.contains(pattern, case=False, na=False)]
        
    if keyword.strip():
        kw = keyword.strip().lower()
        mask = (df["Title"].str.lower().str.contains(kw, na=False) | df["Rule ID"].str.lower().str.contains(kw, na=False))
        df = df[mask]

    st.markdown(f"""
    <div class="stat-grid">
      <div class="stat-card blue"><div class="stat-label">Total Aturan</div><div class="stat-value">{len(df_raw):,}</div><div class="stat-detail">dari {df_raw["Source File"].nunique()} dokumen</div></div>
      <div class="stat-card green"><div class="stat-label">Tampil di Tabel</div><div class="stat-value">{len(df):,}</div><div class="stat-detail">aturan (terfilter)</div></div>
      <div class="stat-card amber"><div class="stat-label">Level 1</div><div class="stat-value">{len(df[df["Level"].str.contains("Level 1", case=False, na=False)]):,}</div><div class="stat-detail">aturan dasar</div></div>
      <div class="stat-card purple"><div class="stat-label">Domain Area (ML)</div><div class="stat-value">{df["AI_Domain_Cluster"].nunique() if "AI_Domain_Cluster" in df.columns else 0}</div><div class="stat-detail">K-Means Clustering</div></div>
    </div>
    """, unsafe_allow_html=True)

    tab_grid, tab_juklak, tab_chart = st.tabs(["⚡ Interactive Grid", "📝 Juklak/SOP Generator", "📊 AI & Framework"])

    # TAB 1: INTERACTIVE AG-GRID
    with tab_grid:
        st.caption("Pilih baris tabel untuk melihat detail di Tab Juklak/SOP Generator.")
        display_cols = ["Rule ID", "Title", "Level", "Framework Map", "AI_Domain_Cluster", "Source File"]
        df_display = df[[c for c in display_cols if c in df.columns]]
        
        gb = GridOptionsBuilder.from_dataframe(df_display)
        gb.configure_pagination(paginationAutoPageSize=True)
        gb.configure_side_bar()
        gb.configure_selection('single', use_checkbox=True)
        grid_response = AgGrid(
            df_display, 
            gridOptions=gb.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
            theme='balham' # Tema gelap kompak
        )

    # TAB 2: JUKLAK / SOP GENERATOR (Personalized)
    with tab_juklak:
        selected = grid_response['selected_rows']
        if selected is not None and len(selected) > 0:
            # Pandas 2.0+ compability untuk AgGrid response
            sel_id = selected[0]['Rule ID'] if isinstance(selected[0], dict) else selected.iloc[0]['Rule ID']
            rule_data = df[df['Rule ID'] == sel_id].iloc[0]
            
            st.markdown('<div class="section-head">📄 Auto-Generated Draft</div>', unsafe_allow_html=True)
            
            draft_text = f"""### PETUNJUK PELAKSANAAN (JUKLAK) KEAMANAN ASET IT
**Terkait:** {rule_data['Title']} ({rule_data['Rule ID']})
**Framework Relasi:** {rule_data.get('Framework Map', 'N/A')}

---

**1. TUJUAN**
Memastikan pemenuhan postur keamanan siber organisasi selaras dengan standar operasional yang berlaku, khususnya pada kontrol `{rule_data['Title']}`.

**2. RUANG LINGKUP & TANGGUNG JAWAB**
*   **Fungsi PMO (Rencana Strategi Perusahaan - RSP):** Melakukan tracking pemenuhan kontrol dan integrasi audit (UAR).
*   **Fungsi Eksekusi (Aplikasi dan Teknologi Informasi - ATI):** Menerapkan prosedur hardening dan remediasi teknis pada aset terkait.

**3. RASIONALISASI KONTROL**
{rule_data['Rationale']}

**4. PROSEDUR HARDENING / REMEDIASI (TUGAS TIM ATI)**
Langkah-langkah teknis yang harus dikonfigurasi:
> {rule_data['Remediation']}

**5. PROSEDUR AUDIT & REVIEW (TUGAS TIM RSP / AUDITOR)**
Metode untuk memverifikasi kepatuhan kontrol:
> {rule_data['Audit']}
"""
            st.markdown(f'<div style="background:#1a1f2e; padding:2rem; border-radius:10px; border:1px solid #2a3147;">{draft_text}</div>', unsafe_allow_html=True)
            st.download_button("💾 Download Draft Juklak (Markdown)", draft_text, file_name=f"Juklak_{rule_data['Rule ID']}.md", mime="text/markdown")
        else:
            st.info("Pilih satu aturan di tab 'Interactive Grid' terlebih dahulu untuk membuat draft Juklak otomatis.")

    # TAB 3: CHARTS
    with tab_chart:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="section-head">AI Clustering (Topik Serupa)</div>', unsafe_allow_html=True)
            if "AI_Domain_Cluster" in df.columns: st.bar_chart(df["AI_Domain_Cluster"].value_counts())
        with c2:
            st.markdown('<div class="section-head">Distribusi Framework Tagging</div>', unsafe_allow_html=True)
            st.bar_chart(df["Framework Map"].value_counts().head(5))

    # ─── EXPORT SECTION ─────────────────────────────────────────────────────────
    st.markdown("---")
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown('<div class="section-head">💾 Export Data Standar (CSV)</div>', unsafe_allow_html=True)
        csv_data = df.drop(columns=["_section"], errors="ignore").to_csv(index=False).encode('utf-8')
        st.download_button(label=f"⬇️ Download Full CSV ({len(df):,} baris)", data=csv_data, file_name="CIS_Full_Report.csv", mime="text/csv", use_container_width=True)

    with c2:
        st.markdown('<div class="section-head">🎫 Export ke format Jira / Trello (CSV)</div>', unsafe_allow_html=True)
        # Menyiapkan kolom khusus untuk import ke sistem Ticketing
        df_jira = pd.DataFrame({
            'Summary': '[CIS] ' + df['Rule ID'] + ' - ' + df['Title'],
            'Description': 'Level: ' + df['Level'] + '\n\n*Rationale:*\n' + df['Rationale'] + '\n\n*Remediation:*\n' + df['Remediation'],
            'Issue Type': 'Task',
            'Labels': df['Framework Map'].str.replace(' | ', ',', regex=False)
        })
        jira_csv = df_jira.to_csv(index=False).encode('utf-8')
        st.download_button(label=f"⬇️ Download CSV for Jira Import", data=jira_csv, file_name="Jira_Import.csv", mime="text/csv", use_container_width=True)
