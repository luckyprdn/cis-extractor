import streamlit as st
import fitz
import polars as pl
import pandas as pd
import plotly.express as px
import re
import io
import os
from concurrent.futures import ProcessPoolExecutor

# --- 1. GLOBAL CONFIGURATION & REGEX ---
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

# --- 2. BACKEND WORKER (TITAN ENGINE) ---
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

def run_titan_engine(pdf_bytes, cpu_cores):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    
    # Quick ToC Scan
    master_toc = {}
    for i in range(min(40, total_pages)):
        lines = doc[i].get_text("text").split('\n')
        for line in lines:
            if "...." in line:
                match = re.search(r'^(\d+(?:\.\d+)+)\s+(.*?)\.*?\s+(\d+)$', line.strip())
                if match: master_toc[match.group(1)] = int(match.group(3))
    doc.close()

    if not master_toc: return None

    # Parallel Processing
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

    # Polars Processing
    raw_processed = [{k: clean_fast(v) if isinstance(v, list) else v for k, v in r.items() if k != "current_key"} for r in results]
    if not raw_processed: return None
    
    return pl.DataFrame(raw_processed).unique(subset=["Rule ID"]).sort("Rule ID")

# --- 3. FRONTEND UI (STREAMLIT) ---
def main():
    st.set_page_config(page_title="Titan CIS Analyzer", layout="wide", initial_sidebar_state="expanded")
    
    # CSS UI
    st.markdown("""
        <style>
        .main { background-color: #f5f7f9; }
        .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Titan CIS Analyzer")
    st.subheader("Enterprise-Grade Policy & Benchmark Extractor")

    with st.sidebar:
        st.header("⚙️ Engine Configuration")
        cores = st.slider("Parallel Processing Cores", 1, os.cpu_count() or 1, 4)
        st.divider()
        st.info("Titan Engine v9.1 Active")

    uploaded_files = st.file_uploader("Upload CIS Benchmark PDFs", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        if st.button("⚡ Run Titan Extraction", type="primary"):
            all_dfs = []
            
            with st.status("Running Titan Parallel Engine...", expanded=True) as status:
                for uploaded_file in uploaded_files:
                    st.write(f"Processing: {uploaded_file.name}")
                    file_bytes = uploaded_file.read()
                    df_result = run_titan_engine(file_bytes, cores)
                    
                    if df_result is not None:
                        df_pd = df_result.to_pandas()
                        df_pd['Source File'] = uploaded_file.name
                        all_dfs.append(df_pd)
                
                if all_dfs:
                    master_df = pd.concat(all_dfs, ignore_index=True)
                    st.session_state['master_df'] = master_df
                    status.update(label="Extraction Success!", state="complete")
                else:
                    st.error("No data extracted. Pastikan PDF adalah CIS Benchmark asli.")

    # --- DASHBOARD AREA ---
    if 'master_df' in st.session_state:
        df = st.session_state['master_df']
        st.divider()
        
        # 1. Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rules", len(df))
        m2.metric("L1 Controls", len(df[df['Level'].str.contains('Level 1', na=False)]))
        m3.metric("L2 Controls", len(df[df['Level'].str.contains('Level 2', na=False)]))
        m4.metric("Files", df['Source File'].nunique())

        # 2. Charts
        c1, c2 = st.columns(2)
        with c1:
            fig_pie = px.pie(df, names='Level', title='Controls Level Distribution', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            df['Category'] = df['Rule ID'].str.split('.').str[0]
            fig_bar = px.bar(df.groupby('Category').size().reset_index(name='count'), 
                             x='Category', y='count', title='Rules by Main Category')
            st.plotly_chart(fig_bar, use_container_width=True)

        # 3. Explorer
        st.markdown("### 🔍 Data Explorer")
        search = st.text_input("Filter rules...", "")
        if search:
            df_display = df[df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
        else:
            df_display = df
        st.dataframe(df_display, use_container_width=True)

        # 4. Export
        st.markdown("### 💾 Export")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_display.to_excel(writer, index=False, sheet_name='CIS_Master')
        
        st.download_button("Download Excel", data=output.getvalue(), 
                           file_name="CIS_Master_Extract.xlsx", 
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    main()
