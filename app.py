import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Pro V8")

st.title("🏗️ Pile Load Visualization (V8 - Individual Scaling)")
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
        st.sidebar.header("📏 1. ปรับขนาดสัญลักษณ์แยกหน้าตัด")
        custom_sizes = {}
        for sec in unique_sections:
            custom_sizes[sec] = st.sidebar.slider(f"ขนาดจุด: {sec}", 5, 100, 25)
        
        font_size = st.sidebar.slider("ขนาดตัวเลขโหลด", 6, 30, 12)

        st.sidebar.markdown("---")
        st.sidebar.header("⚖️ 2. ตั้งค่า Safe Load & Ratio")
        safe_loads = {sec: st.sidebar.number_input(f"Safe Load: {sec} (tons)", value=500.0) for sec in unique_sections}
        
        yellow_limit = st.sidebar.slider("เกณฑ์สีเหลือง (Ratio > )", 0.0, 1.5, 0.90)
        red_limit = st.sidebar.slider("เกณฑ์สีแดง (Ratio > )", 0.0, 1.5, 1.00)

        st.sidebar.markdown("---")
        st.sidebar.header("🖼️ 3. การบันทึกภาพ (PNG Export)")
        export_w = st.sidebar.number_input("ความกว้างภาพบันทึก (Pixels)", value=2500)
        
        # คำนวณ Aspect Ratio อัตโนมัติจากพิกัดจริง
        dx = df_raw['X_Plot'].max() - df_raw['X_Plot'].min()
        dy = df_raw['Y_Plot'].max() - df_raw['Y_Plot'].min()
        project_ratio = dx / dy if dy != 0 else 1
        export_h = int(export_w / project_ratio)
        st.sidebar.info(f"ความสูงบันทึกอัตโนมัติ (เพื่อให้พอดี): {export_h} px")
        export_scale = st.sidebar.slider("ความคมชัด (Scale)", 1, 4, 2)

        # --- Calculation ---
        df_raw['Marker_Size'] = df_raw['Section Property'].map(custom_sizes)
        df_raw['Ratio'] = df_raw['Load_P'] / df_raw['Section Property'].map(safe_loads)
        
        def assign_status(r):
            if r >= red_limit: return 'Over Load (Red)'
            elif r >= yellow_limit: return 'Warning (Yellow)'
            return 'Safe (Green)'
        df_raw['Status'] = df_raw['Ratio'].apply(assign_status)

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
        
        # ปรับขอบเขตให้พอดีข้อมูลที่สุด (Margin 3% เพื่อไม่ให้จุดโดนตัดขอบ)
        margin = 0.03
        fig.update_xaxes(range=[df_raw['X_Plot'].min() - (dx*margin), df_raw['X_Plot'].max() + (dx*margin)], 
                         showgrid=False, zeroline=False, title="X (m)", color="black")
        fig.update_yaxes(range=[df_raw['Y_Plot'].min() - (dy*margin), df_raw['Y_Plot'].max() + (dy*margin)], 
                         showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1, color="black")

        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=850,
            font=dict(color="black"),
            legend=dict(
                title=dict(text='สถานะ / หน้าตัด', font=dict(color='black', size=14)),
                font=dict(family="Arial Black", size=12, color="black"),
                bordercolor="black", borderwidth=1
            )
        )

        # Config สำหรับปุ่ม Save PNG
        config = {
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'Pile_Load_Plan',
                'height': export_h,
                'width': export_w,
                'scale': export_scale
            },
            'displaylogo': False
        }
        
        st.plotly_chart(fig, use_container_width=True, config=config)
        
        st.subheader(f"📊 ตารางสรุปข้อมูล (เสาเข็มทั้งหมด {len(df_raw)} ต้น)")
        st.dataframe(df_raw[['Unique Name', 'Label', 'Section Property', 'Load_P', 'Ratio', 'Status']].sort_values('Ratio', ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error: {e}")
else:
    st.info("☝️ กรุณาอัปโหลดไฟล์ Excel เพื่อแสดงผล")
