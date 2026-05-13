import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import time
import plotly.express as px
import plotly.graph_objects as go
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

# --- 3. FRONTEND UI (PREDATOR ULTIMATE DASHBOARD) ---
def main():
    st.set_page_config(page_title="Predator Compare Pro", layout="wide", page_icon="🛡️")
    
    # CSS Custom (Hanya UI, Tanpa Logic)
    st.markdown("""
        <style>
        .stApp { background-color: #f0f2f6; }
        .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] { background-color: #ffffff; padding: 10px 20px; border-radius: 5px 5px 0 0; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Predator Engine: Ultimate Analysis")
    st.markdown("---")

    with st.sidebar:
        st.header("⚙️ Settings")
        st.success("Predator v8.7 Ready")
        st.divider()
        st.markdown("### Visual Options")
        show_wordcloud = st.toggle("Enable WordCloud Analysis", value=True)
        st.divider()
        if st.button("Reset Session", type="secondary"):
            st.session_state.clear()
            st.rerun()

    # MULTI UPLOAD
    uploaded_files = st.file_uploader("Upload CIS Benchmark PDFs (Multi-select)", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        if st.button("⚡ EXECUTE MULTI-SCAN & ANALYZE", type="primary", use_container_width=True):
            all_data = []
            with st.status("Engine is hunting...", expanded=True) as status:
                for uploaded_file in uploaded_files:
                    st.write(f"Slicing: {uploaded_file.name}...")
                    file_bytes = uploaded_file.read()
                    extracted = predator_engine(file_bytes)
                    if extracted:
                        df_tmp = pd.DataFrame(extracted)
                        df_tmp['Source_File'] = uploaded_file.name
                        all_data.append(df_tmp)
                
                if all_data:
                    st.session_state['master_data'] = pd.concat(all_data, ignore_index=True)
                    status.update(label="Scanning Complete!", state="complete")
                else:
                    st.error("No valid data found.")

    # --- ANALYSIS DASHBOARD ---
    if 'master_data' in st.session_state:
        df = st.session_state['master_data']
        total_files = df['Source_File'].nunique()
        
        # LOGIK PERBANDINGAN (TIDAK MENGURANGI, HANYA MENAMBAH VIEW)
        title_counts = df.groupby('Title')['Source_File'].nunique().reset_index()
        title_counts.columns = ['Title', 'File_Count']
        df_analysis = df.merge(title_counts, on='Title')
        
        common_df = df_analysis[df_analysis['File_Count'] == total_files].drop_duplicates(subset=['Title'])
        specific_df = df_analysis[df_analysis['File_Count'] == 1]

        # TABS FRONTEND
        tab_sum, tab_common, tab_specific, tab_compare, tab_cloud = st.tabs([
            "📊 Summary Analytics", "🔗 Common Rules", "🎯 Specific Rules", "🔄 Side-by-Side", "☁️ WordCloud"
        ])

        with tab_sum:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Files Analyzed", total_files)
            col2.metric("Common Rules Found", len(common_df))
            col3.metric("Specific Rules Found", len(specific_df))
            
            st.write("### Rule Distribution per Source")
            dist_df = df.groupby('Source_File').size().reset_index(name='Rule Count')
            fig = px.bar(dist_df, x='Source_File', y='Rule Count', color='Rule Count', 
                         color_continuous_scale='Viridis', text_auto=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab_common:
            st.subheader("Standard Global Rules (Exist in all files)")
            st.dataframe(common_df[['Rule ID', 'Title', 'Level', 'Description']], use_container_width=True)
            
            output_common = io.BytesIO()
            common_df.to_excel(output_common, index=False)
            st.download_button("📥 Export Common Rules", output_common.getvalue(), "common_rules.xlsx")

        with tab_specific:
            st.subheader("Unique Source Rules")
            sel_file = st.selectbox("Select Source to View Specific Rules:", df['Source_File'].unique())
            file_spec = specific_df[specific_df['Source_File'] == sel_file]
            st.dataframe(file_spec[['Rule ID', 'Title', 'Level', 'Description']], use_container_width=True)

        with tab_compare:
            st.subheader("Side-by-Side Comparison Viewer")
            st.info("Bandingkan implementasi rules yang sama antar file.")
            target_title = st.selectbox("Select Rule to Compare:", common_df['Title'].unique())
            
            compare_view = df[df['Title'] == target_title]
            for idx, row in compare_view.iterrows():
                with st.expander(f"📄 Source: {row['Source_File']}"):
                    st.write(f"**ID:** {row['Rule ID']} | **Level:** {row['Level']}")
                    st.write("**Audit Procedure:**")
                    st.code(row['Audit'])
                    st.write("**Remediation:**")
                    st.code(row['Remediation'])

        with tab_cloud:
            if show_wordcloud:
                st.subheader("Policy Theme Discovery")
                text_blob = " ".join(df['Description'].astype(str))
                wordcloud = WordCloud(width=800, height=400, background_color='white', 
                                      colormap='viridis').generate(text_blob)
                
                fig_wc, ax_wc = plt.subplots(figsize=(10, 5))
                ax_wc.imshow(wordcloud, interpolation='bilinear')
                ax_wc.axis('off')
                st.pyplot(fig_wc)
                st.caption("Visualisasi ini ngebantu lo nemuin fokus security yang paling sering disebut di benchmark.")

if __name__ == "__main__":
    main()
