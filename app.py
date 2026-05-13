import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import time
import plotly.express as px

# --- 1. GLOBAL PRE-COMPILED REGEX (LOGIKA ASLI LO - TIDAK DISENTUH) ---
RE_TOC_LINE = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*?)\.*?\s+(\d+)$')
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
    unique_items = list(dict.fromkeys([t.strip() for t in text_list if t.strip()]))
    full = " ".join(unique_items)
    full = RE_CLEAN.sub('', full)
    return " ".join(full.split()).strip() or "N/A"

# --- 2. PREDATOR ENGINE (LOGIKA ASLI LO - 100% ORIGINAL) ---
def predator_engine(pdf_stream):
    doc = fitz.open(stream=pdf_stream, filetype="pdf")
    total_pages = len(doc)
    all_pages_content = []
    master_toc = {}

    for i in range(total_pages):
        page_text = doc[i].get_text("text")
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        all_pages_content.append(lines)
        if i < 25:
            for line in lines:
                match = RE_TOC_LINE.search(line)
                if match and "...." in line:
                    master_toc[match.group(1)] = {"page": int(match.group(3))}
    doc.close()

    all_ids = sorted(master_toc.keys(), key=lambda x: [int(i) for i in x.split('.')])
    final_results = []

    for i, rid in enumerate(all_ids):
        start_idx = max(0, master_toc[rid]["page"] - 2)
        next_rid = all_ids[i+1] if i+1 < len(all_ids) else None
        end_idx = min(total_pages, master_toc[next_rid]["page"] + 1 if next_rid else total_pages)

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
                    s_match = RE_SECTION.match(line)
                    if s_match:
                        key_lower = s_match.group(1).lower()
                        rule_data["current_key"] = SECTION_MAP.get(key_lower, "Description")
                        content = RE_SECTION.sub('', line).strip()
                        if content: rule_data[rule_data["current_key"]].append(content)
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

# --- 3. FRONTEND UI (MULTI-UPLOAD & COMPARE MODE) ---
def main():
    st.set_page_config(page_title="Predator Compare Pro", layout="wide", page_icon="🛡️")
    
    st.markdown("""
        <style>
        .stApp { background-color: #f4f7f9; }
        .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e6ed; }
        .stButton>button { border-radius: 8px; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Predator Engine: Multi-Upload & Compare")
    st.caption("IT Governance PNM - Benchmark Comparison Suite")

    with st.sidebar:
        st.header("Control Center")
        st.success("Predator v8.7 Ready")
        st.divider()
        st.info("Comparison Mode: Based on Rule Title")
        if st.button("Clear Session"):
            for key in st.session_state.keys():
                del st.session_state[key]
            st.rerun()

    # MULTI UPLOAD
    uploaded_files = st.file_uploader("Upload CIS Benchmark PDFs (Bisa pilih banyak file)", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        if st.button("🚀 EXECUTE MULTI-SCAN & COMPARE", type="primary"):
            all_data = []
            with st.status("Engine is hunting through multiple files...", expanded=True) as status:
                for uploaded_file in uploaded_files:
                    st.write(f"Scanning: {uploaded_file.name}...")
                    file_bytes = uploaded_file.read()
                    extracted = predator_engine(file_bytes)
                    if extracted:
                        df_tmp = pd.DataFrame(extracted)
                        df_tmp['Source_File'] = uploaded_file.name # Tag sumber file
                        all_data.append(df_tmp)
                
                if all_data:
                    master_df = pd.concat(all_data, ignore_index=True)
                    st.session_state['master_data'] = master_df
                    status.update(label="All targets neutralized!", state="complete")
                else:
                    st.error("No data extracted from the uploaded files.")

    # --- ANALYSIS DASHBOARD ---
    if 'master_data' in st.session_state:
        df = st.session_state['master_data']
        total_files = df['Source_File'].nunique()
        
        st.divider()
        
        # 1. Comparison Logic (Set Theory)
        # Hitung berapa kali judul muncul di file yang berbeda
        title_counts = df.groupby('Title')['Source_File'].nunique().reset_index()
        title_counts.columns = ['Title', 'File_Count']
        
        # Merge back ke df utama
        df_analysis = df.merge(title_counts, on='Title')
        
        # COMMON RULES: Muncul di SEMUA file yang di-upload
        common_df = df_analysis[df_analysis['File_Count'] == total_files].drop_duplicates(subset=['Title'])
        
        # SPECIFIC RULES: Cuma muncul di SATU file tertentu
        specific_df = df_analysis[df_analysis['File_Count'] == 1]

        # UI Tabs
        tab_sum, tab_common, tab_specific, tab_raw = st.tabs(["📊 Summary", "🔗 Common Rules", "🎯 Specific Rules", "📋 Raw Data"])

        with tab_sum:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Files", total_files)
            c2.metric("Common Rules (Global)", len(common_df))
            c3.metric("Specific Rules (Unique)", len(specific_df))
            
            st.write("### Rules Distribution per File")
            dist_df = df.groupby('Source_File').size().reset_index(name='Rule Count')
            fig = px.bar(dist_df, x='Source_File', y='Rule Count', color='Rule Count', text_auto=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab_common:
            st.subheader(f"Rules found in ALL {total_files} files")
            st.info("Aturan ini adalah standar umum yang ada di setiap benchmark yang lo upload.")
            st.dataframe(common_df[['Rule ID', 'Title', 'Level', 'Description']], use_container_width=True)
            
            # Export Common
            out_common = io.BytesIO()
            common_df.to_excel(out_common, index=False)
            st.download_button("📥 Download Common Rules", out_common.getvalue(), "common_rules.xlsx")

        with tab_specific:
            st.subheader("Rules unique to specific files")
            selected_file = st.selectbox("Filter Specific Rules by File:", options=df['Source_File'].unique())
            file_spec_df = specific_df[specific_df['Source_File'] == selected_file]
            
            st.warning(f"Ditemukan {len(file_spec_df)} aturan yang HANYA ada di file ini.")
            st.dataframe(file_spec_df[['Rule ID', 'Title', 'Level', 'Description']], use_container_width=True)
            
            # Export Specific
            out_spec = io.BytesIO()
            file_spec_df.to_excel(out_spec, index=False)
            st.download_button(f"📥 Download Unique Rules for {selected_file[:20]}...", out_spec.getvalue(), "specific_rules.xlsx")

        with tab_raw:
            st.subheader("Combined Dataset")
            st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    import pandas as pd
    main()
