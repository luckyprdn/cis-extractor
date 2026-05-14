import streamlit as st
import pandas as pd
import time
from backend.titan_engine import extract_cis_data

st.set_page_config(page_title="Upload Center", layout="wide")
st.title("☁️ Secure Upload Center")
st.markdown("Upload multiple CIS Benchmark PDFs for high-speed parsing.")

uploaded_files = st.file_uploader("Drop PDF Benchmarks here", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("🚀 EXECUTE TITAN ENGINE", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, file in enumerate(uploaded_files):
            status_text.text(f"Processing [{idx+1}/{len(uploaded_files)}]: {file.name} ...")
            start_time = time.time()
            
            pdf_bytes = file.read()
            result = extract_cis_data(pdf_bytes) # Call Backend
            
            end_time = time.time()
            
            if result:
                df = pd.DataFrame(result["data"])
                st.session_state.uploaded_files_data[file.name] = {
                    "dataframe": df, "report": result["report"], "processing_time": round(end_time - start_time, 2)
                }
                st.session_state.execution_logs.append(f"[SUCCESS] {file.name} parsed in {round(end_time - start_time, 2)}s")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        status_text.text("✅ All files processed successfully. Data is ready in memory.")
        st.success("Extraction Complete.")
