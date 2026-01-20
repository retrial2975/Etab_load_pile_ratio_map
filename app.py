import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Dashboard V2")

st.title("🏗️ Pile Load Visualization & Export")
st.info("💡 คำแนะนำการถ่ายรูป: เลื่อนเมาส์ไปที่มุมขวาบนของกราฟ แล้วกดปุ่มรูป 'กล้องถ่ายรูป' เพื่อเซฟไฟล์ภาพทั้งแปลน (PNG) โดยที่ภาพไม่ขาด")

# 2. ฟังก์ชันโหลดและเตรียมข้อมูลแบบ Robust
@st.cache_data
def process_etabs_data(file):
    # อ่าน Sheet ต่างๆ
    df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
    df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
    df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
    df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])

    # กรองเอาเฉพาะ Row ที่มีข้อมูลจริง
    df_forces = df_forces.dropna(subset=['Unique Name'])
    df_conn = df_conn.dropna(subset=['Unique Name'])
    df_points = df_points.dropna(subset=['UniqueName'])
    df_sect = df_sect.dropna(subset=['UniqueName'])

    # แปลงชนิดข้อมูล
    df_forces['Unique Name'] = df_forces['Unique Name'].astype(int)
    df_forces['P'] = pd.to_numeric(df_forces['P'], errors='coerce')
    df_forces['Station'] = pd.to_numeric(df_forces['Station'], errors='coerce')
    
    df_conn['Unique Name'] = df_conn['Unique Name'].astype(int)
    df_conn['UniquePtJ'] = df_conn['UniquePtJ'].astype(int)
    
    df_points['UniqueName'] = df_points['UniqueName'].astype(int)
    df_sect['UniqueName'] = df_sect['UniqueName'].astype(int)

    # 1. เชื่อมหน้าตัดก่อน
    df_master = df_sect[['UniqueName', 'Section Property']].merge(
        df_conn[['Unique Name', 'UniquePtJ', 'Length']], 
        left_on='UniqueName', right_on='Unique Name'
    )

    # 2. เชื่อมพิกัด X, Y จาก Point J (หัวเสา)
    df_master = df_master.merge(df_points[['UniqueName', 'X', 'Y']], left_on='UniquePtJ', right_on='UniqueName', suffixes=('', '_pt'))

    # 3. ดึงโหลด P (เลือก Station ที่มากที่สุดของแต่ละ Unique Name เพื่อเอาค่าที่หัวเสา)
    # วิธีนี้จะแก้ปัญหาพิกัดมาไม่ครบเนื่องจาก Station ไม่ Match
    df_top_forces = df_forces.sort_values('Station').groupby('Unique Name').tail(1)
    df_final = df_master.merge(df_top_forces[['Unique Name', 'P']], on='Unique Name')

    # จัดการค่าโหลดและขนาดหน้าตัด
    df_final['Load_P'] = df_final['P'].abs().round(0).astype(int)
    
    def extract_dia(name):
        nums = re.findall(r'\d+', str(name))
        return int(nums[0]) if nums else 600
    df_final['Dia_mm'] = df_final['Section Property'].apply(extract_dia)
    
    return df_final

# --- ส่วน UI ---
uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์ Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = process_etabs_data(uploaded_file)
        
        # --- Sidebar สำหรับปรับจูน ---
        st.sidebar.header("🎨 ปรับแต่งการแสดงผล")
        
        # ตัวปรับขนาดจุดและตัวอักษร
        dot_size = st.sidebar.slider("ขนาดวงกลม (Circle Size)", 5, 50, 15)
        font_size = st.sidebar.slider("ขนาดตัวเลขโหลด (Font Size)", 8, 24, 12)
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Safe Load (tons)")
        unique_sections = df_raw['Section Property'].unique()
        safe_loads = {}
        for sec in unique_sections:
            safe_loads[sec] = st.sidebar.number_input(f"{sec}", value=500.0, step=10.0)
            
        yellow_limit = st.sidebar.slider("Ratio สีเหลือง >", 0.0, 1.5, 0.90)
        red_limit = st.sidebar.slider("Ratio สีแดง >", 0.0, 1.5, 1.00)
        
        # คำนวณ Ratio
        df_raw['Ratio'] = df_raw.apply(lambda r: r['Load_P'] / safe_loads.get(r['Section Property'], 1.0), axis=1)
        
        def get_status(r):
            if r >= red_limit: return 'Over Load (Red)'
            elif r >= yellow_limit: return 'Warning (Yellow)'
            return 'Safe (Green)'
        df_raw['Status'] = df_raw['Ratio'].apply(get_status)

        # --- การพล็อต ---
        color_map = {
            'Over Load (Red)': '#F8766D', 
            'Warning (Yellow)': '#FFCC00', 
            'Safe (Green)': '#00BFC4'
        }
        
        # ปรับขนาดจุดตาม Dia_mm โดยใช้พื้นฐานจากที่ User เลือก
        df_raw['Marker_Size'] = (df_raw['Dia_mm'] / df_raw['Dia_mm'].max()) * dot_size

        fig = px.scatter(
            df_raw, x="X", y="Y", 
            color="Status",
            size="Marker_Size",
            text=df_raw['Load_P'],
            hover_data={'X':True, 'Y':True, 'Unique Name':True, 'Section Property':True, 'Ratio':':.2f', 'Marker_Size':False},
            color_discrete_map=color_map,
            category_orders={"Status": ["Safe (Green)", "Warning (Yellow)", "Over Load (Red)"]}
        )
        
        fig.update_traces(
            mode='markers+text',
            marker=dict(symbol='circle', line=dict(width=1, color='black')),
            textposition='top center', 
            textfont=dict(family="Arial Black", size=font_size, color="black")
        )
        
        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            xaxis=dict(showgrid=False, zeroline=False, title="X (m)", color="black"),
            yaxis=dict(showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1, color="black"),
            margin=dict(l=20, r=20, t=50, b=20),
            height=900,
            font=dict(color="black"),
            legend=dict(
                title_font_color="black",
                font=dict(family="Arial Black", size=14, color="black"),
                bgcolor="rgba(255,255,255,0.7)",
                bordercolor="black",
                borderwidth=1
            ),
            legend_title_text='สถานะ / ขนาดเสาเข็ม'
        )
        
        st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False, 'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'eraseshape']})
        
        # --- ตารางสรุป ---
        st.subheader(f"📊 ตารางสรุป (พบเสาเข็มทั้งหมด {len(df_raw)} ต้น)")
        st.dataframe(
            df_raw[['Unique Name', 'Section Property', 'Load_P', 'Ratio', 'Status']]
            .sort_values(by='Ratio', ascending=False)
            .style.format({'Load_P': '{:,.0f}', 'Ratio': '{:.2f}'}),
            use_container_width=True
        )

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
        st.info("ตรวจสอบว่าไฟล์ Excel มี Sheet ครบ และไม่มีบรรทัดว่างที่หัวตารางมากเกินไป")

else:
    st.info("☝️ กรุณาอัปโหลดไฟล์ Pile_load2.xlsx เพื่อตรวจสอบ")
