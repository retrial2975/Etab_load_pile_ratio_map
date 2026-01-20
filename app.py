import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Dashboard V3")

st.title("🏗️ Pile Load Dashboard (Full Export Support)")
st.markdown("---")

# 2. ฟังก์ชันโหลดและเตรียมข้อมูลแบบ Robust (เช็คค่า Z เพื่อหาจุดบนสุด)
@st.cache_data
def process_etabs_data(file):
    # อ่าน Sheet ต่างๆ
    df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
    df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
    df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
    df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])

    # กรองข้อมูลเบื้องต้น
    df_forces = df_forces.dropna(subset=['Unique Name'])
    df_conn = df_conn.dropna(subset=['Unique Name'])
    df_points = df_points.dropna(subset=['UniqueName'])
    df_sect = df_sect.dropna(subset=['UniqueName'])

    # แปลงชนิดข้อมูล
    df_forces['Unique Name'] = df_forces['Unique Name'].astype(int)
    df_forces['P'] = pd.to_numeric(df_forces['P'], errors='coerce')
    df_conn['Unique Name'] = df_conn['Unique Name'].astype(int)
    df_points['UniqueName'] = df_points['UniqueName'].astype(int)
    df_sect['UniqueName'] = df_sect['UniqueName'].astype(int)

    # เชื่อมข้อมูลหาพิกัด X, Y และ Z ของทั้งจุด I และ J
    # เชื่อมจุด I
    df_m = df_conn.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtI', right_on='UniqueName', how='left').rename(columns={'X':'X_I', 'Y':'Y_I', 'Z':'Z_I'})
    # เชื่อมจุด J
    df_m = df_m.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtJ', right_on='UniqueName', how='left', suffixes=('', '_J')).rename(columns={'X':'X_J', 'Y':'Y_J', 'Z':'Z_J'})

    # เลือกจุดที่ Z สูงกว่า (จุดบน)
    # ถ้า Z_J >= Z_I ให้ใช้พิกัด J ถ้าไม่ให้ใช้ I (กรณีกลับหัว)
    df_m['X_Plot'] = np.where(df_m['Z_J'] >= df_m['Z_I'], df_m['X_J'], df_m['X_I'])
    df_m['Y_Plot'] = np.where(df_m['Z_J'] >= df_m['Z_I'], df_m['Y_J'], df_m['Y_I'])
    df_m['Station_Top'] = np.where(df_m['Z_J'] >= df_m['Z_I'], df_m['Length'], 0)

    # ในกรณีที่พิกัดหายไปข้างหนึ่ง (NaN) ให้เอาค่าที่มีมาใช้
    df_m['X_Plot'] = df_m['X_Plot'].fillna(df_m['X_J']).fillna(df_m['X_I'])
    df_m['Y_Plot'] = df_m['Y_Plot'].fillna(df_m['Y_J']).fillna(df_m['Y_I'])

    # เชื่อมหน้าตัด
    df_m = df_m.merge(df_sect[['UniqueName', 'Section Property']], left_on='Unique Name', right_on='UniqueName')

    # ดึงโหลด P ที่ Station บนสุด (Station_Top)
    # ใช้การ Match Station ที่ใกล้เคียงที่สุดเพื่อกัน Error ทศนิยม
    df_final = []
    for _, row in df_m.iterrows():
        u_name = row['Unique Name']
        target_st = row['Station_Top']
        f_subset = df_forces[df_forces['Unique Name'] == u_name]
        if not f_subset.empty:
            # หาแถวที่ Station ใกล้เคียง target_st ที่สุด
            idx = (f_subset['Station'] - target_st).abs().idxmin()
            load_val = abs(f_subset.loc[idx, 'P'])
            row['Load_P'] = round(load_val)
            df_final.append(row)
    
    df_res = pd.DataFrame(df_final)
    
    # สกัดขนาดหน้าตัด
    def extract_dia(name):
        nums = re.findall(r'\d+', str(name))
        return int(nums[0]) if nums else 600
    df_res['Dia_mm'] = df_res['Section Property'].apply(extract_dia)
    
    return df_res

# --- ส่วน UI ---
uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์ Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = process_etabs_data(uploaded_file)
        
        # --- Sidebar ---
        st.sidebar.header("🎨 ตั้งค่าการแสดงผล")
        dot_scale = st.sidebar.slider("ขนาดวงกลม (Base Size)", 5, 30, 10)
        font_size = st.sidebar.slider("ขนาดตัวเลขโหลด", 8, 20, 10)
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("🖼️ ตั้งค่าการเซฟรูป (PNG)")
        img_w = st.sidebar.number_input("ความกว้างภาพ (px)", value=1920)
        img_h = st.sidebar.number_input("ความสูงภาพ (px)", value=1080)

        st.sidebar.markdown("---")
        st.sidebar.subheader("Safe Load (tons)")
        unique_sections = df_raw['Section Property'].unique()
        safe_loads = {sec: st.sidebar.number_input(f"{sec}", value=500.0) for sec in unique_sections}
        
        yellow_limit = st.sidebar.slider("Ratio เหลือง >", 0.0, 1.5, 0.90)
        red_limit = st.sidebar.slider("Ratio แดง >", 0.0, 1.5, 1.00)
        
        # คำนวณ Status
        df_raw['Ratio'] = df_raw.apply(lambda r: r['Load_P'] / safe_loads.get(r['Section Property'], 1.0), axis=1)
        def get_status(r):
            if r >= red_limit: return 'Over Load (Red)'
            elif r >= yellow_limit: return 'Warning (Yellow)'
            return 'Safe (Green)'
        df_raw['Status'] = df_raw['Ratio'].apply(get_status)

        # --- การพล็อต ---
        color_map = {'Over Load (Red)': '#F8766D', 'Warning (Yellow)': '#FFCC00', 'Safe (Green)': '#00BFC4'}
        
        # ปรับขนาดจุดให้สัมพันธ์กับ Dia_mm
        df_raw['Marker_Size'] = (df_raw['Dia_mm'] / df_raw['Dia_mm'].max()) * dot_scale

        fig = px.scatter(
            df_raw, x="X_Plot", y="Y_Plot", color="Status",
            size="Marker_Size", text="Load_P",
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
            plot_bgcolor='white', paper_bgcolor='white',
            xaxis=dict(showgrid=False, zeroline=False, title="X (m)", color="black"),
            yaxis=dict(showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1, color="black"),
            height=800,
            font=dict(color="black"),
            legend=dict(
                title=dict(text='สถานะ / ขนาดเสาเข็ม', font=dict(color='black', size=14)),
                font=dict(family="Arial Black", size=12, color="black"),
                bordercolor="black", borderwidth=1
            )
        )
        
        # --- จุดสำคัญ: ตั้งค่าปุ่ม Download ให้ได้ขนาดตามที่กำหนด ---
        config = {
            'toImageButtonOptions': {
                'format': 'png', # หรือ 'svg', 'jpeg'
                'filename': 'pile_load_map',
                'height': img_h,
                'width': img_w,
                'scale': 2 # ความคมชัด (2 = 2เท่า)
            },
            'displaylogo': False
        }
        
        st.plotly_chart(fig, use_container_width=True, config=config)
        
        st.subheader(f"📊 สรุปข้อมูล (ทั้งหมด {len(df_raw)} ต้น)")
        st.dataframe(df_raw[['Unique Name', 'Section Property', 'Load_P', 'Ratio', 'Status']].sort_values('Ratio', ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error: {e}")
else:
    st.info("☝️ กรุณาอัปโหลดไฟล์ Pile_load2.xlsx")
