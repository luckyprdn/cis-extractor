import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import time
import plotly.express as px

# --- 1. GLOBAL PRE-COMPILED REGEX (V9.8 - LEBIH AGRESIF) ---
RE_TOC_LINE = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*?)\.*?\s+(\d+)$')
RE_HEADER = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*)')
# FIX: Hapus '^' supaya bisa nangkep section meskipun ada bullet/spasi di depannya
RE_SECTION = re.compile(r'(Profile Applicability|Description|Rationale|Impact|Audit|Remediation|Default Value|References):?', re.IGNORECASE)
RE_CLEAN = re.compile(r'(Page \d+|Internal Only - General|P a g e \| \d+|CIS (?:Microsoft|Windows|Debian|Ubuntu).*?Benchmark)', re.IGNORECASE)

SECTION_MAP = {
    "profile applicability": "Level", "description": "Description",
    "rationale": "Rationale", "impact": "Impact", "audit": "Audit",
    "remediation": "Remediation", "default value": "Default Value",
    "references": "References"
}

def clean_fast(text_list):
    if not text_list: return "N/A"
    unique_items = list(dict.fromkeys([t.strip() for t in text_list if t.strip()]))
    full = " ".join(unique_items)
    full = RE_CLEAN.sub('', full)
    return " ".join(full.split()).strip() or "N/A"

# --- 2. PREDATOR ENGINE (V9.8 - DEEP HUNTER LOGIC) ---
def predator_engine(pdf_stream):
    doc = fitz.open(stream=pdf_stream, filetype="pdf")
    total_pages = len(doc)
    all_pages_content = []
    master_toc = {}

    # Scan ToC lebih dalam (sampai hal 50) buat pastiin ID gak ada yang lewat
    for i in range(total_pages):
        page_text = doc[i].get_text("text")
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        all_pages_content.append(lines)
        if i < 50:
            for line in lines:
                match = RE_TOC_LINE.search(line)
                if match and "...." in line:
                    master_toc[match.group(1)] = {"page": int(match.group(3))}
    doc.close()

    all_ids = sorted(master_toc.keys(), key=lambda x: [int(i) for i in x.split('.')])
    final_results = []

    for i, rid in enumerate(all_ids):
        # Buffer halaman diperlebar biar gak "bolong" gara-gara offset PDF
        start_idx = max(0, master_toc[rid]["page"] - 3) 
        next_rid = all_ids[i+1] if i+1 < len(all_ids) else None
        end_idx = min(total_pages, (master_toc[next_rid]["page"] + 2) if next_rid else total_pages)

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
                
                if h_match and h_match.group(1) == rid:
                    rule_data["Title"].append(h_match.group(2))
                    found = True
                    continue
                
                if found and h_match and h_match.group(1) != rid:
                    if h_match.group(1) in master_toc:
                        break 
                
                if found:
                    s_match = RE_SECTION.search(line) # Pakai search, bukan match
                    if s_match:
                        key_lower = s_match.group(1).lower()
                        rule_data["current_key"] = SECTION_MAP.get(key_lower, "Description")
                        content = RE_SECTION.sub('', line).strip()
                        if content: rule_data[rule_data["current_key"]].append(content)
                    else:
                        # Fuzzy Check: Kalau nemu "Level 1" tapi belum masuk section manapun, 
                        # kemungkinan besar ini data applicability yang nyempil
                        if rule_data["current_key"] == "Title" and ("Level 1" in line or "Level 2" in line):
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

# --- 3. FRONTEND UI (TITAN PRO MODE) ---
# ... (Sisanya sama kayak kode frontend sebelumnya, pakai st.session_state dan tabs) ...
def main():
    st.set_page_config(page_title="Titan Predator v9.8", layout="wide", page_icon="🛡️")
    st.title("🛡️ Predator Engine: Deep Hunter v9.8")
    
    # CSS UI
    st.markdown("""<style>.stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border-left: 5px solid #00d4ff; }</style>""", unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")
    if uploaded_file:
        if st.button("🚀 EXECUTE DEEP SCAN", type="primary", use_container_width=True):
            start_t = time.time()
            with st.status("Engine is hunting... No rules left behind!", expanded=True):
                data = predator_engine(uploaded_file.read())
                if data:
                    st.session_state['data'] = pd.DataFrame(data)
                    st.session_state['speed'] = time.time() - start_t
                else:
                    st.error("Daftar Isi tidak ditemukan.")

    if 'data' in st.session_state:
        df = st.session_state['data']
        # Dashboard Analytics & Table View
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rules", len(df))
        m4.metric("Hunt Speed", f"{st.session_state['speed']:.2f}s")
        st.dataframe(df, use_container_width=True)
        
        # Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Audit_Checklist')
        st.download_button("📥 Download Result", output.getvalue(), "CIS_Audit.xlsx", use_container_width=True)

if __name__ == "__main__":
    main()
