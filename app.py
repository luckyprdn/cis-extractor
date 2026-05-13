import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import time
import plotly.express as px
from wordcloud import WordCloud
import matplotlib.pyplot as plt

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

# --- 3. EXECUTIVE FRONTEND (FIXED & OPTIMIZED) ---
def main():
    st.set_page_config(page_title="Titan Predator Pro", layout="wide", page_icon="🛡️")
    
    st.markdown("""
        <style>
        .stApp { background-color: #0e1117; color: #e0e6ed; }
        .stMetric { background-color: #1a1c24; padding: 20px; border-radius: 12px; border: 1px solid #3d444d; }
        .stButton>button { border-radius: 10px; font-weight: bold; background-color: #00d4ff; color: #000; border: none; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Predator Engine: Executive Analyzer")
    st.caption("Intelligence Policy Extraction & Compliance Auditor for PNM IT Governance")

    with st.sidebar:
        st.header("🎛️ Control Panel")
        st.success("Predator v8.7: Online")
        st.divider()
        st.markdown("### Filters")
        lv_filter = st.multiselect("Filter by Level", ["Level 1", "Level 2"], default=["Level 1", "Level 2"])
        st.divider()
        if st.button("Clear Session Cache"):
            st.session_state.clear()
            st.rerun()

    uploaded_files = st.file_uploader("Upload CIS Benchmark PDFs", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        if st.button("🚀 EXECUTE PREDATOR SCAN", type="primary", width="stretch"):
            start_time = time.time()
            all_dfs = []
            
            with st.status("Engine is hunting... 🎯", expanded=True) as status:
                for uploaded_file in uploaded_files:
                    st.write(f"Slicing: {uploaded_file.name}...")
                    file_bytes = uploaded_file.read()
                    data = predator_engine(file_bytes)
                    if data:
                        df_tmp = pd.DataFrame(data)
                        df_tmp['Source'] = uploaded_file.name
                        all_dfs.append(df_tmp)
                
                if all_dfs:
                    master_df = pd.concat(all_dfs, ignore_index=True)
                    st.session_state['master_data'] = master_df
                    st.session_state['exec_time'] = time.time() - start_time
                    status.update(label="Scanning Complete!", state="complete")
                else:
                    st.error("No valid data extracted.")

    if 'master_data' in st.session_state:
        df = st.session_state['master_data']
        exec_t = st.session_state['exec_time']
        
        if lv_filter:
            pattern = "|".join(lv_filter)
            df = df[df['Level'].str.contains(pattern, case=False, na=False)]

        st.divider()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rules", len(df))
        m2.metric("L1 Controls", len(df[df['Level'].str.contains('L1|Level 1', case=False, na=False)]))
        m3.metric("L2 Controls", len(df[df['Level'].str.contains('L2|Level 2', case=False, na=False)]))
        m4.metric("Engine Speed", f"{exec_t:.2f}s")

        tab_viz, tab_compare, tab_explorer, tab_cloud = st.tabs(["📊 Analytics", "🔄 Comparison", "🔍 Data Explorer", "☁️ Themes"])

        with tab_viz:
            c1, c2 = st.columns(2)
            with c1:
                fig_pie = px.pie(df, names='Level', title='Control Level Distribution', hole=0.5,
                                 color_discrete_sequence=px.colors.qualitative.Vivid)
                st.plotly_chart(fig_pie, width="stretch")
            with c2:
                df['Cat'] = df['Rule ID'].str.split('.').str[0]
                fig_bar = px.bar(df.groupby(['Source', 'Cat']).size().reset_index(name='Count'), 
                                 x='Cat', y='Count', color='Source', barmode='group', title='Rules by Category')
                st.plotly_chart(fig_bar, width="stretch")

        with tab_compare:
            if df['Source'].nunique() > 1:
                t_counts = df.groupby('Title')['Source'].nunique().reset_index()
                t_counts.columns = ['Title', 'File_Count']
                df_c = df.merge(t_counts, on='Title')
                common = df_c[df_c['File_Count'] == df['Source'].nunique()].drop_duplicates('Title')
                specific = df_c[df_c['File_Count'] == 1]
                
                cc1, cc2 = st.columns(2)
                cc1.info(f"**Common Rules:** {len(common)}")
                cc2.warning(f"**Specific Rules:** {len(specific)}")
                sel_source = st.selectbox("Select File for unique rules:", df['Source'].unique())
                st.dataframe(specific[specific['Source'] == sel_source][['Rule ID', 'Title', 'Level']])
            else:
                st.info("Upload >1 file for comparison.")

        with tab_explorer:
            query = st.text_input("Global Search:", "")
            df_disp = df[df.apply(lambda r: r.astype(str).str.contains(query, case=False).any(), axis=1)] if query else df
            st.dataframe(df_disp)

            st.warning("⚠️ Excel memiliki batas 32,767 karakter per cell. Gunakan CSV jika data Audit/Remediation sangat panjang.")
            
            # Excel Buffer
            output_ex = io.BytesIO()
            with pd.ExcelWriter(output_ex, engine='xlsxwriter') as writer:
                df_disp.to_excel(writer, index=False, sheet_name='Audit_Checklist')
            
            # CSV Buffer (No character limit)
            output_csv = df_disp.to_csv(index=False).encode('utf-8')

            ex1, ex2 = st.columns(2)
            with ex1:
                st.download_button("📥 Download Excel (Standard)", output_ex.getvalue(), "audit.xlsx", width="stretch")
            with ex2:
                st.download_button("📥 Download CSV (Full Data)", output_csv, "audit_full.csv", width="stretch")

        with tab_cloud:
            text_blob = " ".join(df['Description'].astype(str))
            wc = WordCloud(width=800, height=400, background_color='#0e1117', colormap='Blues').generate(text_blob)
            fig_wc, ax = plt.subplots(figsize=(10, 5), facecolor='#0e1117')
            ax.imshow(wc, interpolation='bilinear')
            ax.axis('off')
            st.pyplot(fig_wc)

if __name__ == "__main__":
    main()
