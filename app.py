import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import plotly.express as px
from concurrent.futures import ProcessPoolExecutor

# --- KONFIGURASI REGEX & MAP (LOGIKA ASLI LO - TIDAK DISENTUH) ---
RE_HEADER = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*)')
RE_SECTION = re.compile(r'^(Profile Applicability|Description|Rationale|Impact|Audit|Remediation|Default Value|References):?', re.IGNORECASE)
RE_CLEAN = re.compile(r'(Page \d+|Internal Only - General|P a g e \| \d+|CIS (?:Microsoft|Windows|Debian|Ubuntu).*?Benchmark)', re.IGNORECASE)
SECTION_MAP = {
    "profile applicability": "Level", "description": "Description",
    "rationale": "Rationale", "impact": "Impact", "audit": "Audit",
    "remediation": "Remediation", "default value": "Default Value",
    "references": "References"
}

def clean_fast(text_list):
    if not text_list: return "N/A"
    full = " ".join(text_list)
    full = RE_CLEAN.sub('', full)
    return " ".join(full.split()).strip() or "N/A"

# --- WORKER FUNCTION (LOGIKA ASLI LO - TIDAK DISENTUH) ---
def process_page_chunk(pdf_bytes, start_page, end_page, master_toc_ids):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunk_results = []
    current_rule = None
    
    for p in range(start_page, end_page):
        lines = doc[p].get_text("text").split('\n')
        for line in lines:
            line_s = line.strip()
            if not line_s: continue
            if line_s[0].isdigit():
                header_match = RE_HEADER.search(line_s)
                if header_match:
                    rid = header_match.group(1)
                    if rid in master_toc_ids:
                        if current_rule: chunk_results.append(current_rule)
                        current_rule = {
                            "Rule ID": rid, "Title": [header_match.group(2)],
                            "Level": [], "Description": [], "Rationale": [],
                            "Impact": [], "Audit": [], "Remediation": [],
                            "Default Value": [], "References": [], "current_key": "Title"
                        }
                        continue
            if current_rule:
                s_match = RE_SECTION.match(line_s)
                if s_match:
                    key_lower = s_match.group(1).lower()
                    current_rule["current_key"] = SECTION_MAP.get(key_lower, "Description")
                    content = RE_SECTION.sub('', line_s).strip()
                    if content: current_rule[current_rule["current_key"]].append(content)
                else:
                    current_rule[current_rule["current_key"]].append(line_s)
    if current_rule: chunk_results.append(current_rule)
    doc.close()
    return chunk_results

# --- ENGINE (LOGIKA ASLI LO - TIDAK DISENTUH) ---
def run_titan_engine(pdf_bytes, cpu_cores):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    
    master_toc = {}
    for i in range(min(40, total_pages)):
        lines = doc[i].get_text("text").split('\n')
        for line in lines:
            if "...." in line:
                match = re.search(r'^(\d+(?:\.\d+)+)\s+(.*?)\.*?\s+(\d+)$', line.strip())
                if match: master_toc[match.group(1)] = int(match.group(3))
    doc.close()

    if not master_toc: return None

    chunk_size = total_pages // cpu_cores
    results = []
    with ProcessPoolExecutor(max_workers=cpu_cores) as executor:
        futures = []
        for i in range(cpu_cores):
            start = i * chunk_size
            end = total_pages if i == cpu_cores - 1 else (i + 1) * chunk_size
            futures.append(executor.submit(process_page_chunk, pdf_bytes, start, end, set(master_toc.keys())))
        
        for f in futures:
            results.extend(f.result())

    df = pl.DataFrame([{k: clean_fast(v) if isinstance(v, list) else v for k, v in r.items() if k != "current_key"} for r in results])
    return df.unique(subset=["Rule ID"]).sort("Rule ID")

# --- NEW FRONTEND FEATURES (ASU MODE) ---
def main():
    st.set_page_config(page_title="Titan CIS Extractor", layout="wide", initial_sidebar_state="expanded")
    
    # Custom CSS buat gaya Enterprise
    st.markdown("""
        <style>
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        div[data-testid="stStatusWidget"] { border: 1px solid #00d4ff; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🚀 Titan Engine: CIS Benchmark Extractor")
    st.markdown("---")

    with st.sidebar:
        st.header("⚙️ Engine Settings")
        cores = st.slider("CPU Cores (Parallelism)", 1, os.cpu_count(), 4)
        st.info(f"Titan Engine ready with {cores} cores.")
        st.divider()
        st.markdown("### About")
        st.caption("High-performance extraction for CIS Benchmarks using PyMuPDF, Multiprocessing, and Polars.")

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        
        if st.button("⚡ Start Extraction", type="primary", use_container_width=True):
            with st.status("Titan Engine is parsing your PDF...", expanded=True) as status:
                st.write("Initializing Multiprocessing...")
                df_result = run_titan_engine(file_bytes, cores)
                
                if df_result is not None:
                    status.update(label="Extraction Complete!", state="complete", expanded=False)
                    st.session_state['extracted_data'] = df_result
                else:
                    status.update(label="Extraction Failed!", state="error")
                    st.error("Daftar Isi tidak ditemukan. Pastikan ini dokumen asli CIS Benchmark.")

    # Tampilkan dashboard jika data sudah ada di session state
    if 'extracted_data' in st.session_state:
        df = st.session_state['extracted_data']
        df_pd = df.to_pandas()

        st.success(f"Berhasil mengekstrak {len(df)} rules!")

        # 1. Metrics Bar
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Rules", len(df_pd))
        with m2:
            l1_count = len(df_pd[df_pd['Level'].str.contains('L1|Level 1', na=False, case=False)])
            st.metric("Level 1 (L1)", l1_count)
        with m3:
            l2_count = len(df_pd[df_pd['Level'].str.contains('L2|Level 2', na=False, case=False)])
            st.metric("Level 2 (L2)", l2_count)
        with m4:
            cat_count = df_pd['Rule ID'].str.split('.').str[0].nunique()
            st.metric("Main Categories", cat_count)

        # 2. Charts Row
        st.markdown("### 📊 Compliance Analytics")
        c1, c2 = st.columns(2)
        
        with c1:
            fig_pie = px.pie(df_pd, names='Level', title='Controls by Level Distribution', 
                             hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with c2:
            df_pd['Category'] = df_pd['Rule ID'].str.split('.').str[0]
            cat_df = df_pd.groupby('Category').size().reset_index(name='count')
            fig_bar = px.bar(cat_df, x='Category', y='count', title='Rules per Category',
                             labels={'Category': 'Rule Category', 'count': 'Number of Rules'},
                             color='count', color_continuous_scale='Viridis')
            st.plotly_chart(fig_bar, use_container_width=True)

        # 3. Interactive Search Table
        st.markdown("### 🔍 Search & Filter Data")
        search_query = st.text_input("Cari kata kunci (misal: 'password', 'audit', 'registry')...", "")
        
        if search_query:
            filtered_df = df_pd[df_pd.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)]
        else:
            filtered_df = df_pd

        st.dataframe(filtered_df, use_container_width=True, height=450)

        # 4. Multi-format Export
        st.markdown("### 📥 Export Results")
        ex1, ex2, ex3 = st.columns(3)
        
        # Excel
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
            filtered_df.to_excel(writer, index=False, sheet_name='CIS_Results')
        with ex1:
            st.download_button(label="Download Excel (.xlsx)", data=output_excel.getvalue(),
                               file_name=f"TITAN_{uploaded_file.name.replace('.pdf', '.xlsx')}",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        
        # CSV
        csv_data = filtered_df.to_csv(index=False).encode('utf-8')
        with ex2:
            st.download_button(label="Download CSV (.csv)", data=csv_data,
                               file_name=f"TITAN_{uploaded_file.name.replace('.pdf', '.csv')}",
                               mime="text/csv", use_container_width=True)
            
        # JSON (Buat Integrasi GRC)
        json_data = filtered_df.to_json(orient='records')
        with ex3:
            st.download_button(label="Download JSON (.json)", data=json_data,
                               file_name=f"TITAN_{uploaded_file.name.replace('.pdf', '.json')}",
                               mime="application/json", use_container_width=True)

if __name__ == "__main__":
    import pandas as pd
    main()
