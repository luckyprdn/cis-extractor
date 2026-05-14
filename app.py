import streamlit as st
import os

st.set_page_config(page_title="Titan Extractor", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

local_css("assets/cyber_style.css")

if "uploaded_files_data" not in st.session_state:
    st.session_state.uploaded_files_data = {}
if "execution_logs" not in st.session_state:
    st.session_state.execution_logs = []

st.sidebar.markdown("## 🛡️ TITAN CORE")
st.sidebar.markdown("### CIS Benchmark Intelligence")
st.sidebar.markdown("---")
st.sidebar.info("Gunakan menu di atas untuk navigasi.")

st.title("⚡ TITAN CIS BENCHMARK EXTRACTOR")
st.markdown("### Enterprise Cybersecurity Dashboard")
st.markdown("""
Sistem ekstraksi dan intelijen CIS Benchmark otomatis berbasis **Titan Engine**.
Silakan navigasikan ke **Upload Center** di sidebar untuk memulai ekstraksi.
""")

st.markdown('<div class="titan-branding">TITAN EXTRACTOR v5.0 | Powered by Lucky Pradana</div>', unsafe_allow_html=True)
