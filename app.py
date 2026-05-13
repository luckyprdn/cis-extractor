import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
import time
import plotly.express as px

# --- 1. GLOBAL PRE-COMPILED REGEX (LOGIKA ASLI LO) ---
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

# --- UPDATE FILTER: ANTI-DUPLIKAT ---
def clean_fast(text_list):
    if not text_list: return "N/A"
    
    # Buang whitespace, buang string kosong, dan BUANG DUPLIKAT (Penting buat kolom Level)
    # Pakai dict.fromkeys untuk menjaga urutan teks asli
    unique_items = list(dict.fromkeys([t.strip() for t in text_list if t.strip()]))
    
    full = " ".join(unique_items)
    full = RE_CLEAN.sub('', full)
    return " ".join(full.split()).strip() or "N/A"

# --- 2. PREDATOR ENGINE (LOGIKA ASLI LO - TETAP UNTOUCHED) ---
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

# --- 3. FRONTEND UI ---
def main():
    st.set_page_config(page_title="Predator CIS Analyzer", layout="wide", page_icon="🛡️")
    
    st.markdown("""
        <style>
        .stApp { background-color: #f4f7f9; }
        .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e6ed; }
        .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; height: 3em; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Predator Engine: CIS Pro Analyzer")
    st.caption("IT Governance & Policy Optimization Tool")

    with st.sidebar:
        st.header("Control Center")
        st.success("Predator v8.7 Ready")
        st.info("Anti-Duplicate Level Filter Enabled")
        st.divider()
        st.caption("PNM IT Audit Intelligence")

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")

    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        if st.button("🚀 RUN PREDATOR ENGINE", type="primary"):
            start_time = time.time()
            with st.status("Engine is hunting... 🎯", expanded=True) as status:
                data = predator_engine(file_bytes)
                if data:
                    exec_time = time.time() - start_time
                    status.update(label=f"Hunting Complete in {exec_time:.2f}s!", state="complete", expanded=False)
                    st.session_state['data'] = pl.DataFrame(data).to_pandas()
                else:
                    status.update(label="Target Lost!", state="error")
                    st.error("Daftar Isi tidak ditemukan.")

    if 'data' in st.session_state:
        df = st.session_state['data']
        
        st.divider()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Rules", len(df))
        
        l1 = len(df[df['Level'].str.contains('Level 1|L1', case=False, na=False)])
        l2 = len(df[df['Level'].str.contains('Level 2|L2', case=False, na=False)])
        
        k2.metric("L1 Controls", l1)
        k3.metric("L2 Controls", l2)
        k4.metric("Sections", df['Rule ID'].str.split('.').str[0].nunique())

        tab1, tab2, tab3 = st.tabs(["📊 Analytics", "🔍 Explorer", "📥 Export"])

        with tab1:
            c1, c2 = st.columns(2)
            with c1:
                fig_pie = px.pie(df, names='Level', title='Control Level Distribution', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                df['Cat'] = df['Rule ID'].str.split('.').str[0]
                fig_bar = px.bar(df.groupby('Cat').size().reset_index(name='Count'), x='Cat', y='Count', title='Rules by Category')
                st.plotly_chart(fig_bar, use_container_width=True)

        with tab2:
            query = st.text_input("Global Search:", placeholder="e.g. Password, Audit, etc")
            if query:
                display_df = df[df.apply(lambda r: r.astype(str).str.contains(query, case=False).any(), axis=1)]
            else:
                display_df = df
            st.dataframe(display_df, use_container_width=True, height=500)

        with tab3:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                display_df.to_excel(writer, index=False, sheet_name='CIS_Master')
            
            st.download_button(
                label="📥 DOWNLOAD MASTER EXCEL (.xlsx)",
                data=output.getvalue(),
                file_name=f"PREDATOR_EXTRACT_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

if __name__ == "__main__":
    main()
