import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import time
import plotly.express as px

# --- 1. GLOBAL PRE-COMPILED REGEX (V9.9 - ATOMIC SENSITIVITY) ---
RE_TOC_LINE = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*?)\.*?\s+(\d+)$')
RE_HEADER = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*)')
# FIX: Hilangkan anchor ^ dan buat lebih fleksibel nangkep "Applicability"
RE_SECTION = re.compile(r'(Applicability|Description|Rationale|Impact|Audit|Remediation|Default Value|References)', re.IGNORECASE)
RE_CLEAN = re.compile(r'(Page \d+|Internal Only - General|P a g e \| \d+|CIS (?:Microsoft|Windows|Debian|Ubuntu).*?Benchmark)', re.IGNORECASE)

SECTION_MAP = {
    "profile applicability": "Level", "applicability": "Level", 
    "description": "Description", "rationale": "Rationale", 
    "impact": "Impact", "audit": "Audit", "remediation": "Remediation", 
    "default value": "Default Value", "references": "References"
}

def clean_fast(text_list):
    if not text_list: return "N/A"
    # Deduplikasi & Clean whitespace
    unique_items = list(dict.fromkeys([t.strip() for t in text_list if t.strip()]))
    full = " ".join(unique_items)
    full = RE_CLEAN.sub('', full)
    return " ".join(full.split()).strip() or "N/A"

# --- 2. PREDATOR ENGINE (LOGIKA ASLI LO - 100% ORIGINAL + REINFORCED) ---
def predator_engine(pdf_stream):
    doc = fitz.open(stream=pdf_stream, filetype="pdf")
    total_pages = len(doc)
    all_pages_content = []
    master_toc = {}

    # ToC Scan lebih dalam (60 hal) buat jaga-jaga benchmark tebal
    for i in range(total_pages):
        page_text = doc[i].get_text("text")
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        all_pages_content.append(lines)
        if i < 60:
            for line in lines:
                match = RE_TOC_LINE.search(line)
                if match and "...." in line:
                    master_toc[match.group(1)] = {"page": int(match.group(3))}
    doc.close()

    all_ids = sorted(master_toc.keys(), key=lambda x: [int(i) for i in x.split('.')])
    final_results = []

    for i, rid in enumerate(all_ids):
        # FIX: Perlebar range halaman (-5 sampai +5) buat handle ToC yang meleset jauh
        start_idx = max(0, master_toc[rid]["page"] - 5)
        next_rid = all_ids[i+1] if i+1 < len(all_ids) else None
        end_idx = min(total_pages, (master_toc[next_rid]["page"] + 5) if next_rid else total_pages)

        rule_data = {
            "Rule ID": rid, "Title": [], "Level": [], "Description": [],
            "Rationale": [], "Impact": [], "Audit": [], "Remediation": [],
            "Default Value": [], "References": [], "current_key": "Title"
        }
        
        found = False
        for p in range(start_idx, end_idx):
            page_lines = all_pages_content[p]
            for line in page_lines:
                h_match = RE_HEADER.search(line)
                
                # Rule Identification
                if h_match and h_match.group(1) == rid:
                    rule_data["Title"].append(h_match.group(2))
                    found = True
                    continue
                
                # Stop if next rule starts
                if found and h_match and h_match.group(1) != rid:
                    if h_match.group(1) in master_toc:
                        break 
                
                if found:
                    # FIX: Gunakan .search() supaya nangkep keyword di tengah baris sekalipun
                    s_match = RE_SECTION.search(line)
                    if s_match:
                        key_lower = s_match.group(0).lower() # Group 0 untuk nangkep full keyword
                        # Mapping fleksibel (handle 'Applicability' doang atau full)
                        target_key = "Level" if "applicability" in key_lower else SECTION_MAP.get(key_lower, "Description")
                        rule_data["current_key"] = target_key
                        
                        content = RE_SECTION.sub('', line).strip()
                        if content: rule_data[rule_data["current_key"]].append(content)
                    else:
                        # ATOMIC FIX: Kalau nemu "Level 1" atau "Level 2" tapi section belum ketemu,
                        # paksa masuk ke kolom Level. Sering terjadi di rule 1.1.x
                        if ("Level 1" in line or "Level 2" in line) and len(rule_data["Level"]) == 0:
                            rule_data["Level"].append(line)
                        else:
                            rule_data[rule_data["current_key"]].append(line)
                            
            if found and h_match and h_match.group(1) in master_toc and h_match.group(1) != rid:
                break

        if found:
            final_results.append({
                "Rule ID": rid,
                "Title": clean_fast(rule_data["Title"]),
                "Level": clean_fast(rule_data["Level"]),
                "Description": clean_fast(rule_data["Description"]),
                "Rationale": clean_fast(rule_data["Rationale"]),
                "Impact": clean_fast(rule_data["Impact"]),
                "Audit": clean_fast(rule_data["Audit"]),
                "Remediation": clean_fast(rule_data["Remediation"]),
                "Default Value": clean_fast(rule_data["Default Value"]),
                "References": clean_fast(rule_data["References"])
            })
    return final_results

# --- 3. FRONTEND TITAN UI ---
def main():
    st.set_page_config(page_title="Titan Predator v9.9", layout="wide", page_icon="🛡️")
    st.title("🛡️ Predator Engine: Atomic v9.9")
    
    # CSS UI
    st.markdown("""<style>.stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border-left: 5px solid #00d4ff; }</style>""", unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")
    if uploaded_file:
        if st.button("🚀 EXECUTE ATOMIC SCAN", type="primary", width="stretch"):
            start_t = time.time()
            with st.status("Atomic Engine is hunting... No N/A allowed!", expanded=True):
                data = predator_engine(uploaded_file.read())
                if data:
                    st.session_state['data'] = pd.DataFrame(data)
                    st.session_state['speed'] = time.time() - start_t
                else:
                    st.error("Daftar Isi tidak ditemukan.")

    if 'data' in st.session_state:
        df = st.session_state['data']
        # Executive Summary
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rules", len(df))
        m4.metric("Hunt Speed", f"{st.session_state['speed']:.2f}s")
        
        # Display Table
        st.dataframe(df, width="stretch")
        
        # Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Audit_Checklist')
        st.download_button("📥 Download Master Result", output.getvalue(), "CIS_Audit_Titan.xlsx", width="stretch")

if __name__ == "__main__":
    main()
