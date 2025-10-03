# views/employee_report.py
import streamlit as st
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from db import queries_report as q_report # 引用我們剛剛建立的新查詢檔案
import io

def show_page(conn):
    st.header("📋 員工基本資料報表")
    st.info("用於篩選特定加保公司的在職員工，並匯出其基本資料，例如用於年度體檢名單。")

    try:
        # 為了提升效能，將載入的資料暫存在 session_state 中
        if 'employee_basic_data' not in st.session_state:
            with st.spinner("正在載入員工資料..."):
                st.session_state.employee_basic_data = q_report.get_employee_basic_data_for_report(conn)
        
        df_raw = st.session_state.employee_basic_data
        
        # 增加一個判斷，先確認 df_raw 不是 None，再檢查是否為 empty
        if df_raw is None or df_raw.empty:
            st.warning("資料庫中沒有在職員工的資料可供查詢。")
            return

        # --- 篩選器 ---
        st.subheader("篩選條件")
        # 從已載入的資料中動態產生公司列表
        all_companies = ['所有公司'] + sorted(df_raw['加保公司'].dropna().unique().tolist())
        selected_company = st.selectbox(
            "選擇加保公司",
            options=all_companies
        )

        # --- 根據篩選結果處理資料 ---
        if selected_company == '所有公司':
            df_filtered = df_raw.copy()
        else:
            df_filtered = df_raw[df_raw['加保公司'] == selected_company].copy()

        if not df_filtered.empty:
            # --- 計算年齡 ---
            today = date.today()
            # 將生日欄位轉換為日期格式，以便計算
            df_filtered['birth_date_dt'] = pd.to_datetime(df_filtered['生日'], errors='coerce')
            
            # 使用 apply 函式逐行計算年齡
            df_filtered['年齡'] = df_filtered['birth_date_dt'].apply(
                lambda x: relativedelta(today, x.date()).years if pd.notna(x) else 0
            )

            # --- 顯示報表 ---
            st.subheader("報表預覽")
            display_cols = ['加保公司', '員工姓名', '身分證字號', '到職日', '生日', '年齡']
            st.dataframe(df_filtered[display_cols], hide_index=True)

            # --- 下載功能 ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_filtered[display_cols].to_excel(writer, index=False, sheet_name='員工基本資料')
            
            st.download_button(
                label="📥 下載 Excel 報表",
                data=output.getvalue(),
                file_name=f"員工基本資料報表_{selected_company}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"產生報表時發生錯誤: {e}")