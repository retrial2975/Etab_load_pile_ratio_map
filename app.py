import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# 1. ตั้งค่าหน้ากระดาษ
st.set_page_config(layout="wide", page_title="Pile Load Dashboard")

# ส่วนหัวโปรแกรม
st.title("🏗️ Pile Load & Ratio Visualization")
st.markdown("โปรแกรมคำนวณ Ratio และ Plot ตำแหน่งเสาเข็มอัตโนมัติจากไฟล์ ETABS")

# 2. ฟังก์ชันโหลดและเตรียมข้อมูล
@st.cache_data
def process_etabs_data(file):
    # อ่าน Sheet ต่างๆ (ข้ามบรรทัด Header Table และ Unit)
    df_forces = pd.read_excel(file, sheet_name="Element Forces - Columns", skiprows=[0, 2])
    df_conn = pd.read_excel(file, sheet_name="Column Object Connectivity", skiprows=[0, 2])
    df_points = pd.read_excel(file, sheet_name="Point Object Connectivity", skiprows=[0, 2])
    df_sect = pd.read_excel(file, sheet_name="Frame Assigns - Sect Prop", skiprows=[0, 2])

    # เชื่อม Column กับ Point J (ตำแหน่งหัวเสา) เพื่อหาพิกัด X, Y
    df_merged = df_conn.merge(df_points[['UniqueName', 'X', 'Y']], left_on='UniquePtJ', right_on='UniqueName')
    
    # เชื่อมหน้าตัดเสา (Section Property)
    df_merged = df_merged.merge(df_sect[['UniqueName', 'Section Property']], 
                                left_on='Unique Name', right_on='UniqueName', suffixes=('', '_sect'))
    
    # ดึงโหลด P ที่ตำแหน่งหัวเสา (Station == Length)
    df_forces['Station'] = pd.to_numeric(df_forces['Station'], errors='coerce')
    df_merged['Length'] = pd.to_numeric(df_merged['Length'], errors='coerce')
    
    df_final = df_merged.merge(df_forces, left_on=['Unique Name', 'Length'], right_on=['Unique Name', 'Station'])
    
    # ใช้ค่า Load สัมบูรณ์ (Absolute) และปัดเป็นเลขจำนวนเต็ม
    df_final['Load_P'] = df_final['P'].abs().round(0).astype(int)
    return df_final

# --- ส่วน UI หลัก ---
uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์ Excel (.xlsx) ที่ Export จาก ETABS", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = process_etabs_data(uploaded_file)
        
        # --- 3. Sidebar ตั้งค่า Safe Load และ Ratio ---
        st.sidebar.header("⚙️ ตั้งค่าเกณฑ์")
        
        unique_sections = df_raw['Section Property'].unique()
        safe_loads = {}
        st.sidebar.subheader("Safe Load (tons)")
        for sec in unique_sections:
            safe_loads[sec] = st.sidebar.number_input(f"หน้าตัด {sec}:", value=500.0, step=10.0)
            
        st.sidebar.subheader("เกณฑ์การแสดงสี (Ratio)")
        yellow_limit = st.sidebar.slider("เริ่มสีเหลืองที่ Ratio >", 0.0, 1.5, 0.90)
        red_limit = st.sidebar.slider("เริ่มสีแดงที่ Ratio >", 0.0, 1.5, 1.00)
        
        # --- 4. การคำนวณ Ratio ---
        # คำนวณ Ratio (เก็บทศนิยมไว้ 2 ตำแหน่งเพื่อความแม่นยำ)
        df_raw['Ratio'] = df_raw.apply(lambda r: r['Load_P'] / safe_loads.get(r['Section Property'], 1.0), axis=1)
        
        def assign_status(r):
            if r >= red_limit: return 'Over Load (Red)'
            elif r >= yellow_limit: return 'Warning (Yellow)'
            return 'Safe (Green)'
            
        df_raw['Status'] = df_raw['Ratio'].apply(assign_status)

        # --- 5. การพล็อต (Minimal ggplot style & No Decimal & Black Legend) ---
        color_map = {
            'Over Load (Red)': '#F8766D', 
            'Warning (Yellow)': '#FFCC00', 
            'Safe (Green)': '#00BFC4'
        }
        
        fig = px.scatter(
            df_raw, x="X", y="Y", 
            color="Status",
            symbol="Section Property",
            text=df_raw['Load_P'], # แสดงเลขโหลด (จำนวนเต็ม)
            hover_data={'X':False, 'Y':False, 'Column':True, 'Section Property':True, 'Ratio':':.2f'},
            color_discrete_map=color_map,
            category_orders={"Status": ["Safe (Green)", "Warning (Yellow)", "Over Load (Red)"]}
        )
        
        # ปรับแต่งตัวอักษรบนจุด (สีดำเข้ม / จำนวนเต็ม)
        fig.update_traces(
            textposition='top center', 
            marker=dict(size=14, line=dict(width=1, color='black')),
            textfont=dict(family="Arial Black", size=12, color="black")
        )
        
        # ปรับ Layout และบังคับ Legend Title ให้เป็นสีดำ
        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            xaxis=dict(showgrid=False, zeroline=False, title="X (m)", color="black"),
            yaxis=dict(showgrid=False, zeroline=False, title="Y (m)", scaleanchor="x", scaleratio=1, color="black"),
            height=850,
            font=dict(color="black"), # บังคับตัวอักษรทั้งกราฟ
            legend=dict(
                font=dict(family="Arial Black", size=13, color="black"), 
                title_font_color="black", # บังคับหัวข้อ Legend เป็นสีดำ
                bgcolor="rgba(255,255,255,0.7)",
                bordercolor="black",
                borderwidth=1
            ),
            legend_title_text='สถานะ / ชนิดหน้าตัด'
        )
        
        # แสดงกราฟ
        st.plotly_chart(fig, use_container_width=True)
        
        # --- 6. ตารางสรุปผล ---
        st.subheader("📊 ตารางสรุปข้อมูลเสาเข็ม")
        st.dataframe(
            df_raw[['Column', 'Section Property', 'Load_P', 'Ratio', 'Status']]
            .sort_values(by='Ratio', ascending=False)
            .style.format({'Load_P': '{:,.0f}', 'Ratio': '{:.2f}'}), # ตารางแสดง Load เป็นเลขจำนวนเต็ม
            use_container_width=True
        )

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
        st.info("ตรวจสอบชื่อ Sheet: Element Forces - Columns, Column Object Connectivity, Point Object Connectivity, Frame Assigns - Sect Prop")

else:
    st.info("☝️ กรุณาอัปโหลดไฟล์ Excel เพื่อเริ่มต้น")
