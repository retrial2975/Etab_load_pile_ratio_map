import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# ตั้งค่าหน้าเว็บให้กว้างและดูสะอาดตา
st.set_page_config(layout="wide", page_title="Pile Load Dashboard")

st.title("🏗️ Pile Load & Ratio Visualization")
st.markdown("---")

# --- 1. อัปโหลดไฟล์ ---
uploaded_file = st.file_uploader("อัปโหลดไฟล์ Excel จาก ETABS (.xlsx)", type=["xlsx"])

if uploaded_file:
    @st.cache_data
    def load_and_process(file):
        # อ่าน Sheet ต่างๆ (ข้ามบรรทัดหัวตารางและหน่วย)
        df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
        df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
        df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
        df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])

        # เชื่อมข้อมูลหาพิกัด X, Y ที่หัวเสา (Point J)
        df_merged = df_conn.merge(df_points[['UniqueName', 'X', 'Y']], left_on='UniquePtJ', right_on='UniqueName')
        
        # เชื่อมกับ Section Property
        df_merged = df_merged.merge(df_sect[['UniqueName', 'Section Property']], 
                                    left_on='Unique Name', right_on='UniqueName', suffixes=('', '_sect'))
        
        # เชื่อมกับ Forces (ดึงโหลด P ที่ Station ปลายเสา)
        df_forces['Station'] = pd.to_numeric(df_forces['Station'], errors='coerce')
        df_merged['Length'] = pd.to_numeric(df_merged['Length'], errors='coerce')
        
        df_final = df_merged.merge(df_forces, left_on=['Unique Name', 'Length'], right_on=['Unique Name', 'Station'])
        
        # จัดการค่าโหลด (ติดลบคือ Compression ให้ใช้ค่าบวกมาคิด Ratio)
        df_final['Load_P'] = df_final['P'].abs()
        return df_final

    try:
        df_raw = load_and_process(uploaded_file)
        
        # --- 2. ส่วนตั้งค่าที่ Sidebar ---
        st.sidebar.header("🎨 การตั้งค่าเกณฑ์")
        
        # กำหนด Safe Load แยกตามหน้าตัด
        unique_sections = df_raw['Section Property'].unique()
        safe_loads = {}
        st.sidebar.subheader("Safe Load (tons)")
        for sec in unique_sections:
            safe_loads[sec] = st.sidebar.number_input(f"{sec}", value=500.0, step=10.0)
            
        # กำหนดช่วงสี Ratio
        st.sidebar.subheader("เกณฑ์การเปลี่ยนสี (Ratio)")
        yellow_val = st.sidebar.slider("สีเหลือง เมื่อ Ratio เกิน", 0.0, 1.5, 0.90)
        red_val = st.sidebar.slider("สีแดง เมื่อ Ratio เกิน", 0.0, 1.5, 1.00)
        
        # --- 3. คำนวณ Ratio และกำหนดสี ---
        df_raw['Ratio'] = df_raw.apply(lambda r: r['Load_P'] / safe_loads.get(r['Section Property'], 1.0), axis=1)
        
        def get_status(r):
            if r >= red_val: return 'Over Load (Red)'
            elif r >= yellow_val: return 'Warning (Yellow)'
            return 'Safe (Green)'
            
        df_raw['Status'] = df_raw['Ratio'].apply(get_status)

        # --- 4. การพล็อตด้วย Plotly (ggplot Minimal Style) ---
        # สีแบบ ggplot2: Soft Red, Soft Yellow, Soft Teal
        color_map = {
            'Over Load (Red)': '#F8766D', 
            'Warning (Yellow)': '#FFCC00', 
            'Safe (Green)': '#00BFC4'
        }
        
        fig = px.scatter(
            df_raw, x="X", y="Y", 
            color="Status",
            symbol="Section Property",
            text=df_raw['Load_P'].apply(lambda x: f"{x:.1f}"), # แสดงเลขโหลด
            hover_data={'X':False, 'Y':False, 'Column':True, 'Ratio':':.2f'},
            color_discrete_map=color_map,
            category_orders={"Status": ["Safe (Green)", "Warning (Yellow)", "Over Load (Red)"]}
        )
        
        # ปรับแต่ง Marker และ Label (ตัวเลขสีดำ)
        fig.update_traces(
            textposition='top center', 
            marker=dict(size=14, line=dict(width=1, color='DarkSlateGrey')),
            textfont=dict(family="Arial", size=11, color="black") # บังคับตัวเลขเป็นสีดำ
        )
        
        # ปรับ Layout เป็นพื้นหลังขาว Minimal
        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            xaxis=dict(showgrid=False, zeroline=False, title="X (m)"),
            yaxis=dict(showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1),
            height=800,
            font=dict(color="black"),
            legend_title_text='สถานะและหน้าตัดเสา'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # --- 5. ตารางสรุปด้านล่าง ---
        st.subheader("📊 ตารางสรุปข้อมูลเสาเข็ม")
        st.dataframe(df_raw[['Column', 'Section Property', 'Load_P', 'Ratio', 'Status']]
                     .sort_values('Ratio', ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")
        st.info("ตรวจสอบให้แน่ใจว่าไฟล์ Excel มี Sheet ชื่อ: Element Forces - Columns, Column Object Connectivity, Point Object Connectivity, Frame Assigns - Sect Prop")
