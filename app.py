import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import time
import plotly.express as px
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

# --- 3. FRONTEND TITAN DASHBOARD ---
def main():
    st.set_page_config(page_title="Titan Predator Extractor", layout="wide", page_icon="🛡️")

    # Styling UI Pro
    st.markdown("""
        <style>
        .stApp { background-color: #0e1117; color: #ffffff; }
        [data-testid="stMetricValue"] { font-size: 32px; color: #00d4ff; font-weight: bold; }
        .stButton>button { border-radius: 10px; background-color: #00d4ff; color: #000000; font-weight: bold; border: none; height: 3em; }
        .stButton>button:hover { background-color: #00b8e6; color: #ffffff; }
        .stTabs [data-baseweb="tab-list"] { gap: 20px; }
        .stTabs [data-baseweb="tab"] { color: #808495; }
        .stTabs [aria-selected="true"] { color: #00d4ff !important; border-bottom-color: #00d4ff !important; }
        </style>
    """, unsafe_allow_html=True)

    # Hero Section
    c1, c2 = st.columns([4, 1])
    with c1:
        st.title("🛡️ Titan Predator Pro")
        st.caption("Intelligence Policy Extraction Engine | PNM IT Governance")
    with c2:
        st.image("https://www.cisecurity.org/wp-content/uploads/2017/04/cis-logo.png", width=90)

    st.divider()

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")

    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        if st.button("🚀 EXECUTE PREDATOR SCAN", use_container_width=True):
            start_t = time.time()
            with st.status("Engine is hunting... 🎯", expanded=True) as status:
                st.write("Processing Memory Blocks...")
                data = predator_engine(file_bytes)
                
                if data:
                    exec_t = time.time() - start_t
                    st.session_state['data'] = pd.DataFrame(data)
                    st.session_state['exec_time'] = exec_t
                    status.update(label=f"Hunting Complete in {exec_t:.2f}s!", state="complete", expanded=False)
                else:
                    status.update(label="Target Lost!", state="error")
                    st.error("Gagal mendeteksi Daftar Isi.")

    # --- DASHBOARD VIEW ---
    if 'data' in st.session_state:
        df = st.session_state['data']
        
        # Row 1: Executive Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rules", len(df))
        l1 = len(df[df['Level'].str.contains('Level 1|L1', case=False, na=False)])
        m2.metric("L1 (Critical)", l1)
        l2 = len(df[df['Level'].str.contains('Level 2|L2', case=False, na=False)])
        m3.metric("L2 (Defense)", l2)
        m4.metric("Engine Speed", f"{st.session_state['exec_time']:.2f}s")

        st.write("")

        # Row 2: Analytics Tabs
        tab_viz, tab_table, tab_export = st.tabs(["📊 Analytics Heatmap", "🔍 Policy Explorer", "📥 Master Export"])

        with tab_viz:
            v1, v2 = st.columns(2)
            with v1:
                # Perbaikan: Pakai skema warna string yang aman
                fig_pie = px.pie(df, names='Level', hole=0.5, 
                                 title='Security Hardening Distribution',
                                 color_discrete_sequence=px.colors.qualitative.T10)
                fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with v2:
                df['Category'] = df['Rule ID'].str.split('.').str[0]
                cat_count = df.groupby('Category').size().reset_index(name='Rules')
                fig_bar = px.bar(cat_count, x='Category', y='Rules', title='Rules Volume by Section',
                                 color='Rules', color_continuous_scale='blues')
                fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig_bar, use_container_width=True)

        with tab_table:
            st.subheader("Global Policy Database")
            search = st.text_input("Quick Filter (Title, Audit, or Remediation)...", "")
            
            if search:
                mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
                display_df = df[mask]
            else:
                display_df = df
            
            st.dataframe(display_df, use_container_width=True, height=500)

        with tab_export:
            st.subheader("Reporting Center")
            st.info("Pilih format ekspor untuk dokumen audit internal.")
            
            # Excel Buffer (XlsxWriter)
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Audit_Checklist')
                # Styling Header
                workbook = writer.book
                worksheet = writer.sheets['Audit_Checklist']
                header_fmt = workbook.add_format({'bold': True, 'bg_color': '#00d4ff', 'border': 1})
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_fmt)

            ex1, ex2 = st.columns(2)
            with ex1:
                st.download_button(
                    label="📥 DOWNLOAD EXCEL (.xlsx)",
                    data=excel_buffer.getvalue(),
                    file_name=f"TITAN_AUDIT_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )
            with ex2:
                csv_data = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📄 DOWNLOAD CSV (.csv)",
                    data=csv_data,
                    file_name=f"TITAN_AUDIT_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

if __name__ == "__main__":
    main()
