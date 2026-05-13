import streamlit as st
import fitz
import polars as pl
import pandas as pd
import re
import io
import os
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

# --- 2. PREDATOR ENGINE (LOGIKA ASLI LO - TWEAK STREAM SAJA) ---
def clean_fast(text_list):
    if not text_list: return "N/A"
    full = " ".join(text_list)
    full = RE_CLEAN.sub('', full)
    return " ".join(full.split()).strip() or "N/A"

def predator_engine(pdf_stream):
    # Support stream dari Streamlit uploader
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

# --- 3. FRONTEND UI (TITAN DASHBOARD) ---
def main():
    st.set_page_config(page_title="Predator CIS Extractor", layout="wide")
    
    st.markdown("""
        <style>
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Predator Engine: CIS Extractor")
    st.subheader("High-Performance Compliance Parsing")

    with st.sidebar:
        st.header("Settings")
        st.info("Predator Engine v8.6 Active\nLogic: Memory Slicing")
        st.divider()
        st.caption("Developed for IT Governance & Audit Efficiency")

    uploaded_file = st.file_uploader("Upload CIS Benchmark PDF", type="pdf")

    if uploaded_file:
        # Kita simpan bytes di memori
        pdf_bytes = uploaded_file.read()
        
        if st.button("🚀 Run Predator Extraction", type="primary"):
            with st.status("Engine is hunting for rules...", expanded=True) as status:
                st.write("Caching pages into RAM...")
                data = predator_engine(pdf_bytes)
                
                if data:
                    status.update(label="Hunting Complete!", state="complete", expanded=False)
                    # Load ke Polars
                    df = pl.DataFrame(data)
                    st.session_state['data'] = df.to_pandas()
                else:
                    status.update(label="Target lost!", state="error")
                    st.error("Daftar Isi tidak ditemukan atau format PDF tidak didukung.")

    # Dashboard Display
    if 'data' in st.session_state:
        df = st.session_state['data']
        
        st.divider()
        
        # Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rules", len(df))
        m2.metric("L1 Controls", len(df[df['Level'].str.contains('Level 1', na=False)]))
        m3.metric("L2 Controls", len(df[df['Level'].str.contains('Level 2', na=False)]))
        m4.metric("Categories", df['Rule ID'].str.split('.').str[0].nunique())

        # Analytics
        c1, c2 = st.columns(2)
        with c1:
            fig_pie = px.pie(df, names='Level', title='Controls by Level', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            df['Cat'] = df['Rule ID'].str.split('.').str[0]
            fig_bar = px.bar(df.groupby('Cat').size().reset_index(name='count'), x='Cat', y='count', title='Rules by Category')
            st.plotly_chart(fig_bar, use_container_width=True)

        # Searchable Table
        st.markdown("### 🔍 Search Database")
        query = st.text_input("Search anything (ID, Title, Audit, etc)...", "")
        if query:
            filtered_df = df[df.apply(lambda row: row.astype(str).str.contains(query, case=False).any(), axis=1)]
        else:
            filtered_df = df
        
        st.dataframe(filtered_df, use_container_width=True, height=400)

        # Export
        st.markdown("### 📥 Export Result")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            filtered_df.to_excel(writer, index=False, sheet_name='CIS_Extract')
        
        st.download_button(
            label="Download Master Excel (.xlsx)",
            data=output.getvalue(),
            file_name=f"PREDATOR_{uploaded_file.name.replace('.pdf', '.xlsx')}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if __name__ == "__main__":
    main()
