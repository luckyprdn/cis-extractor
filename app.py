import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

# --- CONFIG & THEME ---
st.set_page_config(
    page_title="CIS Extractor Pro",
    page_icon="🛡️",
    layout="wide"
)

# Custom CSS untuk tampilan Flat & Modern
st.markdown("""
    <style>
    /* Main Background */
    .stApp {
        background-color: #f8f9fa;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e0e0e0;
    }
    
    /* Card-like containers */
    div.stButton > button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        background-color: #007bff;
        color: white;
        border: none;
        transition: all 0.3s ease;
        font-weight: 600;
    }
    
    div.stButton > button:hover {
        background-color: #0056b3;
        border: none;
        color: white;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    
    /* File Uploader styling */
    section[data-testid="stFileUploadDropzone"] {
        background-color: #ffffff;
        border: 2px dashed #007bff;
        border-radius: 12px;
    }

    /* Header styling */
    h1 {
        color: #1e293b;
        font-weight: 800 !important;
    }
    
    .stAlert {
        border-radius: 10px;
        border: none;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# --- LOGIC EXTRACTION ---
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
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
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
                        "Level": "N/A", "Description": "N/A", "Rationale": "N/A",
                        "Audit": "N/A", "Remediation": "N/A", "section": None
                    }
                    if "(L1)" in title_full: current_rule["Level"] = "Level 1"
                    elif "(L2)" in title_full: current_rule["Level"] = "Level 2"
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
        if current_rule and current_rule['Description'] != "N/A":
            rules.append(current_rule)
    return rules

# --- UI LAYOUT ---
with st.sidebar:
    st.image("https://www.cisecurity.org/hubfs/cis-logo.svg", width=150) # Pakai logo CIS biar legit
    st.title("Settings")
    st.info("Alat ini mengekstrak aturan dari dokumen CIS Benchmark menjadi file Excel yang siap pakai untuk audit.")
    st.divider()
    st.caption("Developed for IT Governance Efficiency")

# Main Content
st.title("🛡️ CIS Benchmark Extractor")
st.markdown("Automated Extraction for **Security Compliance Audits**")

col1, col2 = st.columns([2, 1])

with col1:
    uploaded_files = st.file_uploader("Upload PDF Benchmarks (Bisa multi-file)", type="pdf", accept_multiple_files=True)

with col2:
    st.subheader("Instructions")
    st.write("1. Upload satu atau lebih PDF.")
    st.write("2. Tunggu proses ekstraksi selesai.")
    st.write("3. Klik tombol download untuk hasil XLSX.")

if uploaded_files:
    st.divider()
    output = io.BytesIO()
    total_rules = 0
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for uploaded_file in uploaded_files:
            with st.status(f"Processing {uploaded_file.name}...", expanded=True) as status:
                data = extract_cis(uploaded_file)
                if data:
                    df = pd.DataFrame(data).drop(columns=['section'])
                    df = df[df['Description'] != "N/A"]
                    sheet_name = uploaded_file.name[:30].replace(".pdf", "").replace("CIS_", "")
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    st.write(f"✅ Found {len(df)} rules")
                    total_rules += len(df)
                status.update(label=f"Done: {uploaded_file.name}", state="complete")
    
    if total_rules > 0:
        st.balloons()
        st.success(f"Total {total_rules} aturan berhasil diekstrak!")
        st.download_button(
            label="🚀 DOWNLOAD EXCEL RESULT",
            data=output.getvalue(),
            file_name="CIS_Compliance_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Tidak ada aturan valid yang ditemukan. Pastikan PDF adalah dokumen CIS Benchmark asli.")