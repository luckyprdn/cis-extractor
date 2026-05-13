import streamlit as st
import pandas as pd
import polars as pl
import plotly.express as px
import io
import os
import re
from concurrent.futures import ProcessPoolExecutor

# --- (Backend Titan Engine tetap sama seperti sebelumnya) ---
# ... (Gunakan fungsi run_titan_engine dan worker dari versi sebelumnya) ...

def main():
    st.set_page_config(page_title="Titan CIS Analyzer", layout="wide", initial_sidebar_state="expanded")
    
    # Custom CSS buat tampilan lebih pro
    st.markdown("""
        <style>
        .main { background-color: #f5f7f9; }
        .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        </style>
    """, unsafe_allow_value=True)

    st.title("🛡️ Titan CIS Analyzer")
    st.subheader("Enterprise-Grade Policy & Benchmark Extractor")

    with st.sidebar:
        st.header("⚙️ Engine Configuration")
        cores = st.slider("Parallel Processing Cores", 1, os.cpu_count(), 4)
        st.divider()
        st.markdown("### Metadata Options")
        include_ref = st.checkbox("Extract References", value=True)
        st.info("Titan Engine v9.0 Active")

    # Multi-file uploader
    uploaded_files = st.file_uploader("Upload CIS Benchmark PDFs (Support Multiple Files)", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        if st.button("⚡ Run Titan Extraction", type="primary"):
            all_dfs = []
            
            with st.status("Running Titan Parallel Engine...", expanded=True) as status:
                for uploaded_file in uploaded_files:
                    st.write(f"Processing: {uploaded_file.name}")
                    file_bytes = uploaded_file.read()
                    df_result = run_titan_engine(file_bytes, cores) # Panggil backend titan lo
                    
                    if df_result is not None:
                        # Tambahin kolom sumber file
                        df_pd = df_result.to_pandas()
                        df_pd['Source File'] = uploaded_file.name
                        all_dfs.append(df_pd)
                
                if all_dfs:
                    master_df = pd.concat(all_dfs, ignore_index=True)
                    st.session_state['master_df'] = master_df
                    status.update(label="Extraction Success!", state="complete")
                else:
                    st.error("No data extracted. Check PDF format.")

    # --- DASHBOARD & INTERACTIVE AREA ---
    if 'master_df' in st.session_state:
        df = st.session_state['master_df']
        
        st.divider()
        
        # 1. Dashboard Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Rules", len(df))
        with col2:
            l1_count = len(df[df['Level'].str.contains('Level 1', na=False)])
            st.metric("Level 1 Controls", l1_count)
        with col3:
            l2_count = len(df[df['Level'].str.contains('Level 2', na=False)])
            st.metric("Level 2 Controls", l2_count)
        with col4:
            st.metric("Files Processed", df['Source File'].nunique())

        # 2. Visualizations
        c1, c2 = st.columns([1, 1])
        with c1:
            fig_pie = px.pie(df, names='Level', title='Distribution of Controls Level', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            # Bar chart per kategori (berdasarkan Rule ID digit pertama)
            df['Category'] = df['Rule ID'].str.split('.').str[0]
            fig_bar = px.bar(df.groupby('Category').size().reset_index(name='count'), 
                             x='Category', y='count', title='Controls by Main Category',
                             color_discrete_sequence=['#00CC96'])
            st.plotly_chart(fig_bar, use_container_width=True)

        # 3. Data Explorer with Search
        st.markdown("### 🔍 Data Explorer")
        search_query = st.text_input("Search in Title, Description, or Audit procedure...", "")
        
        if search_query:
            filtered_df = df[
                df.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
            ]
        else:
            filtered_df = df

        st.dataframe(filtered_df, use_container_width=True, height=400)

        # 4. Export Options
        st.markdown("### 💾 Export Results")
        ex_col1, ex_col2, ex_col3 = st.columns(3)
        
        # Excel Export
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
            filtered_df.to_excel(writer, index=False, sheet_name='CIS_Master')
        
        with ex_col1:
            st.download_button("Download Excel (.xlsx)", data=output_excel.getvalue(), 
                               file_name="CIS_Master_Extract.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
        
        # CSV Export
        csv_data = filtered_df.to_csv(index=False).encode('utf-8')
        with ex_col2:
            st.download_button("Download CSV (.csv)", data=csv_data, 
                               file_name="CIS_Master_Extract.csv", mime="text/csv", use_container_width=True)
            
        # JSON Export (Buat integrasi ke sistem lain)
        json_data = filtered_df.to_json(orient='records')
        with ex_col3:
            st.download_button("Download JSON (.json)", data=json_data, 
                               file_name="CIS_Master_Extract.json", mime="application/json", use_container_width=True)

if __name__ == "__main__":
    main()
