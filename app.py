import streamlit as st
import pdfplumber
import pandas as pd
import re
import os
import io
from collections import Counter

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CIS Benchmark Extractor",
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
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.5rem 2rem;
    background: linear-gradient(135deg, #1a1f2e 0%, #141824 100%);
    border: 1px solid #2a3147;
    border-radius: 12px;
    margin-bottom: 1.8rem;
  }
  .banner-icon {
    font-size: 2.4rem;
    line-height: 1;
    background: linear-gradient(135deg, #3b82f6, #6366f1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .banner-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #f1f5f9;
    letter-spacing: -0.02em;
    margin: 0;
  }
  .banner-sub {
    font-size: 0.82rem;
    color: #64748b;
    margin: 0;
    margin-top: 0.15rem;
  }

  /* ── Stat cards ── */
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.8rem;
  }
  .stat-card {
    background: #1a1f2e;
    border: 1px solid #2a3147;
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    position: relative;
    overflow: hidden;
  }
  .stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 10px 10px 0 0;
  }
  .stat-card.blue::before  { background: #3b82f6; }
  .stat-card.green::before { background: #10b981; }
  .stat-card.amber::before { background: #f59e0b; }
  .stat-card.purple::before{ background: #8b5cf6; }
  .stat-label {
    font-size: 0.72rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.4rem;
  }
  .stat-value {
    font-size: 2rem;
    font-weight: 700;
    color: #f1f5f9;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1;
  }
  .stat-detail {
    font-size: 0.75rem;
    color: #475569;
    margin-top: 0.3rem;
  }

  /* ── Section headers ── */
  .section-head {
    font-size: 0.72rem;
    font-weight: 700;
    color: #3b82f6;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .section-head::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #2a3147;
  }

  /* ── Upload zone ── */
  [data-testid="stFileUploader"] {
    background: #1a1f2e !important;
    border: 2px dashed #2a3147 !important;
    border-radius: 10px !important;
    padding: 1.5rem !important;
    transition: border-color .2s;
  }
  [data-testid="stFileUploader"]:hover {
    border-color: #3b82f6 !important;
  }

  /* ── Buttons ── */
  .stButton > button {
    background: linear-gradient(135deg, #3b82f6, #6366f1) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 0.55rem 1.4rem !important;
    letter-spacing: 0.01em !important;
    transition: opacity .2s, transform .15s !important;
  }
  .stButton > button:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
  }

  /* ── Download button ── */
  .stDownloadButton > button {
    background: #10b981 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
  }

  /* ── Sidebar ── */
  [data-testid="stSidebar"] {
    background: #141824 !important;
    border-right: 1px solid #2a3147 !important;
  }
  [data-testid="stSidebar"] .block-container { padding: 1.5rem 1.2rem; }

  /* ── Selectbox / Multiselect ── */
  [data-testid="stSelectbox"] > div,
  [data-testid="stMultiSelect"] > div {
    background: #1a1f2e !important;
    border: 1px solid #2a3147 !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
  }

  /* ── Text input ── */
  [data-testid="stTextInput"] input {
    background: #1a1f2e !important;
    border: 1px solid #2a3147 !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important;
  }

  /* ── Dataframe ── */
  [data-testid="stDataFrame"] {
    border: 1px solid #2a3147;
    border-radius: 10px;
    overflow: hidden;
  }

  /* ── Progress ── */
  .stProgress > div > div > div { background: #3b82f6 !important; }

  /* ── Expander ── */
  .streamlit-expanderHeader {
    background: #1a1f2e !important;
    border: 1px solid #2a3147 !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
    font-weight: 600 !important;
  }

  /* ── Tag badges ── */
  .tag {
    display: inline-block;
    padding: 0.18rem 0.6rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
  }
  .tag-l1  { background: #1e3a5f; color: #60a5fa; }
  .tag-l2  { background: #2d1b69; color: #a78bfa; }
  .tag-na  { background: #1e2530; color: #64748b; }

  /* ── Log box ── */
  .log-box {
    background: #0d1117;
    border: 1px solid #2a3147;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: #94a3b8;
    max-height: 200px;
    overflow-y: auto;
    line-height: 1.7;
  }
  .log-ok  { color: #10b981; }
  .log-err { color: #f87171; }
  .log-dim { color: #475569; }

  /* ── Rule detail card ── */
  .rule-card {
    background: #1a1f2e;
    border: 1px solid #2a3147;
    border-radius: 10px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
  }
  .rule-title {
    font-size: 1rem;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 0.6rem;
  }
  .rule-id {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: #3b82f6;
    margin-bottom: 0.8rem;
  }
  .field-label {
    font-size: 0.68rem;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 0.8rem;
    margin-bottom: 0.2rem;
  }
  .field-value {
    font-size: 0.84rem;
    color: #cbd5e1;
    line-height: 1.6;
  }

  /* ── Empty state ── */
  .empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: #475569;
  }
  .empty-icon { font-size: 3rem; margin-bottom: 1rem; }
  .empty-text { font-size: 0.9rem; }

  /* ── Divider ── */
  hr { border-color: #2a3147 !important; margin: 1.5rem 0 !important; }
</style>
""", unsafe_allow_html=True)


# ─── CORE EXTRACTION LOGIC ────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'Page \d+', '', text)
    text = re.sub(r'Internal Only - General', '', text)
    text = re.sub(r'© \d{4}.+?International', '', text)
    text = re.sub(r'CIS.+?Benchmark', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def extract_rules(pdf_bytes: bytes, filename: str, log_fn=None) -> list[dict]:
    """Extract CIS Benchmark rules from a PDF byte stream."""
    sections = ["Profile Applicability", "Description", "Rationale", "Audit", "Remediation"]
    rules: list[dict] = []
    current_rule: dict | None = None
    page_count = 0

    def _log(msg: str, kind: str = ""):
        if log_fn:
            log_fn(msg, kind)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        total_pages = len(pdf.pages)
        _log(f"📄 {filename} — {total_pages} halaman ditemukan", "ok")

        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue
            page_count += 1

            for line in text.split('\n'):
                # ── Detect rule header (e.g. 1.1.1 (L1) Ensure ...)
                header_match = re.search(r'^(\d+\.\d+(?:\.\d+)+)\s+(.*)', line)
                if header_match:
                    if current_rule and current_rule['Description'] != "N/A":
                        rules.append(current_rule)

                    rule_id = header_match.group(1)
                    title_full = header_match.group(2)

                    if "...." in title_full or len(title_full) < 5:
                        current_rule = None
                        continue

                    level = "N/A"
                    if "(L1)" in title_full:
                        level = "Level 1"
                    elif "(L2)" in title_full:
                        level = "Level 2"
                    elif "(BL)" in title_full:
                        level = "BitLocker"
                    elif "(NG)" in title_full:
                        level = "Next Gen"

                    title_clean = re.sub(r'\(L\d\)\s*|\(BL\)\s*|\(NG\)\s*', '', title_full)
                    current_rule = {
                        "Rule ID":     rule_id,
                        "Title":       clean_text(title_clean),
                        "Level":       level,
                        "Description": "N/A",
                        "Rationale":   "N/A",
                        "Audit":       "N/A",
                        "Remediation": "N/A",
                        "Source File": filename,
                        "_section":    None,
                    }
                    continue

                if not current_rule:
                    continue

                # ── Detect section transitions
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

                # ── Accumulate text in current section
                sec = current_rule["_section"]
                if sec:
                    key = "Level" if sec == "Profile Applicability" else sec
                    existing = "" if current_rule[key] == "N/A" else current_rule[key]
                    current_rule[key] = clean_text(existing + " " + line)

        # Append last rule
        if current_rule and current_rule['Description'] != "N/A":
            rules.append(current_rule)

    _log(f"✅ Diekstrak {len(rules)} aturan dari {page_count} halaman aktif", "ok")

    # Clean helper key
    for r in rules:
        r.pop("_section", None)

    return rules


# ─── SESSION STATE ─────────────────────────────────────────────────────────────

if "all_rules" not in st.session_state:
    st.session_state.all_rules = []
if "logs" not in st.session_state:
    st.session_state.logs = []
if "processed_files" not in st.session_state:
    st.session_state.processed_files = []


def add_log(msg: str, kind: str = ""):
    st.session_state.logs.append((msg, kind))


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="section-head">⚙️ Filter & Konfigurasi</div>', unsafe_allow_html=True)

    level_filter = st.multiselect(
        "Level",
        options=["Level 1", "Level 2", "BitLocker", "Next Gen", "N/A"],
        default=["Level 1", "Level 2"],
        help="Filter aturan berdasarkan level CIS"
    )

    keyword = st.text_input("🔍 Cari Judul / ID", placeholder="contoh: password, firewall, 1.1.1")

    st.markdown("---")
    st.markdown('<div class="section-head">📊 Export</div>', unsafe_allow_html=True)

    export_cols = st.multiselect(
        "Kolom yang diekspor",
        options=["Rule ID", "Title", "Level", "Description", "Rationale", "Audit", "Remediation", "Source File"],
        default=["Rule ID", "Title", "Level", "Description", "Rationale", "Audit", "Remediation"],
    )

    st.markdown("---")
    st.markdown('<div class="section-head">ℹ️ Tentang</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:.75rem;color:#475569;line-height:1.8">
      🛡️ CIS Benchmark Extractor<br>
      Ekstrak, filter, dan ekspor aturan<br>
      dari PDF CIS Benchmark ke Excel.<br><br>
      Mendukung: Debian · Ubuntu · Windows
    </div>
    """, unsafe_allow_html=True)

    if st.button("🗑️ Reset Semua Data"):
        st.session_state.all_rules = []
        st.session_state.logs = []
        st.session_state.processed_files = []
        st.rerun()


# ─── MAIN CONTENT ─────────────────────────────────────────────────────────────

# Top banner
st.markdown("""
<div class="top-banner">
  <div class="banner-icon">🛡️</div>
  <div>
    <p class="banner-title">CIS Benchmark Extractor</p>
    <p class="banner-sub">Extract · Filter · Export — PDF ke Excel dalam hitungan detik</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Upload section
st.markdown('<div class="section-head">📤 Upload PDF</div>', unsafe_allow_html=True)

uploaded_files = st.file_uploader(
    "Seret & lepas file PDF CIS Benchmark di sini",
    type=["pdf"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

col_extract, col_space = st.columns([1, 4])
with col_extract:
    do_extract = st.button("⚡ Mulai Ekstraksi", use_container_width=True, disabled=not uploaded_files)

# ── Extraction process
if do_extract and uploaded_files:
    progress_bar = st.progress(0, text="Mempersiapkan...")
    log_placeholder = st.empty()

    for i, uf in enumerate(uploaded_files):
        fname = uf.name
        if fname in st.session_state.processed_files:
            add_log(f"⏭️  {fname} sudah diproses, dilewati", "dim")
            continue

        progress_bar.progress((i) / len(uploaded_files), text=f"Memproses {fname}…")
        pdf_bytes = uf.read()

        try:
            rules = extract_rules(pdf_bytes, fname, log_fn=add_log)
            st.session_state.all_rules.extend(rules)
            st.session_state.processed_files.append(fname)
        except Exception as e:
            add_log(f"❌ Error pada {fname}: {e}", "err")

    progress_bar.progress(1.0, text="✅ Selesai!")

# ── Log output
if st.session_state.logs:
    with st.expander("📋 Log Proses", expanded=False):
        log_html = ""
        for msg, kind in st.session_state.logs[-50:]:
            css = {"ok": "log-ok", "err": "log-err", "dim": "log-dim"}.get(kind, "")
            log_html += f'<div class="{css}">{msg}</div>'
        st.markdown(f'<div class="log-box">{log_html}</div>', unsafe_allow_html=True)

# ── Data section
if st.session_state.all_rules:
    df_raw = pd.DataFrame(st.session_state.all_rules)

    # Apply filters
    df = df_raw.copy()
    if level_filter:
        df = df[df["Level"].isin(level_filter)]
    if keyword.strip():
        kw = keyword.strip().lower()
        mask = (
            df["Title"].str.lower().str.contains(kw, na=False) |
            df["Rule ID"].str.lower().str.contains(kw, na=False) |
            df["Description"].str.lower().str.contains(kw, na=False)
        )
        df = df[mask]

    st.markdown("---")

    # ── Stats
    total_raw = len(df_raw)
    total_filt = len(df)
    l1_count = len(df[df["Level"] == "Level 1"])
    l2_count = len(df[df["Level"] == "Level 2"])
    files_count = df_raw["Source File"].nunique() if "Source File" in df_raw.columns else 0

    st.markdown(f"""
    <div class="stat-grid">
      <div class="stat-card blue">
        <div class="stat-label">Total Aturan</div>
        <div class="stat-value">{total_raw:,}</div>
        <div class="stat-detail">dari {files_count} file PDF</div>
      </div>
      <div class="stat-card green">
        <div class="stat-label">Hasil Filter</div>
        <div class="stat-value">{total_filt:,}</div>
        <div class="stat-detail">aturan ditampilkan</div>
      </div>
      <div class="stat-card amber">
        <div class="stat-label">Level 1</div>
        <div class="stat-value">{l1_count:,}</div>
        <div class="stat-detail">aturan dasar</div>
      </div>
      <div class="stat-card purple">
        <div class="stat-label">Level 2</div>
        <div class="stat-value">{l2_count:,}</div>
        <div class="stat-detail">aturan lanjutan</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Tabs
    tab_table, tab_detail, tab_chart = st.tabs(["📋 Tabel Data", "🔍 Detail Aturan", "📊 Distribusi"])

    # ─── TAB 1: Table
    with tab_table:
        display_cols = [c for c in ["Rule ID", "Title", "Level", "Description", "Source File"] if c in df.columns]
        st.dataframe(
            df[display_cols].reset_index(drop=True),
            use_container_width=True,
            height=480,
            column_config={
                "Rule ID":     st.column_config.TextColumn("Rule ID", width=90),
                "Title":       st.column_config.TextColumn("Judul", width=280),
                "Level":       st.column_config.TextColumn("Level", width=90),
                "Description": st.column_config.TextColumn("Deskripsi", width=420),
                "Source File": st.column_config.TextColumn("File", width=160),
            },
            hide_index=True,
        )
        st.caption(f"Menampilkan {total_filt:,} dari {total_raw:,} total aturan")

    # ─── TAB 2: Detail
    with tab_detail:
        if len(df) == 0:
            st.markdown('<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-text">Tidak ada aturan yang cocok dengan filter saat ini.</div></div>', unsafe_allow_html=True)
        else:
            rule_options = df.apply(lambda r: f"{r['Rule ID']} — {r['Title'][:70]}", axis=1).tolist()
            selected_label = st.selectbox("Pilih aturan untuk dilihat detail:", rule_options, label_visibility="collapsed")
            sel_idx = rule_options.index(selected_label)
            row = df.iloc[sel_idx]

            level_tag_cls = {"Level 1": "tag-l1", "Level 2": "tag-l2"}.get(row["Level"], "tag-na")
            st.markdown(f"""
            <div class="rule-card">
              <div class="rule-id">{row['Rule ID']} &nbsp;<span class="tag {level_tag_cls}">{row['Level']}</span></div>
              <div class="rule-title">{row['Title']}</div>
              <div class="field-label">📄 Deskripsi</div>
              <div class="field-value">{row['Description']}</div>
              <div class="field-label">💡 Rasional</div>
              <div class="field-value">{row['Rationale']}</div>
              <div class="field-label">🔎 Audit</div>
              <div class="field-value">{row['Audit']}</div>
              <div class="field-label">🔧 Remediasi</div>
              <div class="field-value">{row['Remediation']}</div>
              <div class="field-label">📁 Sumber</div>
              <div class="field-value">{row.get('Source File','—')}</div>
            </div>
            """, unsafe_allow_html=True)

    # ─── TAB 3: Chart
    with tab_chart:
        c1, c2 = st.columns(2)

        with c1:
            st.markdown('<div class="section-head">Level Distribution</div>', unsafe_allow_html=True)
            level_counts = df["Level"].value_counts().reset_index()
            level_counts.columns = ["Level", "Jumlah"]
            st.bar_chart(level_counts.set_index("Level"), use_container_width=True, color="#3b82f6")

        with c2:
            st.markdown('<div class="section-head">Per File Source</div>', unsafe_allow_html=True)
            if "Source File" in df.columns:
                file_counts = df["Source File"].value_counts().reset_index()
                file_counts.columns = ["File", "Jumlah"]
                file_counts["File"] = file_counts["File"].str.replace(".pdf", "", regex=False).str[:25]
                st.bar_chart(file_counts.set_index("File"), use_container_width=True, color="#10b981")

        # Top rules by section completeness
        st.markdown('<div class="section-head" style="margin-top:1.5rem">Kelengkapan Bagian per Aturan</div>', unsafe_allow_html=True)
        completeness_cols = ["Description", "Rationale", "Audit", "Remediation"]
        df_temp = df.copy()
        df_temp["Skor Kelengkapan"] = df_temp[completeness_cols].apply(
            lambda row: sum(1 for v in row if v != "N/A"), axis=1
        )
        completeness_dist = df_temp["Skor Kelengkapan"].value_counts().sort_index().reset_index()
        completeness_dist.columns = ["Bagian Terisi", "Jumlah Aturan"]
        completeness_dist["Bagian Terisi"] = completeness_dist["Bagian Terisi"].astype(str) + " / 4"
        st.bar_chart(completeness_dist.set_index("Bagian Terisi"), use_container_width=True, color="#8b5cf6")

    # ── Export section
    st.markdown("---")
    st.markdown('<div class="section-head">💾 Export ke Excel</div>', unsafe_allow_html=True)

    exp_col1, exp_col2, exp_col3 = st.columns([2, 2, 3])

    with exp_col1:
        export_scope = st.radio(
            "Data yang diekspor:",
            ["Hasil filter saja", "Semua data (tanpa filter)"],
            horizontal=False,
        )

    with exp_col2:
        split_by_file = st.checkbox("Pisah per sheet/file", value=True)
        include_index = st.checkbox("Sertakan nomor baris", value=False)

    df_export = df if export_scope == "Hasil filter saja" else df_raw
    export_cols_valid = [c for c in export_cols if c in df_export.columns]

    with exp_col3:
        st.markdown(f"""
        <div style="background:#1a1f2e;border:1px solid #2a3147;border-radius:8px;padding:.9rem 1.1rem;margin-top:.2rem">
          <div style="font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Ringkasan Export</div>
          <div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-top:.3rem">{len(df_export):,} aturan</div>
          <div style="font-size:.75rem;color:#475569">{len(export_cols_valid)} kolom · {'Multi-sheet' if split_by_file else 'Single sheet'}</div>
        </div>
        """, unsafe_allow_html=True)

    # Build Excel in memory
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        if split_by_file and "Source File" in df_export.columns:
            for src_file, grp in df_export.groupby("Source File"):
                sheet_name = re.sub(r'[\\/*?:\[\]]', '_', src_file[:28].replace(".pdf", ""))
                grp[export_cols_valid].to_excel(writer, sheet_name=sheet_name, index=include_index)
        else:
            df_export[export_cols_valid].to_excel(writer, sheet_name="CIS_Rules", index=include_index)

    buf.seek(0)

    st.download_button(
        label=f"⬇️  Download Excel ({len(df_export):,} baris)",
        data=buf,
        file_name="CIS_Benchmark_Export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
    )

else:
    # Empty state
    st.markdown("""
    <div class="empty-state">
      <div class="empty-icon">🛡️</div>
      <div class="empty-text">
        Upload satu atau lebih PDF CIS Benchmark di atas,<br>
        lalu klik <b>Mulai Ekstraksi</b> untuk memulai.
      </div>
    </div>
    """, unsafe_allow_html=True)
