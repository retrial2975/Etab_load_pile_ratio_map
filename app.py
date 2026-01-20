import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

st.set_page_config(layout="wide", page_title="Pile Load Visualization")

st.title("🏗️ Pile Load & Ratio Visualization")

# --- 1. Upload File ---
uploaded_file = st.file_uploader("Upload ETABS Excel File", type=["xlsx"])

if uploaded_file:
    # อ่านข้อมูลจาก Sheets ต่างๆ
    @st.cache_data
    def load_data(file):
        # ข้ามบรรทัดแรกที่เป็นชื่อตาราง และบรรทัดที่สองที่เป็นหน่วย (Units) ในบางไฟล์
        df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
        df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
        df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
        df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])
        return df_forces, df_conn, df_points, df_sect

    try:
        df_forces, df_conn, df_points, df_sect = load_data(uploaded_file)
        
        # --- 2. Data Processing & Merging ---
        # เชื่อม Column กับ Point (หาพิกัด X, Y ที่ Point J ซึ่งเป็นหัวเสา)
        df_merged = df_conn.merge(df_points[['UniqueName', 'X', 'Y']], left_on='UniquePtJ', right_on='UniqueName')
        
        # เชื่อมกับ Section Property
        df_merged = df_merged.merge(df_sect[['UniqueName', 'Section Property']], left_on='Unique Name', right_on='UniqueName', suffixes=('', '_sect'))
        
        # เชื่อมกับ Forces (ดึงโหลด P ที่หัวเสา: Station == Length)
        # ปรับค่า Station และ Length ให้เป็นตัวเลขเพื่อความแม่นยำในการ Match
        df_forces['Station'] = pd.to_numeric(df_forces['Station'], errors='coerce')
        df_merged['Length'] = pd.to_numeric(df_merged['Length'], errors='coerce')
        
        df_final = df_merged.merge(df_forces, left_on=['Unique Name', 'Length'], right_on=['Unique Name', 'Station'])
        
        # ค่าโหลด P (ติดลบคือ Compression) -> ใช้ค่าสัมบูรณ์ในการคิด Ratio
        df_final['Load_P'] = df_final['P'].abs()
        
        # --- 3. Configuration Sidebar ---
        st.sidebar.header("Settings")
        
        # กำหนด Safe Load สำหรับแต่ละหน้าตัด
        unique_sections = df_final['Section Property'].unique()
        safe_loads = {}
        st.sidebar.subheader("Define Safe Load (tons)")
        for sec in unique_sections:
            safe_loads[sec] = st.sidebar.number_input(f"Safe Load for {sec}", value=500.0, step=10.0)
            
        # กำหนดเกณฑ์ Ratio สำหรับสี
        st.sidebar.subheader("Ratio Thresholds")
        yellow_thresh = st.sidebar.slider("Yellow Threshold (Ratio > x)", 0.0, 1.5, 0.90)
        red_thresh = st.sidebar.slider("Red Threshold (Ratio > x)", 0.0, 1.5, 1.00)
        
        # --- 4. Calculation ---
        def calculate_ratio(row):
            s_load = safe_loads.get(row['Section Property'], 1.0)
            ratio = row['Load_P'] / s_load
            return ratio

        df_final['Ratio'] = df_final.apply(calculate_ratio, axis=1)
        
        def assign_color(ratio):
            if ratio >= red_thresh: return 'Over Load (Red)'
            elif ratio >= yellow_thresh: return 'Warning (Yellow)'
            else: return 'Safe (Green)'
            
        df_final['Status'] = df_final['Ratio'].apply(assign_color)

        # --- 5. Visualization ---
        color_map = {
            'Over Load (Red)': '#FF0000',
            'Warning (Yellow)': '#FFD700',
            'Safe (Green)': '#008000'
        }
        
        fig = px.scatter(
            df_final, 
            x="X", y="Y", 
            color="Status",
            symbol="Section Property",
            text=df_final['Load_P'].round(1),
            hover_data=['Column', 'Section Property', 'Ratio'],
            color_discrete_map=color_map,
            title="Pile Load Layout Plan"
        )
        
        fig.update_traces(textposition='top center', marker=dict(size=12))
        fig.update_layout(
            plot_bgcolor='white',
            xaxis=dict(showgrid=False, zeroline=False, title="X (m)"),
            yaxis=dict(showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1),
            height=800
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # --- 6. Summary Table ---
        st.subheader("Summary Table")
        st.dataframe(df_final[['Column', 'Section Property', 'Load_P', 'Ratio', 'Status']].sort_values(by='Ratio', ascending=False))

    except Exception as e:
        st.error(f"Error processing file: {e}")
        st.info("โปรดตรวจสอบว่าชื่อ Sheet ในไฟล์ Excel ตรงกับ: 'Element Forces - Columns', 'Column Object Connectivity', 'Point Object Connectivity', 'Frame Assigns - Sect Prop'")
