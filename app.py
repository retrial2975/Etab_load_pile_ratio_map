import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Perfect Fit")

st.title("🏗️ Pile Load Visualization & Perfect Crop")
st.markdown("---")

# 2. ฟังก์ชันเตรียมข้อมูล (Robust Mapping)
@st.cache_data
def process_etabs_data(file):
    # อ่าน Sheet ต่างๆ
    df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
    df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
    df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
    df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])

    # คลีนข้อมูลและแปลง Type
    for df in [df_forces, df_conn, df_points, df_sect]:
        df.columns = df.columns.str.strip()
        if 'Unique Name' in df.columns:
            df['Unique Name'] = pd.to_numeric(df['Unique Name'], errors='coerce')
        if 'UniqueName' in df.columns:
            df['UniqueName'] = pd.to_numeric(df['UniqueName'], errors='coerce')

    # รวมฐานข้อมูลพิกัด
    df_master = df_sect[['UniqueName', 'Section Property', 'Label']].rename(columns={'UniqueName': 'Unique Name'})
    df_master = df_master.merge(df_conn[['Unique Name', 'UniquePtI', 'UniquePtJ', 'Length']], on='Unique Name', how='left')

    # ดึงพิกัดจากตาราง Point (X, Y, Z)
    df_master = df_master.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtJ', right_on='UniqueName', how='left').rename(columns={'X':'X_J', 'Y':'Y_J', 'Z':'Z_J'}).drop(columns='UniqueName')
    df_master = df_master.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtI', right_on='UniqueName', how='left', suffixes=('', '_I')).rename(columns={'X':'X_I', 'Y':'Y_I', 'Z':'Z_I'}).drop(columns='UniqueName')

    # เลือกพิกัดหัวเสา (Z สูงกว่า) หรือตัวที่หาเจอเพื่อความครบถ้วน
    df_master['X_Plot'] = df_master['X_J'].fillna(df_master['X_I'])
    df_master['Y_Plot'] = df_master['Y_J'].fillna(df_master['Y_I'])
    
    # กรณีที่มีพิกัดทั้งคู่ ให้เลือกตัวที่ Z สูงกว่า
    mask_both = df_master['Z_I'].notna() & df_master['Z_J'].notna()
    df_master.loc[mask_both, 'X_Plot'] = np.where(df_master.loc[mask_both, 'Z_J'] >= df_master.loc[mask_both, 'Z_I'], df_master.loc[mask_both, 'X_J'], df_master.loc[mask_both, 'X_I'])
    df_master.loc[mask_both, 'Y_Plot'] = np.where(df_master.loc[mask_both, 'Z_J'] >= df_master.loc[mask_both, 'Z_I'], df_master.loc[mask_both, 'Y_J'], df_master.loc[mask_both, 'Y_I'])

    # ดึงโหลด P และปัดเป็นจำนวนเต็ม
    df_forces['P'] = pd.to_numeric(df_forces['P'], errors='coerce')
    df_load = df_forces.sort_values(['Unique Name', 'Station']).groupby('Unique Name').head(1)
    df_final = df_master.merge(df_load[['Unique Name', 'P']], on='Unique Name', how='left')
    df_final['Load_P'] = df_final['P'].abs().fillna(0).round(0).astype(int)

    # สกัดขนาด Dia_mm
    def extract_dia(name):
        nums = re.findall(r'\d+', str(name))
        return int(nums[0]) if nums else 600
    df_final['Dia_mm'] = df_final['Section Property'].apply(extract_dia)
    
    return df_final.dropna(subset=['X_Plot'])

# --- UI Logic ---
uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์ Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = process_etabs_data(uploaded_file)
        
        # --- Sidebar สำหรับปรับแต่ง ---
        st.sidebar.header("🎨 ตั้งค่าการแสดงผล")
        dot_scale = st.sidebar.slider("ขนาดวงกลมบนจอ", 5, 50, 20)
        font_size = st.sidebar.slider("ขนาดตัวเลขโหลด", 6, 20, 10)

        st.sidebar.markdown("---")
        st.sidebar.subheader("🖼️ ตั้งค่าการบันทึกภาพ (Export)")
        
        # คำนวณ Aspect Ratio อัตโนมัติจากข้อมูลจริง
        dx = df_raw['X_Plot'].max() - df_raw['X_Plot'].min()
        dy = df_raw['Y_Plot'].max() - df_raw['Y_Plot'].min()
        project_ratio = dx / dy if dy != 0 else 1
        
        st.sidebar.write(f"สัดส่วนโครงการจริง (X:Y) = {project_ratio:.2f}:1")
        
        # ช่องกรอกความกว้าง และคำนวณความสูงที่ Crop พอดีให้
        export_w = st.sidebar.number_input("ความกว้างภาพบันทึก (Pixels)", value=3000)
        auto_h = int(export_w / project_ratio)
        export_h = st.sidebar.number_input("ความสูงภาพบันทึก (Auto-Calc)", value=auto_h)
        export_scale = st.sidebar.slider("ความคมชัด (Scale)", 1, 4, 2)

        st.sidebar.markdown("---")
        st.sidebar.subheader("Safe Load (tons)")
        safe_loads = {sec: st.sidebar.number_input(f"{sec}", value=500.0) for sec in df_raw['Section Property'].unique()}
        
        yellow_lim = st.sidebar.slider("Ratio เหลือง >", 0.0, 1.5, 0.90)
        red_lim = st.sidebar.slider("Ratio แดง >", 0.0, 1.5, 1.00)
        
        # คำนวณ Ratio และ Status
        df_raw['Ratio'] = df_raw['Load_P'] / df_raw['Section Property'].map(safe_loads)
        df_raw['Status'] = df_raw['Ratio'].apply(lambda r: 'Over Load (Red)' if r >= red_lim else ('Warning (Yellow)' if r >= yellow_lim else 'Safe (Green)'))

        # --- Plotting ---
        color_map = {'Over Load (Red)': '#F8766D', 'Warning (Yellow)': '#FFCC00', 'Safe (Green)': '#00BFC4'}
        df_raw['Marker_Size'] = (df_raw['Dia_mm'] / df_raw['Dia_mm'].max()) * dot_scale

        fig = px.scatter(
            df_raw, x="X_Plot", y="Y_Plot", color="Status",
            size="Marker_Size", text="Load_P",
            color_discrete_map=color_map,
            category_orders={"Status": ["Safe (Green)", "Warning (Yellow)", "Over Load (Red)"]}
        )
        
        # บังคับทุกส่วนเป็นสีดำ
        fig.update_traces(
            mode='markers+text',
            marker=dict(symbol='circle', line=dict(width=1, color='black')),
            textposition='top center', 
            textfont=dict(family="Arial Black", size=font_size, color="black")
        )
        
        # ปรับขอบเขตให้ชิดจุดที่สุด (Margin 2%)
        margin_val = 0.02
        fig.update_xaxes(range=[df_raw['X_Plot'].min() - (dx * margin_val), df_raw['X_Plot'].max() + (dx * margin_val)], 
                         showgrid=False, zeroline=False, title="X (m)", color="black")
        fig.update_yaxes(range=[df_raw['Y_Plot'].min() - (dy * margin_val), df_raw['Y_Plot'].max() + (dy * margin_val)], 
                         showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1, color="black")

        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=850,
            font=dict(color="black"),
            legend=dict(
                title=dict(text='สถานะ / ขนาดเสาเข็ม', font=dict(color='black', size=14)),
                font=dict(family="Arial Black", size=12, color="black"),
                bordercolor="black", borderwidth=1
            )
        )

        # Config สำหรับปุ่ม Save PNG
        config = {
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'Pile_Layout_Perfect_Fit',
                'height': export_h,
                'width': export_w,
                'scale': export_scale
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
