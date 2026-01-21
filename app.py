import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Multi-Select V11")

st.title("🏗️ Pile Load Dashboard (Multi-Select & Custom Envelope)")
st.markdown("---")

# 2. ฟังก์ชันเตรียมข้อมูล
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

    # เชื่อมพิกัด X, Y
    df_m = df_sect[['UniqueName', 'Section Property', 'Label']].rename(columns={'UniqueName': 'Unique Name'})
    df_m = df_m.merge(df_conn[['Unique Name', 'UniquePtI', 'UniquePtJ']], on='Unique Name', how='left')
    df_m = df_m.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtJ', right_on='UniqueName', how='left').rename(columns={'X':'X_J', 'Y':'Y_J', 'Z':'Z_J'}).drop(columns='UniqueName')
    df_m = df_m.merge(df_points[['UniqueName', 'X', 'Y', 'Z']], left_on='UniquePtI', right_on='UniqueName', how='left', suffixes=('', '_I')).rename(columns={'X':'X_I', 'Y':'Y_I', 'Z':'Z_I'}).drop(columns='UniqueName')

    df_m['X_Plot'] = df_m['X_J'].fillna(df_m['X_I'])
    df_m['Y_Plot'] = df_m['Y_J'].fillna(df_m['Y_I'])
    mask_both = df_m['Z_I'].notna() & df_m['Z_J'].notna()
    df_m.loc[mask_both, 'X_Plot'] = np.where(df_m.loc[mask_both, 'Z_J'] >= df_m.loc[mask_both, 'Z_I'], df_m.loc[mask_both, 'X_J'], df_m.loc[mask_both, 'X_I'])
    df_m.loc[mask_both, 'Y_Plot'] = np.where(df_m.loc[mask_both, 'Z_J'] >= df_m.loc[mask_both, 'Z_I'], df_m.loc[mask_both, 'Y_J'], df_m.loc[mask_both, 'Y_I'])

    # เตรียมแรง P ทุกเคส (Station หัวเสา)
    df_forces['P'] = pd.to_numeric(df_forces['P'], errors='coerce')
    df_forces_top = df_forces.sort_values(['Unique Name', 'Output Case', 'Station']).groupby(['Unique Name', 'Output Case']).head(1)
    
    return df_m.dropna(subset=['X_Plot']), df_forces_top

# --- UI Logic ---
uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์ Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        df_base, df_all_forces = process_etabs_data(uploaded_file)
        unique_sections = sorted(df_base['Section Property'].unique())
        all_cases = sorted(df_all_forces['Output Case'].unique())

        # --- Sidebar ---
        st.sidebar.header("📊 1. เลือก Combinations")
        
        # ปุ่ม Select All
        select_all = st.sidebar.checkbox("เลือกทั้งหมด (Select All Cases)")
        if select_all:
            selected_cases = st.sidebar.multiselect("เลือก Load Combinations", all_cases, default=all_cases)
        else:
            selected_cases = st.sidebar.multiselect("เลือก Load Combinations", all_cases, default=[all_cases[0]] if all_cases else [])

        if not selected_cases:
            st.warning("⚠️ กรุณาเลือกอย่างน้อย 1 Load Combination ในแถบด้านข้าง")
            st.stop()

        display_mode = st.sidebar.radio("แสดงผลบนแผนที่", ["Load (P)", "Ratio (2 decimal)"])

        st.sidebar.markdown("---")
        st.sidebar.header("⚖️ 2. Safe Load Settings")
        safe_comp, safe_tens = {}, {}
        for sec in unique_sections:
            with st.sidebar.expander(f"หน้าตัด {sec}"):
                safe_comp[sec] = st.number_input(f"Safe Compression", value=500.0, key=f"c_{sec}")
                safe_tens[sec] = st.number_input(f"Safe Tension", value=50.0, key=f"t_{sec}")

        y_lim = st.sidebar.slider("Ratio เหลือง >", 0.0, 1.5, 0.90)
        r_lim = st.sidebar.slider("Ratio แดง >", 0.0, 1.5, 1.00)

        st.sidebar.markdown("---")
        st.sidebar.header("🎨 3. Visual Settings")
        dot_sizes = {sec: st.sidebar.slider(f"ขนาดจุด: {sec}", 5, 80, 20) for sec in unique_sections}
        font_size = st.sidebar.slider("ขนาดฟอนต์บน Map", 6, 25, 11)

        # --- Logic: Calculation ---
        df_merged = df_all_forces.merge(df_base[['Unique Name', 'Section Property', 'X_Plot', 'Y_Plot', 'Label']], on='Unique Name')
        
        # กรองเฉพาะเคสที่เลือก
        df_filtered = df_merged[df_merged['Output Case'].isin(selected_cases)].copy()
        
        def do_calc(row):
            is_t = row['P'] > 0
            limit = safe_tens[row['Section Property']] if is_t else safe_comp[row['Section Property']]
            ratio = abs(row['P']) / (limit if limit != 0 else 1)
            return pd.Series([ratio, is_t])

        df_filtered[['Ratio', 'Is_Tension']] = df_filtered.apply(do_calc, axis=1)

        # หาค่าวิกฤตที่สุด (Envelope) ของกลุ่มที่เลือก
        df_final = df_filtered.sort_values('Ratio').groupby('Unique Name').tail(1).copy()

        # สร้าง Label สำหรับแผนที่
        if "Ratio" in display_mode:
            df_final['Map_Label'] = df_final.apply(lambda r: f"{r['Ratio']:.2f}{' (T)' if r['Is_Tension'] else ''}", axis=1)
        else:
            df_final['Map_Label'] = df_final.apply(lambda r: f"{int(abs(r['P']))}{' (T)' if r['Is_Tension'] else ''}", axis=1)

        df_final['Status'] = df_final['Ratio'].apply(lambda r: 'Over Load (Red)' if r >= r_lim else ('Warning (Yellow)' if r >= y_lim else 'Safe (Green)'))
        df_final['Marker_Size'] = df_final['Section Property'].map(dot_sizes)

        # --- Plotting ---
        color_map = {'Over Load (Red)': '#F8766D', 'Warning (Yellow)': '#FFCC00', 'Safe (Green)': '#00BFC4'}
        
        fig = px.scatter(
            df_final, x="X_Plot", y="Y_Plot", color="Status",
            size="Marker_Size", text="Map_Label",
            hover_data=['Label', 'Output Case', 'P', 'Ratio'],
            color_discrete_map=color_map,
            category_orders={"Status": ["Safe (Green)", "Warning (Yellow)", "Over Load (Red)"]}
        )
        
        fig.update_traces(
            mode='markers+text',
            marker=dict(symbol='circle', line=dict(width=df_final['Is_Tension'].map({True:3, False:1}), color='black')),
            textposition='top center', 
            textfont=dict(family="Arial Black", size=font_size, color="black")
        )
        
        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=850,
            xaxis=dict(showgrid=False, zeroline=False, title="X (m)", color="black"),
            yaxis=dict(showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1, color="black"),
            legend=dict(title=dict(text='สถานะ / รูปแบบแรง', font=dict(color='black', size=14)), font=dict(family="Arial Black", size=12, color="black"), bordercolor="black", borderwidth=1)
        )

        st.plotly_chart(fig, use_container_width=True, config={'toImageButtonOptions': {'height': 1500, 'width': 2500, 'scale': 2}})
        
        st.subheader(f"📊 ตารางสรุป: วิกฤตที่สุดจาก {len(selected_cases)} Combinations ที่เลือก")
        df_final['Type'] = df_final['Is_Tension'].map({True: 'Tension (ดึง)', False: 'Compression (อัด)'})
        st.dataframe(df_final[['Label', 'Section Property', 'Type', 'Output Case', 'P', 'Ratio', 'Status']].sort_values('Ratio', ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error: {e}")
else:
    st.info("☝️ กรุณาอัปโหลดไฟล์ Excel เพื่อเริ่มต้น")
