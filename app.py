import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import plotly.express as px

# --- 1. GLOBAL PRE-COMPILED REGEX (LOGIKA ASLI LO - HARAM DISENTUH) ---
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
    full = " ".join(text_list)
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

# --- 3. FRONTEND UI (REVISED ENTERPRISE LOOK) ---
def main():
    st.set_page_config(page_title="Predator CIS Analyzer", layout="wide", page_icon="🛡️")
    
    # Injection CSS untuk merapikan visual
    st.markdown("""
        <style>
        .stApp { background-color: #f4f7f9; }
        .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e6ed; }
        .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
        div[data-testid="stExpander"] { background-color: #ffffff; border-radius: 10px; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Predator Engine: CIS Benchmark Extractor")
    st.markdown("Automated Policy Extraction & Audit Intelligence")

    # --- SIDEBAR ---
    with st.sidebar:
        st.image("https://www.cisecurity.org/wp-content/uploads/2017/04/cis-logo.png", width=150)
        st.header("Control Center")
        st.info("Predator Engine v8.6 Active\nMode: High-Performance")
        
        # User Manual
        with st.expander("📖 Quick Guide"):
            st.caption("1. Upload PDF CIS asli\n2. Klik 'Run Predator'\n3. Filter & Download Hasil")
        
        st.divider()
        st.caption("PNM IT Governance Optimization Tool")

    # --- UPLOAD SECTION ---
    upload_col, info_col = st.columns([2, 1])
    with upload_col:
        uploaded_file = st.file_uploader("Drop PDF Benchmark here", type="pdf")
    with info_col:
        if uploaded_file:
            st.success(f"**File Loaded:**\n{uploaded_file.name}")
        else:
            st.warning("Awaiting PDF upload...")

    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        if st.button("🚀 RUN PREDATOR ENGINE", type="primary"):
            with st.status("Engine is hunting... 🎯", expanded=True) as status:
                st.write("Extracting and Slicing Pages...")
                data = predator_engine(file_bytes)
                
                if data:
                    status.update(label="Hunting Complete!", state="complete", expanded=False)
                    st.session_state['predator_data'] = pl.DataFrame(data).to_pandas()
                else:
                    status.update(label="Target Lost!", state="error")
                    st.error("Daftar Isi tidak ditemukan. Pastikan PDF adalah CIS Benchmark asli.")

    # --- RESULT DASHBOARD ---
    if 'predator_data' in st.session_state:
        df = st.session_state['predator_data']
        
        # 1. KPI Metrics
        st.divider()
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Total Controls", len(df))
        
        # Penanganan L1/L2 lebih dinamis
        l1_count = len(df[df['Level'].str.contains('Level 1|L1', case=False, na=False)])
        l2_count = len(df[df['Level'].str.contains('Level 2|L2', case=False, na=False)])
        
        kpi2.metric("L1 Controls", l1_count)
        kpi3.metric("L2 Controls", l2_count)
        kpi4.metric("Categories", df['Rule ID'].str.split('.').str[0].nunique())

        # 2. Tabs untuk Organisasi Data
        tab_dash, tab_table, tab_export = st.tabs(["📊 Analytics", "🔍 Data Explorer", "📥 Export Master"])

        with tab_dash:
            c1, c2 = st.columns(2)
            with c1:
                # Pie Chart Level
                fig_pie = px.pie(df, names='Level', title='Control Level Distribution', 
                                 hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                # Bar Chart Category
                df['Cat'] = df['Rule ID'].str.split('.').str[0]
                cat_summary = df.groupby('Cat').size().reset_index(name='Count')
                fig_bar = px.bar(cat_summary, x='Cat', y='Count', title='Controls by Main Category',
                                 labels={'Cat': 'Rule Category'}, color='Count', color_continuous_scale='Teals')
                st.plotly_chart(fig_bar, use_container_width=True)

        with tab_table:
            st.markdown("### Searchable Ruleset")
            query = st.text_input("Global Search (ID, Title, Audit Procedure, etc):", placeholder="e.g. Password")
            
            if query:
                mask = df.apply(lambda r: r.astype(str).str.contains(query, case=False).any(), axis=1)
                filtered_df = df[mask]
            else:
                filtered_df = df
            
            st.dataframe(filtered_df, use_container_width=True, height=500)

        with tab_export:
            st.info("Export hasil ekstraksi ke format Excel untuk kebutuhan Audit Checklist.")
            
            # Export Logic
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Pakai dataframe yang terfilter search jika ada
                target_df = filtered_df if query else df
                target_df.to_excel(writer, index=False, sheet_name='CIS_Master_Checklist')
                
                # Auto-adjust column width (Basic)
                worksheet = writer.sheets['CIS_Master_Checklist']
                for idx, col in enumerate(target_df.columns):
                    worksheet.set_column(idx, idx, 20)

            st.download_button(
                label="📥 DOWNLOAD MASTER EXCEL",
                data=output.getvalue(),
                file_name=f"PREDATOR_EXTRACT_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

if __name__ == "__main__":
    main()
