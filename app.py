import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Dashboard")

# ส่วนหัวโปรแกรม
st.title("🏗️ Pile Load & Ratio Visualization")
st.markdown("ระบบแสดงผลโหลดเสาเข็ม: จุดวงกลมขนาดตามหน้าตัดจริง และสีตาม Ratio")

# 2. ฟังก์ชันโหลดและเตรียมข้อมูล
@st.cache_data
def process_etabs_data(file):
    df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
    df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
    df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
    df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])

    # เชื่อมข้อมูลหาพิกัด X, Y
    df_merged = df_conn.merge(df_points[['UniqueName', 'X', 'Y']], left_on='UniquePtJ', right_on='UniqueName')
    df_merged = df_merged.merge(df_sect[['UniqueName', 'Section Property']], 
                                left_on='Unique Name', right_on='UniqueName', suffixes=('', '_sect'))
    
    # ดึงโหลด P ที่ตำแหน่งหัวเสา
    df_forces['Station'] = pd.to_numeric(df_forces['Station'], errors='coerce')
    df_merged['Length'] = pd.to_numeric(df_merged['Length'], errors='coerce')
    df_final = df_merged.merge(df_forces, left_on=['Unique Name', 'Length'], right_on=['Unique Name', 'Station'])
    
    # ปัดโหลดเป็นจำนวนเต็ม
    df_final['Load_P'] = df_final['P'].abs().round(0).astype(int)

    # --- ฟังก์ชันสกัดขนาดหน้าตัด (Diameter) มาเป็นตัวเลข ---
    def extract_diameter(name):
        nums = re.findall(r'\d+', str(name))
        return int(nums[0]) if nums else 600 # ถ้าไม่เจอเลขให้ Default ที่ 600

    df_final['Dia_mm'] = df_final['Section Property'].apply(extract_diameter)
    
    return df_final

# --- ส่วน UI หลัก ---
uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์ Excel (.xlsx) ที่ Export จาก ETABS", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = process_etabs_data(uploaded_file)
        
        # --- 3. Sidebar ตั้งค่า Safe Load ---
        st.sidebar.header("⚙️ ตั้งค่าเกณฑ์")
        unique_sections = df_raw['Section Property'].unique()
        safe_loads = {}
        for sec in unique_sections:
            safe_loads[sec] = st.sidebar.number_input(f"Safe Load: {sec}", value=500.0, step=10.0)
            
        yellow_limit = st.sidebar.slider("เริ่มสีเหลืองที่ Ratio >", 0.0, 1.5, 0.90)
        red_limit = st.sidebar.slider("เริ่มสีแดงที่ Ratio >", 0.0, 1.5, 1.00)
        
        # --- 4. คำนวณ Ratio ---
        df_raw['Ratio'] = df_raw.apply(lambda r: r['Load_P'] / safe_loads.get(r['Section Property'], 1.0), axis=1)
        
        def assign_status(r):
            if r >= red_limit: return 'Over Load (Red)'
            elif r >= yellow_limit: return 'Warning (Yellow)'
            return 'Safe (Green)'
            
        df_raw['Status'] = df_raw['Ratio'].apply(assign_status)

        # --- 5. การพล็อต (วงกลมขนาดตามหน้าตัด & สีมินิมอล & ตัวอักษรดำ) ---
        color_map = {
            'Over Load (Red)': '#F8766D', 
            'Warning (Yellow)': '#FFCC00', 
            'Safe (Green)': '#00BFC4'
        }
        
        # ใช้ px.scatter โดยกำหนด size เป็น Dia_mm
        fig = px.scatter(
            df_raw, x="X", y="Y", 
            color="Status",
            size="Dia_mm", # ขนาดจุดเปลี่ยนตามขนาดหน้าตัด
            size_max=18,   # กำหนดขนาดจุดที่ใหญ่ที่สุดให้พอเหมาะ
            text=df_raw['Load_P'], 
            hover_data={'X':False, 'Y':False, 'Column':True, 'Section Property':True, 'Ratio':':.2f', 'Dia_mm':False},
            color_discrete_map=color_map,
            category_orders={"Status": ["Safe (Green)", "Warning (Yellow)", "Over Load (Red)"]}
        )
        
        # บังคับให้สัญลักษณ์เป็นวงกลมทั้งหมด (Circle) และตัวหนังสือสีดำ
        fig.update_traces(
            mode='markers+text',
            marker=dict(symbol='circle', line=dict(width=1, color='black')), # ขอบดำ
            textposition='top center', 
            textfont=dict(family="Arial Black", size=12, color="black") # ตัวหนังสือดำหนา
        )
        
        # ปรับ Layout และ Legend
        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            xaxis=dict(showgrid=False, zeroline=False, title="X (m)", color="black"),
            yaxis=dict(showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1, color="black"),
            height=850,
            font=dict(color="black"), # บังคับตัวอักษรทั้งกราฟ
            legend=dict(
                title_font_color="black", # หัวข้อ Legend สีดำ
                font=dict(family="Arial Black", size=13, color="black"), # รายละเอียด Legend สีดำ
                bgcolor="rgba(255,255,255,0.7)",
                bordercolor="black",
                borderwidth=1
            ),
            legend_title_text='สถานะ / ขนาดเสาเข็ม'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # --- 6. ตารางสรุป ---
        st.subheader("📊 ตารางสรุปข้อมูลเสาเข็ม")
        st.dataframe(
            df_raw[['Column', 'Section Property', 'Load_P', 'Ratio', 'Status']]
            .sort_values(by='Ratio', ascending=False)
            .style.format({'Load_P': '{:,.0f}', 'Ratio': '{:.2f}'}),
            use_container_width=True
        )

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
        st.info("ตรวจสอบชื่อ Sheet ให้ถูกต้อง")

else:
    st.info("☝️ กรุณาอัปโหลดไฟล์ Excel เพื่อเริ่มต้น")
