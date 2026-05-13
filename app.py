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

# --- 3. FRONTEND UI (TITAN PRO DASHBOARD) ---
def main():
    st.set_page_config(page_title="Predator CIS Pro", layout="wide", page_icon="🛡️")
    
    # Custom CSS for Dark Modern Look
    st.markdown("""
        <style>
        .stApp { background: linear-gradient(to bottom, #0e1117, #1a1c24); color: #e0e6ed; }
        .stMetric { background-color: #262730; padding: 20px; border-radius: 12px; border-left: 5px solid #00d4ff; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] { 
            background-color: #262730; border-radius: 5px 5px 0 0; padding: 10px 20px; color: white;
        }
        .stDataFrame { border: 1px solid #3d444d; border-radius: 10px; }
        </style>
    """, unsafe_allow_html=True)

    # Header with Logo Area
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.title("🛡️ Predator Engine: CIS Pro Analyzer")
        st.caption("Advanced Policy Extraction | High-Performance Slicing | IT Governance Ready")
    with col_h2:
        st.write("")
        st.image("https://www.cisecurity.org/wp-content/uploads/2017/04/cis-logo.png", width=100)

    # Sidebar Tools
    with st.sidebar:
        st.header("⚡ Engine Control")
        st.success("Core: Predator v8.6")
        st.info("Status: Memory-Resident Ready")
        st.divider()
        st.markdown("### Filter Settings")
        level_filter = st.multiselect("Control Level", ["Level 1", "Level 2"], default=["Level 1", "Level 2"])
        st.divider()
        st.caption("Fokus: Zero-Loss Extraction")

    # Upload Zone
    uploaded_file = st.file_uploader("Drop CIS Benchmark PDF", type="pdf")

    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        if st.button("🚀 INITIATE PREDATOR SCAN", type="primary", use_container_width=True):
            start_time = time.time()
            with st.status("Engine is hunting... 🎯", expanded=True) as status:
                st.write("Reading PDF Structure...")
                data = predator_engine(file_bytes)
                
                if data:
                    exec_time = time.time() - start_time
                    status.update(label=f"Hunting Complete in {exec_time:.2f}s!", state="complete", expanded=False)
                    st.session_state['data'] = pl.DataFrame(data).to_pandas()
                    st.session_state['exec_time'] = exec_time
                else:
                    status.update(label="Target Lost!", state="error")
                    st.error("Daftar Isi tidak terdeteksi.")

    # --- RESULT AREA ---
    if 'data' in st.session_state:
        df = st.session_state['data']
        
        # Filtering based on sidebar
        if level_filter:
            pattern = "|".join(level_filter)
            df = df[df['Level'].str.contains(pattern, case=False, na=False)]

        st.divider()

        # 1. KPI Metrics with Performance Timer
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Rules", len(df))
        k2.metric("L1 Controls", len(df[df['Level'].str.contains('Level 1|L1', case=False, na=False)]))
        k3.metric("L2 Controls", len(df[df['Level'].str.contains('Level 2|L2', case=False, na=False)]))
        k4.metric("Exec Speed", f"{st.session_state['exec_time']:.2f}s")

        # 2. Tabs for different views
        tab1, tab2, tab3 = st.tabs(["📊 Audit Analytics", "🔍 Deep Explorer", "📥 Master Export"])

        with tab1:
            c1, c2 = st.columns([1, 1])
            with c1:
                # Sunburst or Pie
                fig_pie = px.pie(df, names='Level', title='Control Level Distribution', hole=0.5,
                                 color_discrete_sequence=px.colors.qualitative.Vivid)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                # Category Bar
                df['Cat'] = df['Rule ID'].str.split('.').str[0]
                cat_sum = df.groupby('Cat').size().reset_index(name='count')
                fig_bar = px.bar(cat_sum, x='Cat', y='count', title='Rules by Category ID',
                                 color='count', color_continuous_scale='Blues')
                st.plotly_chart(fig_bar, use_container_width=True)

        with tab2:
            st.markdown("### Search & Filter Audit Procedures")
            search = st.text_input("Global Search (misal: 'Firewall', 'Password', 'Account'):", placeholder="Cari di semua kolom...")
            
            if search:
                mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
                filtered_df = df[mask]
            else:
                filtered_df = df
            
            st.dataframe(filtered_df, use_container_width=True, height=500)

        with tab3:
            st.info("Ekspor hasil audit checklist ke format Excel (.xlsx) atau CSV.")
            
            final_df = filtered_df if 'filtered_df' in locals() else df
            
            # Export Logic (Memory Buffer)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False, sheet_name='Audit_Checklist')
                # Styling sheet
                workbook = writer.book
                worksheet = writer.sheets['Audit_Checklist']
                header_fmt = workbook.add_format({'bold': True, 'bg_color': '#00d4ff', 'font_color': 'white'})
                for col_num, value in enumerate(final_df.columns.values):
                    worksheet.write(0, col_num, value, header_fmt)

            ex1, ex2 = st.columns(2)
            with ex1:
                st.download_button(
                    label="📥 DOWNLOAD EXCEL CHECKLIST",
                    data=output.getvalue(),
                    file_name=f"PREDATOR_EXTRACT_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            with ex2:
                csv_data = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📄 DOWNLOAD CSV MASTER",
                    data=csv_data,
                    file_name=f"PREDATOR_EXTRACT_{uploaded_file.name.replace('.pdf', '')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

if __name__ == "__main__":
    main()
