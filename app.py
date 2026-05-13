import streamlit as st
import fitz
import polars as pl
import pandas as pd
import plotly.express as px
import re
import io
import os

# --- 1. GLOBAL PRE-COMPILED REGEX (LOGIKA ASLI LO - JANGAN DIGANGGU) ---
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

# --- 3. FRONTEND UI (REVISED & CLEAN) ---
def main():
    st.set_page_config(page_title="Predator CIS Analyzer", layout="wide", page_icon="🛡️")
    
    # CSS Custom untuk tampilan Dark/Light yang konsisten
    st.markdown("""
        <style>
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e6ed; }
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stTabs [data-baseweb="tab"] { height: 50px; font-weight: 600; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Predator Engine: CIS Extractor")
    st.markdown("---")

    with st.sidebar:
        st.header("⚙️ System Status")
        st.success("Predator Engine v8.6 Active")
        st.info("Mode: Memory-Resident Slicing")
        st.divider()
        st.caption("Fokus pada akurasi ID dan pencegahan data bolong.")

    uploaded_file = st.file_uploader("Upload PDF CIS Benchmark", type="pdf")

    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        if st.button("🚀 EXECUTE PREDATOR SCAN", type="primary", use_container_width=True):
            with st.status("Engine is hunting for rules...", expanded=True) as status:
                st.write("Caching pages to RAM...")
                data = predator_engine(file_bytes)
                
                if data:
                    status.update(label="Hunting Complete!", state="complete", expanded=False)
                    # Convert ke Polars lalu ke Pandas untuk UI Streamlit
                    df = pl.DataFrame(data).to_pandas()
                    st.session_state['predator_df'] = df
                else:
                    status.update(label="Target Lost!", state="error")
                    st.error("Gagal mendeteksi Daftar Isi. Pastikan PDF adalah CIS Benchmark asli.")

    # --- HASIL SCAN ---
    if 'predator_df' in st.session_state:
        df = st.session_state['predator_df']
        
        # Dashboard Summary
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Rules Found", len(df))
        
        # Deteksi L1/L2
        l1 = len(df[df['Level'].str.contains('Level 1|L1', case=False, na=False)])
        l2 = len(df[df['Level'].str.contains('Level 2|L2', case=False, na=False)])
        
        col2.metric("Level 1 (Critical)", l1)
        col3.metric("Level 2 (Defense)", l2)
        col4.metric("Categories", df['Rule ID'].str.split('.').str[0].nunique())

        st.divider()

        # Tabs untuk navigasi
        tab1, tab2, tab3 = st.tabs(["📊 Analytics", "🔍 Interactive Explorer", "📥 Export Results"])

        with tab1:
            c1, c2 = st.columns(2)
            with c1:
                fig_pie = px.pie(df, names='Level', title='Controls by Level', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                df['Cat'] = df['Rule ID'].str.split('.').str[0]
                cat_data = df.groupby('Cat').size().reset_index(name='count')
                fig_bar = px.bar(cat_data, x='Cat', y='count', title='Rules by Main Category', color='count')
                st.plotly_chart(fig_bar, use_container_width=True)

        with tab2:
            st.markdown("### Searchable Ruleset")
            search = st.text_input("Filter rules (ID, Title, Description, Audit...)", placeholder="Type 'password' or 'registry'...")
            
            if search:
                # Filter global di semua kolom
                mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
                display_df = df[mask]
            else:
                display_df = df
            
            st.dataframe(display_df, use_container_width=True, height=500)

        with tab3:
            st.markdown("### Download Data")
            st.write("Ekspor hasil scan Predator Engine ke format yang lo butuhin.")
            
            # Excel Buffer
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                display_df.to_excel(writer, index=False, sheet_name='CIS_Checklist')
            
            ex_col1, ex_col2 = st.columns(2)
            with ex_col1:
                st.download_button(
                    label="📥 Download Excel (.xlsx)",
                    data=output.getvalue(),
                    file_name=f"PREDATOR_{uploaded_file.name.replace('.pdf', '.xlsx')}",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            with ex_col2:
                csv = display_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📄 Download CSV (.csv)",
                    data=csv,
                    file_name=f"PREDATOR_{uploaded_file.name.replace('.pdf', '.csv')}",
                    mime="text/csv",
                    use_container_width=True
                )

if __name__ == "__main__":
    main()
