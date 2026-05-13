import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import plotly.express as px
from datetime import datetime

# --- CONFIG & THEME ---
st.set_page_config(page_title="CIS Extractor Pro", page_icon="🛡️", layout="wide")

# Custom CSS Ultra Modern
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    * { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #fcfcfd; }
    [data-testid="stMetricValue"] { font-size: 28px; font-weight: 800; color: #1e293b; }
    .footer { position: fixed; left: 0; bottom: 0; width: 100%; background: white; text-align: center; padding: 10px; font-size: 12px; border-top: 1px solid #f1f5f9; z-index: 99; }
    </style>
    """, unsafe_allow_html=True)

# --- CORE LOGIC ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r'Page \d+', '', text)
    text = re.sub(r'Internal Only - General', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_cis(pdf_file):
    rules = []
    current_rule = None
    sections = ["Profile Applicability", "Description", "Rationale", "Audit", "Remediation"]
    
    with pdfplumber.open(pdf_file) as pdf:
        total_pages = len(pdf.pages)
        progress_bar = st.progress(0)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                lines = text.split('\n')
                for line in lines:
                    header_match = re.search(r'^(\d+\.\d+(?:\.\d+)+)\s+(.*)', line)
                    if header_match:
                        if current_rule and current_rule['Description'] != "N/A":
                            rules.append(current_rule)
                        rule_id = header_match.group(1)
                        title_full = header_match.group(2)
                        if "...." in title_full or len(title_full) < 5:
                            current_rule = None; continue
                        current_rule = {
                            "ID": rule_id, "Title": clean_text(title_full.split('(')[0]),
                            "Level": "N/A", "Status": "Manual", "Description": "N/A",
                            "Rationale": "N/A", "Audit": "N/A", "Remediation": "N/A", "section": None
                        }
                        if "(L1)" in title_full: current_rule["Level"] = "Level 1"
                        elif "(L2)" in title_full: current_rule["Level"] = "Level 2"
                        if "(Automated)" in title_full: current_rule["Status"] = "Automated"
                        continue

                    if current_rule:
                        found_new = False
                        for sec in sections:
                            if line.strip().startswith(sec):
                                current_rule["section"] = sec
                                content = line.replace(sec, "").replace(":", "").strip()
                                if content:
                                    key = "Level" if sec == "Profile Applicability" else sec
                                    current_rule[key] = content
                                found_new = True; break
                        if found_new: continue
                        cur_sec = current_rule["section"]
                        if cur_sec:
                            key = "Level" if cur_sec == "Profile Applicability" else cur_sec
                            existing = "" if current_rule[key] == "N/A" else current_rule[key]
                            current_rule[key] = clean_text(existing + " " + line)
            progress_bar.progress((i + 1) / total_pages)
        if current_rule and current_rule['Description'] != "N/A":
            rules.append(current_rule)
    return rules

# --- UI CONTENT ---
with st.sidebar:
    st.markdown("### 🛡️ CIS Extractor Pro")
    st.caption("v4.0 - Intelligence Edition")
    st.divider()
    uploaded_files = st.file_uploader("Upload PDF Benchmarks", type="pdf", accept_multiple_files=True)
    st.divider()
    st.caption("Developed by Lucky Pradana")

st.title("Automated Compliance Intelligence")

if not uploaded_files:
    st.info("Silakan upload satu atau lebih file PDF di sidebar untuk memulai analisa.")
else:
    all_dfs = {}
    total_rules_all = 0
    
    for uploaded_file in uploaded_files:
        with st.expander(f"📦 Data: {uploaded_file.name}", expanded=True):
            data = extract_cis(uploaded_file)
            if data:
                df = pd.DataFrame(data).drop(columns=['section'])
                df = df[df['Description'] != "N/A"]
                all_dfs[uploaded_file.name] = df
                total_rules_all += len(df)
                
                # Metrics
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Rules", len(df))
                m2.metric("Automated", len(df[df['Status'] == 'Automated']))
                m3.metric("Manual", len(df[df['Status'] == 'Manual']))
                
                # Charts
                c1, c2 = st.columns(2)
                with c1:
                    fig_status = px.pie(df, names='Status', title='Status Distribution', hole=0.4, color_discrete_sequence=px.colors.qualitative.Slate)
                    st.plotly_chart(fig_status, use_container_width=True)
                with c2:
                    # Clean level data for chart
                    level_counts = df['Level'].value_counts().reset_index()
                    fig_level = px.bar(level_counts, x='Level', y='count', title='Rules by Level', color='Level', color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig_level, use_container_width=True)

                # Search Data
                search_query = st.text_input(f"Cari aturan di {uploaded_file.name}...", key=uploaded_file.name)
                if search_query:
                    df_display = df[df.apply(lambda row: search_query.lower() in row.astype(str).str.lower().values, axis=1)]
                else:
                    df_display = df.head(10) # Tampilkan 10 teratas
                
                st.dataframe(df_display, use_container_width=True)

    # --- GLOBAL DOWNLOAD ---
    if all_dfs:
        st.divider()
        st.subheader("📥 Export Final Report")
        col_dl1, col_dl2 = st.columns(2)
        
        # Excel Export
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            for name, df_content in all_dfs.items():
                sheet_name = name[:30].replace(".pdf", "").replace("CIS_", "")
                df_content.to_excel(writer, sheet_name=sheet_name, index=False)
        
        col_dl1.download_button(
            label="🚀 DOWNLOAD FULL XLSX REPORT",
            data=output_excel.getvalue(),
            file_name=f"CIS_Intelligence_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # CSV Export (Gabungan)
        combined_df = pd.concat(all_dfs.values())
        col_dl2.download_button(
            label="📄 DOWNLOAD COMBINED CSV",
            data=combined_df.to_csv(index=False).encode('utf-8'),
            file_name=f"CIS_Combined_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# --- FOOTER ---
st.markdown(f"""
    <div class="footer">
        <p>© {datetime.now().year} Lucky Pradana | IT Governance</p>
    </div>
    """, unsafe_allow_html=True)