import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Pro V7")

st.title("🏗️ Pile Load Visualization & Manual Crop")
st.markdown("---")

# 2. ฟังก์ชันเตรียมข้อมูล (Robust Mapping)
@st.cache_data
def process_etabs_data(file):
    df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
    df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
    df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
    df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])

    for df in [df_forces, df_conn, df_points, df_sect]:
        df.columns = df.columns.str.strip()
        if 'Unique Name' in df.columns: df['Unique Name'] = pd.to_numeric(df['Unique Name'], errors='coerce')
        if 'UniqueName' in df.columns: df['UniqueName'] = pd.to_numeric(df['UniqueName'], errors='coerce')

    df_master = df_sect[['UniqueName', 'Section Property', 'Label']].rename(columns={'UniqueName': 'Unique Name'})
    df_master = df_master.merge(df_conn[['Unique Name', 'UniquePtI', 'UniquePtJ']], on='Unique Name', how='left')

    df_master = df_master.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtJ', right_on='UniqueName', how='left').rename(columns={'X':'X_J', 'Y':'Y_J', 'Z':'Z_J'}).drop(columns='UniqueName')
    df_master = df_master.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtI', right_on='UniqueName', how='left', suffixes=('', '_I')).rename(columns={'X':'X_I', 'Y':'Y_I', 'Z':'Z_I'}).drop(columns='UniqueName')

    df_master['X_Plot'] = df_master['X_J'].fillna(df_master['X_I'])
    df_master['Y_Plot'] = df_master['Y_J'].fillna(df_master['Y_I'])
    
    mask_both = df_master['Z_I'].notna() & df_master['Z_J'].notna()
    df_master.loc[mask_both, 'X_Plot'] = np.where(df_master.loc[mask_both, 'Z_J'] >= df_master.loc[mask_both, 'Z_I'], df_master.loc[mask_both, 'X_J'], df_master.loc[mask_both, 'X_I'])
    df_master.loc[mask_both, 'Y_Plot'] = np.where(df_master.loc[mask_both, 'Z_J'] >= df_master.loc[mask_both, 'Z_I'], df_master.loc[mask_both, 'Y_J'], df_master.loc[mask_both, 'Y_I'])

    df_forces['P'] = pd.to_numeric(df_forces['P'], errors='coerce')
    df_load = df_forces.sort_values(['Unique Name', 'Station']).groupby('Unique Name').head(1)
    df_final = df_master.merge(df_load[['Unique Name', 'P']], on='Unique Name', how='left')
    df_final['Load_P'] = df_final['P'].abs().fillna(0).round(0).astype(int)
    
    return df_final.dropna(subset=['X_Plot'])

# --- UI Logic ---
uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์ Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = process_etabs_data(uploaded_file)
        unique_sections = sorted(df_raw['Section Property'].unique())

        # --- Sidebar ---
        st.sidebar.header("🎨 1. ปรับขนาดวงกลมแยกหน้าตัด")
        custom_sizes = {}
        for sec in unique_sections:
            custom_sizes[sec] = st.sidebar.slider(f"ขนาดจุด: {sec}", 5, 100, 25)
        
        font_size = st.sidebar.slider("ขนาดตัวเลขโหลด", 6, 30, 12)

        st.sidebar.markdown("---")
        st.sidebar.header("✂️ 2. เลือกช่วงพิกัดที่จะ Crop")
        
        # ตั้งค่าช่วงพิกัดสำหรับการ Crop
        min_x, max_x = float(df_raw['X_Plot'].min()), float(df_raw['X_Plot'].max())
        min_y, max_y = float(df_raw['Y_Plot'].min()), float(df_raw['Y_Plot'].max())
        
        x_range = st.sidebar.slider("เลือกช่วงแกน X (m)", min_x - 5, max_x + 5, (min_x, max_x))
        y_range = st.sidebar.slider("เลือกช่วงแกน Y (m)", min_y - 5, max_y + 5, (min_y, max_y))

        st.sidebar.markdown("---")
        st.sidebar.header("🖼️ 3. ตั้งค่าการบันทึกภาพ")
        export_w = st.sidebar.number_input("ความกว้างภาพ (Pixels)", value=2500)
        # คำนวณสัดส่วนตามช่วงที่เรา Crop
        crop_dx = x_range[1] - x_range[0]
        crop_dy = y_range[1] - y_range[0]
        ratio = crop_dx / crop_dy if crop_dy != 0 else 1
        export_h = int(export_w / ratio)
        st.sidebar.info(f"ความสูงบันทึกอัตโนมัติ: {export_h} px")

        st.sidebar.markdown("---")
        st.sidebar.subheader("Safe Load (tons)")
        safe_loads = {sec: st.sidebar.number_input(f"Safe: {sec}", value=500.0) for sec in unique_sections}
        
        # คำนวณ Ratio
        df_raw['Marker_Size'] = df_raw['Section Property'].map(custom_sizes)
        df_raw['Ratio'] = df_raw['Load_P'] / df_raw['Section Property'].map(safe_loads)
        df_raw['Status'] = df_raw['Ratio'].apply(lambda r: 'Over Load (Red)' if r >= 1.0 else ('Warning (Yellow)' if r >= 0.9 else 'Safe (Green)'))

        # --- Plotting ---
        color_map = {'Over Load (Red)': '#F8766D', 'Warning (Yellow)': '#FFCC00', 'Safe (Green)': '#00BFC4'}

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
        
        # บังคับช่วงพิกัดตามที่ User เลือก Crop
        fig.update_xaxes(range=[x_range[0], x_range[1]], showgrid=False, zeroline=False, title="X (m)", color="black")
        fig.update_yaxes(range=[y_range[0], y_range[1]], showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1, color="black")

        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=900,
            font=dict(color="black"),
            legend=dict(
                title=dict(text='สถานะ / ขนาดเสาเข็ม', font=dict(color='black', size=14)),
                font=dict(family="Arial Black", size=12, color="black"),
                bordercolor="black", borderwidth=1
            )
        )

        config = {
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'Pile_Layout_Custom_Crop',
                'height': export_h,
                'width': export_w,
                'scale': 2
            },
            'displaylogo': False
        }
        
        st.plotly_chart(fig, use_container_width=True, config=config)
        
        st.subheader("📊 ข้อมูลเสาเข็มทั้งหมด")
        st.dataframe(df_raw[['Unique Name', 'Label', 'Section Property', 'Load_P', 'Ratio', 'Status']].sort_values('Ratio', ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error: {e}")
else:
    st.info("☝️ กรุณาอัปโหลดไฟล์ Excel เพื่อแสดงผล")
