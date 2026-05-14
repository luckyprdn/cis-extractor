import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
from concurrent.futures import ProcessPoolExecutor

# --- KONFIGURASI REGEX & MAP ---
RE_TOC = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*?)\.*?\s+(\d+)$')
RE_HEADER_STRICT = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*)')
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

# --- FASE 1: WORKER FAST SCAN (PASS 1) ---
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
                header_match = RE_HEADER_STRICT.search(line_s)
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

# --- FASE 2: RECURSIVE RESCUE SCAN (PASS 2 - ANTI GAP) ---
def build_fuzzy_regex(rule_id):
    # Mengizinkan spasi berlebih atau karakter aneh antar titik untuk OCR Tolerance
    escaped_id = rule_id.replace('.', r'\s*\.\s*')
    return re.compile(rf'^({escaped_id})\s+(.*)', re.IGNORECASE)

def rescue_scan(doc, missing_id, start_p, end_p):
    """
    Melakukan scan berulang dengan Fuzzy Regex dan Heading Structure Detection.
    Berperan sebagai OCR reinforcement proxy untuk layout PDF yang rusak.
    """
    fuzzy_re = build_fuzzy_regex(missing_id)
    rescued_rule = None
    
    for p in range(max(0, start_p), min(len(doc), end_p + 1)):
        # Menggunakan "blocks" (Structural Detection) untuk mengatasi teks yang tersembunyi
        blocks = doc[p].get_text("blocks")
        blocks.sort(key=lambda b: b[1]) # Sort by Y coordinate
        
        for b in blocks:
            text_block = b[4].strip()
            lines = text_block.split('\n')
            
            for line in lines:
                line_s = line.strip()
                if not line_s: continue
                
                # Coba Fuzzy Match
                h_match = fuzzy_re.search(line_s) or RE_HEADER_STRICT.search(line_s)
                
                if h_match and h_match.group(1).replace(' ', '') == missing_id:
                    if rescued_rule: return rescued_rule # Stop if another rule starts
                    rescued_rule = {
                        "Rule ID": missing_id, "Title": [h_match.group(2)],
                        "Level": [], "Description": [], "Rationale": [],
                        "Impact": [], "Audit": [], "Remediation": [],
                        "Default Value": [], "References": [], "current_key": "Title"
                    }
                    continue
                
                if rescued_rule:
                    # Deteksi perpindahan ID untuk memberhentikan rescue scan
                    if RE_HEADER_STRICT.match(line_s):
                        potential_id = RE_HEADER_STRICT.match(line_s).group(1)
                        if potential_id != missing_id: return rescued_rule
                    
                    s_match = RE_SECTION.match(line_s)
                    if s_match:
                        key_lower = s_match.group(1).lower()
                        rescued_rule["current_key"] = SECTION_MAP.get(key_lower, "Description")
                        content = RE_SECTION.sub('', line_s).strip()
                        if content: rescued_rule[rescued_rule["current_key"]].append(content)
                    else:
                        rescued_rule[rescued_rule["current_key"]].append(line_s)
                        
    return rescued_rule

# --- ENGINE ORCHESTRATOR ---
def run_titan_engine(pdf_bytes, cpu_cores, status_placeholder):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    
    # 1. GROUND TRUTH (ToC SEQUENCE AWARENESS)
    status_placeholder.write("⚙️ Membangun Sequence Ground Truth dari ToC...")
    master_toc = {}
    ordered_ids = []
    
    for i in range(min(50, total_pages)):
        lines = doc[i].get_text("text").split('\n')
        for line in lines:
            if "...." in line:
                match = RE_TOC.search(line.strip())
                if match:
                    rid, rtitle, rpage = match.groups()
                    master_toc[rid] = int(rpage)
                    ordered_ids.append(rid)
    
    if not master_toc:
        doc.close()
        return None, None, None

    # 2. PASS 1: PARALLEL SCAN
    status_placeholder.write("⚡ Eksekusi Multi-Pass (Pass 1: Parallel High-Speed)...")
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

    extracted_ids = {r["Rule ID"] for r in results}
    
    # 3. GAP DETECTION & INTEGRITY VALIDATION
    missing_ids = [rid for rid in ordered_ids if rid not in extracted_ids]
    rescued_results = []
    
    if missing_ids:
        status_placeholder.write(f"⚠️ Gap Numbering Terdeteksi: {len(missing_ids)} rules missing. Memulai Recursive Rescanning...")
        
        # 4. PASS 2: RECURSIVE RESCUE SCAN
        for missing_id in missing_ids:
            # Cari batas halaman dari ToC
            idx = ordered_ids.index(missing_id)
            start_p = master_toc[missing_id] - 3  # Buffer mundur
            end_p = master_toc[ordered_ids[idx+1]] + 2 if idx + 1 < len(ordered_ids) else total_pages
            
            rescued_rule = rescue_scan(doc, missing_id, start_p, end_p)
            if rescued_rule:
                rescued_results.append(rescued_rule)

    doc.close()
    
    # Kumpulkan Semua Data
    all_results = results + rescued_results
    
    # Pembersihan via Polars
    df = pl.DataFrame([{k: clean_fast(v) if isinstance(v, list) else v for k, v in r.items() if k != "current_key"} for r in all_results])
    df_final = df.unique(subset=["Rule ID"]).sort("Rule ID")
    
    # FINAL INTEGRITY CHECK
    final_extracted_ids = set(df_final["Rule ID"].to_list())
    final_missing = [rid for rid in ordered_ids if rid not in final_extracted_ids]
    status_integrity = "COMPLETE" if not final_missing else "INCOMPLETE"
    
    return df_final, status_integrity, final_missing

# --- STREAMLIT UI ---
def main():
    st.set_page_config(page_title="Titan CIS Extractor (Optimus Build)", layout="wide")
    st.title("🛡️ Titan Engine: Optimus Build")
    st.markdown("Dilengkapi dengan **Anti-Gap Logic**, **Recursive Rescanning**, dan **Integrity Validation**.")

    with st.sidebar:
        st.header("Konfigurasi Sistem")
        cores = st.slider("CPU Cores (Parallelism)", 1, os.cpu_count(), 4)
        st.info(f"Hardware dialokasikan: {cores} Cores.")

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        
        if st.button("🚀 Start Extraction with Anti-Gap Logic", type="primary"):
            with st.status("Engine Menginisialisasi...", expanded=True) as status:
                status_placeholder = st.empty()
                df_result, integrity, missing = run_titan_engine(file_bytes, cores, status_placeholder)
                
                if df_result is not None:
                    if integrity == "COMPLETE":
                        status.update(label="Validasi Berhasil: 100% Sequence Lengkap!", state="complete", expanded=False)
                        st.success(f"Berhasil mengekstrak seluruh {len(df_result)} rules tanpa gap.")
                    else:
                        status.update(label=f"Peringatan: Ekstraksi Selesai dengan Status INCOMPLETE", state="warning", expanded=True)
                        st.warning(f"Berhasil mengekstrak {len(df_result)} rules. Namun, {len(missing)} rules masih gagal dipulihkan setelah rescanning.")
                        st.error(f"Missing Sections List (Needs Manual Review): {', '.join(missing)}")
                    
                    st.dataframe(df_result.to_pandas(), use_container_width=True)
                    
                    # Export Data
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_result.to_pandas().to_excel(writer, index=False, sheet_name='CIS_Results')
                    
                    st.download_button(
                        label="📥 Download Excel Result",
                        data=output.getvalue(),
                        file_name=f"TITAN_OPTIMUS_{uploaded_file.name.replace('.pdf', '.xlsx')}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    status.update(label="Kegagalan Sistem Parsing", state="error")
                    st.error("Daftar Isi tidak ditemukan atau format PDF rusak.")

if __name__ == "__main__":
    main()
