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

# --- 3. FRONTEND UI (TITAN PRO MODE) ---
def main():
    st.set_page_config(page_title="Predator CIS Pro Analyzer", layout="wide", page_icon="🛡️")
    
    st.markdown("""
        <style>
        .stApp { background-color: #f8f9fa; }
        .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border-left: 5px solid #00d4ff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .stButton>button { border-radius: 8px; font-weight: bold; height: 3em; background-color: #00d4ff; color: white; border: none; }
        .stButton>button:hover { background-color: #00b8e6; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Predator Engine: CIS Pro Analyzer")
    st.subheader("Enterprise-Grade Policy Extraction & Audit Intelligence")

    with st.sidebar:
        st.header("⚙️ Engine Control")
        st.success("Core: Predator v8.7 Active")
        st.info("PNM IT Governance Tool (RSP/ATI)")
        st.divider()
        st.markdown("### 🔍 Global Filters")
        # FITUR: Filter Berdasarkan Level
        level_filter = st.multiselect("Filter by Level:", ["Level 1", "Level 2"], default=["Level 1", "Level 2"])
        st.divider()
        if st.button("Reset Session"):
            st.session_state.clear()
            st.rerun()

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")

    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        if st.button("🚀 INITIATE PREDATOR SCAN", type="primary", use_container_width=True):
            # FITUR: Execution Time Tracker
            start_time = time.time()
            with st.status("Engine is hunting for rules... 🎯", expanded=True) as status:
                st.write("Caching Memory Blocks...")
                data = predator_engine(file_bytes)
                
                if data:
                    exec_time = time.time() - start_time
                    status.update(label=f"Hunting Complete in {exec_time:.2f}s!", state="complete", expanded=False)
                    # Simpan data & timer ke session
                    st.session_state['master_data'] = pd.DataFrame(data)
                    st.session_state['exec_time'] = exec_time
                else:
                    status.update(label="Target Lost!", state="error")
                    st.error("Daftar Isi tidak terdeteksi. Gunakan PDF CIS Benchmark asli.")

    # --- DASHBOARD & ANALYTICS AREA ---
    if 'master_data' in st.session_state:
        df = st.session_state['master_data']
        
        # Apply Sidebar Filters
        if level_filter:
            pattern = "|".join(level_filter)
            df = df[df['Level'].str.contains(pattern, case=False, na=False)]

        st.divider()
        
        # 1. KPI Metrics (Eye-catching)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Rules Found", len(df))
        k2.metric("Level 1 Controls", len(df[df['Level'].str.contains('Level 1|L1', case=False, na=False)]))
        k3.metric("Level 2 Controls", len(df[df['Level'].str.contains('Level 2|L2', case=False, na=False)]))
        k4.metric("Engine Execution Speed", f"{st.session_state['exec_time']:.2f}s")

        # 2. Tabs for Organization
        tab_dash, tab_explorer, tab_export = st.tabs(["📊 Audit Analytics", "🔍 Searchable Database", "📥 Professional Export"])

        with tab_dash:
            c1, c2 = st.columns(2)
            with c1:
                # Distribution Pie Chart
                fig_pie = px.pie(df, names='Level', title='Control Level Distribution', hole=0.4,
                                 color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                # Categories Bar Chart
                df['Category'] = df['Rule ID'].str.split('.').str[0]
                cat_summary = df.groupby('Category').size().reset_index(name='Rules')
                fig_bar = px.bar(cat_summary, x='Category', y='Rules', title='Rules by Main Category ID',
                                 color='Rules', color_continuous_scale='Teals')
                st.plotly_chart(fig_bar, use_container_width=True)

        with tab_explorer:
            st.markdown("### Interactive Global Search")
            # FITUR: Filter Search Real-time
            search_query = st.text_input("Cari di seluruh kolom (ID, Title, Audit Procedure, dll):", "")
            
            if search_query:
                filtered_df = df[df.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)]
            else:
                filtered_df = df

            st.dataframe(filtered_df, use_container_width=True, height=500)

        with tab_export:
            st.info("Export hasil audit dalam format profesional untuk pelaporan internal.")
            
            # Excel Logic (XlsxWriter)
            excel_out = io.BytesIO()
            with pd.ExcelWriter(excel_out, engine='xlsxwriter') as writer:
                # Gunakan data yang sedang difilter/dicari jika ada
                target_df = filtered_df if 'filtered_df' in locals() else df
                target_df.to_excel(writer, index=False, sheet_name='Audit_Checklist')
                
                # Pro Header Styling
                workbook = writer.book
                worksheet = writer.sheets['Audit_Checklist']
                header_fmt = workbook.add_format({'bold': True, 'bg_color': '#00d4ff', 'font_color': 'white', 'border': 1})
                for col_num, value in enumerate(target_df.columns.values):
                    worksheet.write(0, col_num, value, header_fmt)

            st.download_button(
                label="📥 DOWNLOAD MASTER EXCEL (.xlsx)",
                data=excel_out.getvalue(),
                file_name=f"TITAN_AUDIT_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

if __name__ == "__main__":
    main()
