import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Dashboard V5")

st.title("🏗️ Pile Load Visualization (Fixed Export)")
st.markdown("---")

# 2. ฟังก์ชันเตรียมข้อมูล (Smart Mapping เพื่อให้ครบ 201 ต้น)
@st.cache_data
def process_etabs_data(file):
    df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
    df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
    df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
    df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])

    # คลีนข้อมูลเบื้องต้น
    df_forces['Unique Name'] = pd.to_numeric(df_forces['Unique Name'], errors='coerce')
    df_conn['Unique Name'] = pd.to_numeric(df_conn['Unique Name'], errors='coerce')
    df_points['UniqueName'] = pd.to_numeric(df_points['UniqueName'], errors='coerce')
    df_sect['UniqueName'] = pd.to_numeric(df_sect['UniqueName'], errors='coerce')

    # เชื่อมข้อมูลพิกัด (X, Y) โดยเช็คทั้งจุด I และ J เพื่อความครบถ้วน
    df_m = df_sect[['UniqueName', 'Section Property', 'Label']].rename(columns={'UniqueName': 'Unique Name'})
    df_m = df_m.merge(df_conn[['Unique Name', 'UniquePtI', 'UniquePtJ', 'Length']], on='Unique Name', how='left')
    
    # ดึงพิกัดจากตาราง Point
    df_m = df_m.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtJ', right_on='UniqueName', how='left').rename(columns={'X':'X_J', 'Y':'Y_J', 'Z':'Z_J'})
    df_m = df_m.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtI', right_on='UniqueName', how='left', suffixes=('', '_I')).rename(columns={'X':'X_I', 'Y':'Y_I', 'Z':'Z_I'})

    # เลือกพิกัดหัวเสา (Z สูงกว่า) หรือตัวที่หาเจอ
    df_m['X_Plot'] = df_m['X_J'].fillna(df_m['X_I'])
    df_m['Y_Plot'] = df_m['Y_J'].fillna(df_m['Y_I'])
    
    # ดึงโหลด P (ปัดเป็นจำนวนเต็ม)
    df_forces['P'] = pd.to_numeric(df_forces['P'], errors='coerce')
    # หาค่า P ที่หัวเสา (สมมติว่าเป็นโหลดแรกสุดหรือท้ายสุดที่เจอ)
    df_load = df_forces.sort_values(['Unique Name', 'Station']).groupby('Unique Name').head(1)
    df_final = df_m.merge(df_load[['Unique Name', 'P']], on='Unique Name', how='left')
    df_final['Load_P'] = df_final['P'].abs().fillna(0).round(0).astype(int)

    # สกัดขนาด Dia_mm
    def extract_dia(name):
        nums = re.findall(r'\d+', str(name))
        return int(nums[0]) if nums else 600
    df_final['Dia_mm'] = df_final['Section Property'].apply(extract_dia)
    
    return df_final

# --- ส่วน UI ---
uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์ Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = process_etabs_data(uploaded_file).dropna(subset=['X_Plot'])
        
        # --- Sidebar ---
        st.sidebar.header("🎨 ตั้งค่าภาพบันทึก (PNG)")
        # ตั้งค่าขนาดภาพให้กว้างๆ เพื่อให้ครอบคลุมทุกพิกัดเวลาเซฟ
        img_w = st.sidebar.number_input("ความกว้างภาพบันทึก (Pixels)", value=3000)
        img_h = st.sidebar.number_input("ความสูงภาพบันทึก (Pixels)", value=2000)
        export_scale = st.sidebar.slider("ความคมชัด (Scale)", 1, 5, 2)
        
        st.sidebar.markdown("---")
        dot_scale = st.sidebar.slider("ขนาดวงกลมบนจอ", 5, 50, 20)
        font_size = st.sidebar.slider("ขนาดตัวเลขโหลด", 6, 20, 10)

        st.sidebar.markdown("---")
        st.sidebar.subheader("Safe Load (tons)")
        safe_loads = {sec: st.sidebar.number_input(f"{sec}", value=500.0) for sec in df_raw['Section Property'].unique()}
        
        yellow_limit = st.sidebar.slider("Ratio เหลือง >", 0.0, 1.5, 0.90)
        red_limit = st.sidebar.slider("Ratio แดง >", 0.0, 1.5, 1.00)
        
        # คำนวณ Status
        df_raw['Ratio'] = df_raw['Load_P'] / df_raw['Section Property'].map(safe_loads)
        df_raw['Status'] = df_raw['Ratio'].apply(lambda r: 'Over Load (Red)' if r >= red_limit else ('Warning (Yellow)' if r >= yellow_limit else 'Safe (Green)'))

        # --- Plotting ---
        color_map = {'Over Load (Red)': '#F8766D', 'Warning (Yellow)': '#FFCC00', 'Safe (Green)': '#00BFC4'}
        df_raw['Marker_Size'] = (df_raw['Dia_mm'] / df_raw['Dia_mm'].max()) * dot_scale

        fig = px.scatter(
            df_raw, x="X_Plot", y="Y_Plot", color="Status",
            size="Marker_Size", text="Load_P",
            color_discrete_map=color_map,
            category_orders={"Status": ["Safe (Green)", "Warning (Yellow)", "Over Load (Red)"]}
        )
        
        # บังคับทุกอย่างเป็นสีดำ
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
            height=850,
            font=dict(color="black"),
            legend=dict(
                title=dict(text='สถานะ / ขนาดเสาเข็ม', font=dict(color='black', size=14)),
                font=dict(family="Arial Black", size=12, color="black"),
                bordercolor="black", borderwidth=1
            )
        )

        # --- จุดแก้ไขเรื่องการบันทึกภาพ ---
        # เราตั้งค่าขอบเขตแกน X และ Y ให้พอดีกับ Data ทั้งหมดแบบอัตโนมัติ
        margin_x = (df_raw['X_Plot'].max() - df_raw['X_Plot'].min()) * 0.1
        margin_y = (df_raw['Y_Plot'].max() - df_raw['Y_Plot'].min()) * 0.1
        
        fig.update_xaxes(range=[df_raw['X_Plot'].min() - margin_x, df_raw['X_Plot'].max() + margin_x])
        fig.update_yaxes(range=[df_raw['Y_Plot'].min() - margin_y, df_raw['Y_Plot'].max() + margin_y])

        config = {
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'Complete_Pile_Layout',
                'height': img_h,
                'width': img_w,
                'scale': export_scale # เพิ่มความละเอียดภาพ
            },
            'displaylogo': False
        }
        
        st.plotly_chart(fig, use_container_width=True, config=config)
        
        st.subheader(f"📊 สรุปข้อมูล (พบทั้งหมด {len(df_raw)} ต้น)")
        st.dataframe(df_raw[['Unique Name', 'Label', 'Section Property', 'Load_P', 'Ratio', 'Status']].sort_values('Ratio', ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error: {e}")
else:
    st.info("☝️ กรุณาอัปโหลดไฟล์ Excel เพื่อแสดงผล")
