import streamlit as st
import fitz
import polars as pl
import re
import io
import os
from concurrent.futures import ProcessPoolExecutor

# --- KONFIGURASI REGEX & MAP (PRE-COMPILED) ---
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

# --- WORKER FUNCTION ---
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

# --- ENGINE ---
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
    df = pl.DataFrame([{k: clean_fast(v) if isinstance(v, list) else v for k, v in r.items() if k != "current_key"} for r in results])
    return df.unique(subset=["Rule ID"]).sort("Rule ID")

# --- STREAMLIT UI ---
def main():
    st.set_page_config(page_title="Titan CIS Extractor", layout="wide")
    st.title("🚀 Titan Engine: CIS Benchmark Extractor")
    st.markdown("Extractor PDF ke Excel dengan performa tinggi menggunakan Multiprocessing & Polars.")

    with st.sidebar:
        st.header("Settings")
        cores = st.slider("CPU Cores (Parallelism)", 1, os.cpu_count(), 4)
        st.info(f"Menggunakan {cores} core untuk pemrosesan.")

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        
        if st.button("Start Extraction"):
            with st.status("Processing PDF...", expanded=True) as status:
                st.write("Initializing Titan Engine...")
                df_result = run_titan_engine(file_bytes, cores)
                
                if df_result is not None:
                    status.update(label="Extraction Complete!", state="complete", expanded=False)
                    st.success(f"Berhasil mengekstrak {len(df_result)} rules.")
                    
                    # Preview
                    st.dataframe(df_result.to_pandas(), use_container_width=True)
                    
                    # Export to Excel (Memory Buffer)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_result.to_pandas().to_excel(writer, index=False, sheet_name='CIS_Results')
                    
                    st.download_button(
                        label="📥 Download Excel Result",
                        data=output.getvalue(),
                        file_name=f"TITAN_{uploaded_file.name.replace('.pdf', '.xlsx')}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    status.update(label="Extraction Failed!", state="error")
                    st.error("Daftar Isi tidak ditemukan. Pastikan file adalah dokumen asli CIS Benchmark.")

if __name__ == "__main__":
    # Penting: Import pandas di sini untuk ExcelWriter
    import pandas as pd
    main()
