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
from datetime import datetime

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

# --- 3. FRONTEND TITAN DASHBOARD PRO ---
def main():
    st.set_page_config(page_title="Titan Predator | IT Governance PNM", layout="wide", page_icon="🛡️")

    # Dark Mode Custom Styling
    st.markdown("""
        <style>
        .stApp { background-color: #0e1117; color: #ffffff; }
        [data-testid="stMetricValue"] { font-size: 28px; color: #00d4ff; }
        .stButton>button { border-radius: 20px; background-color: #00d4ff; color: black; font-weight: bold; border: none; }
        .stButton>button:hover { background-color: #00b8e6; color: white; }
        .css-1r6slb0 { background-color: #1a1c24; border-radius: 15px; padding: 20px; border: 1px solid #3d444d; }
        .stTabs [data-baseweb="tab"] { color: #a1a1a1; }
        .stTabs [aria-selected="true"] { color: #00d4ff !important; border-bottom-color: #00d4ff !important; }
        </style>
    """, unsafe_allow_html=True)

    # Sidebar Pro
    with st.sidebar:
        st.title("🛡️ Titan Predator")
        st.markdown("`Version 9.5-PRO`")
        st.divider()
        st.header("Admin IT Gov")
        st.info(f"User: Lucky Pradana\nDept: RSP / ATI PNM")
        st.divider()
        st.caption("Engine: Predator v8.6 (Original Logic)")
        st.caption(f"Last Sync: {datetime.now().strftime('%H:%M:%S')}")

    # Hero Section
    c_head1, c_head2 = st.columns([3, 1])
    with c_head1:
        st.title("CIS Benchmark Policy Extractor")
        st.write("Transform standard PDF benchmarks into actionable IT Governance datasets.")
    with c_head2:
        st.write("")
        # Placeholder for PNM or IT Gov Logo
        st.image("https://www.cisecurity.org/wp-content/uploads/2017/04/cis-logo.png", width=120)

    # File Uploader with Container
    with st.container():
        st.subheader("📁 Upload Center")
        uploaded_file = st.file_uploader("Drop your CIS Benchmark PDF (Windows/Debian/Ubuntu)", type="pdf")

    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        # Action Button
        if st.button("🚀 INITIATE PREDATOR ENGINE", use_container_width=True):
            start_time = time.time()
            with st.status("Engine is hunting... 🎯", expanded=True) as status:
                st.write("Mapping Memory Blocks...")
                data = predator_engine(file_bytes)
                
                if data:
                    exec_time = time.time() - start_time
                    st.session_state['data'] = pd.DataFrame(data)
                    st.session_state['exec_time'] = exec_time
                    status.update(label=f"Hunting Complete in {exec_time:.2f}s!", state="complete", expanded=False)
                else:
                    status.update(label="Target Lost!", state="error")
                    st.error("Table of Contents not found. Ensure this is an official CIS PDF.")

    # --- DASHBOARD VIEW ---
    if 'data' in st.session_state:
        df = st.session_state['data']
        
        st.divider()
        
        # EXECUTIVE SUMMARY CARDS
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Total Rules Extracted", len(df))
        with col_m2:
            l1_count = len(df[df['Level'].str.contains('Level 1|L1', case=False, na=False)])
            st.metric("L1 (Critical Controls)", l1_count)
        with col_m3:
            l2_count = len(df[df['Level'].str.contains('Level 2|L2', case=False, na=False)])
            st.metric("L2 (Defense in Depth)", l2_count)
        with col_m4:
            st.metric("Processing Speed", f"{st.session_state['exec_time']:.2f}s")

        # TABBED ANALYTICS
        tab_viz, tab_data, tab_export = st.tabs(["📊 Audit Analytics", "🔍 Interactive Explorer", "📥 Multi-Format Export"])

        with tab_viz:
            st.subheader("Compliance Distribution Heatmap")
            v_col1, v_col2 = st.columns(2)
            
            with v_col1:
                # Distribution of Levels
                fig_pie = px.pie(df, names='Level', hole=0.6, 
                                 title='Security Hardening Levels',
                                 color_discrete_sequence=px.colors.sequential.Cyan_r)
                fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with v_col2:
                # Controls by Category (Rule ID digit 1)
                df['Category'] = df['Rule ID'].str.split('.').str[0]
                cat_count = df.groupby('Category').size().reset_index(name='Rules')
                fig_bar = px.bar(cat_count, x='Category', y='Rules', title='Rules Volume by Section',
                                 color='Rules', color_continuous_scale='Blues')
                fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig_bar, use_container_width=True)

        with tab_data:
            st.subheader("Global Policy Database")
            search = st.text_input("Quick Search (e.g. 'Password', 'Encryption', 'Admin')", "")
            
            if search:
                mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
                display_df = df[mask]
            else:
                display_df = df
            
            st.dataframe(display_df, use_container_width=True, height=500)

        with tab_export:
            st.subheader("Final Audit Reporting")
            st.write("Ekspor hasil audit ke format profesional untuk checklist internal PNM.")
            
            # EXCEL EXPORT (High Speed Engine)
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Audit_Checklist')
                workbook = writer.book
                worksheet = writer.sheets['Audit_Checklist']
                
                # Pro Header Styling
                header_format = workbook.add_format({
                    'bold': True, 'bg_color': '#00d4ff', 'color': 'black', 'border': 1
                })
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
            
            e_col1, e_col2, e_col3 = st.columns(3)
            with e_col1:
                st.download_button(
                    label="📥 DOWNLOAD EXCEL (.xlsx)",
                    data=excel_buffer.getvalue(),
                    file_name=f"TITAN_AUDIT_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )
            with e_col2:
                csv_data = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📄 DOWNLOAD CSV (.csv)",
                    data=csv_data,
                    file_name=f"TITAN_AUDIT_{uploaded_file.name.replace('.pdf', '')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with e_col3:
                # JSON buat integrasi backend lain
                json_data = df.to_json(orient='records')
                st.download_button(
                    label="💻 DOWNLOAD JSON (.json)",
                    data=json_data,
                    file_name=f"TITAN_AUDIT_{uploaded_file.name.replace('.pdf', '')}.json",
                    mime="application/json",
                    use_container_width=True
                )

if __name__ == "__main__":
    main()
