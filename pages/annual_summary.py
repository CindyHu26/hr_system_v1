# page_annual_summary.py
import streamlit as st
import pandas as pd
from datetime import datetime
from utils_salary_crud import get_all_salary_items
from utils_annual_summary import get_annual_salary_summary, dataframe_to_styled_excel

def show_page(conn):
    st.header("年度薪資總表")
    st.info("此頁面用於檢視整年度特定薪資項目的加總，例如計算公司負擔的二代健保補充保費基數。")

    # --- 1. 篩選條件 ---
    st.subheader("篩選條件")
    c1, c2 = st.columns([1, 3])
    
    with c1:
        current_year = datetime.now().year
        year = st.number_input("選擇年份", min_value=2020, max_value=current_year + 5, value=current_year)

    with c2:
        try:
            # 從資料庫讀取所有薪資項目作為選項
            all_items_df = get_all_salary_items(conn, active_only=True)
            item_options = dict(zip(all_items_df['name'], all_items_df['id']))
            
            # 設定預設選項 (所有非底薪且類型為 earning 的項目)
            default_items = [
                row['name'] for _, row in all_items_df.iterrows() # <--- 已修正
                if row['name'] not in ['底薪', '加班費', '加班費2'] and row['type'] == 'earning'
            ]
            
            selected_item_names = st.multiselect(
                "選擇要加總的薪資項目*",
                options=item_options.keys(),
                default=default_items,
                help="預設選取所有「給付」類型項目（不含底薪與加班費），可用於計算二代健保基數。"
            )
            selected_item_ids = [item_options[name] for name in selected_item_names]

        except Exception as e:
            st.error(f"讀取薪資項目時發生錯誤: {e}")
            selected_item_ids = []

    # --- 2. 執行查詢並顯示結果 ---
    if st.button("產生年度報表", type="primary"):
        if not selected_item_ids:
            st.warning("請至少選擇一個薪資項目！")
        else:
            with st.spinner("正在彙總整年度資料..."):
                summary_df = get_annual_salary_summary(conn, year, selected_item_ids)
                st.session_state.annual_summary_df = summary_df
                # 清除舊的期間總計
                if 'period_sum_df' in st.session_state:
                    del st.session_state.period_sum_df

    # --- 3. 顯示與操作報表 ---
    if 'annual_summary_df' in st.session_state:
        st.write("---")
        st.subheader("報表預覽")
        
        display_df = st.session_state.get('period_sum_df', st.session_state.annual_summary_df)
        st.dataframe(display_df, use_container_width=True)

        # --- 期間加總功能 ---
        with st.expander("📈 計算特定期間加總"):
            sc1, sc2, sc3 = st.columns([1, 1, 2])
            start_month = sc1.number_input("開始月份", min_value=1, max_value=12, value=1)
            end_month = sc2.number_input("結束月份", min_value=1, max_value=12, value=5)
            
            if sc3.button("計算期間總計"):
                if start_month > end_month:
                    st.error("開始月份不能大於結束月份！")
                else:
                    # 複製一份原始的總結資料
                    period_df = st.session_state.annual_summary_df.copy()
                    # 選取要加總的月份欄位
                    months_to_sum = [f'{m}月' for m in range(start_month, end_month + 1)]
                    # 計算總和
                    period_df['期間總計'] = period_df[months_to_sum].sum(axis=1)
                    # 儲存到 session state 供顯示和下載
                    st.session_state.period_sum_df = period_df
                    st.rerun()

        # --- 下載功能 ---
        if not display_df.empty:
            st.write("---")
            st.subheader("下載報表")
            
            # 準備下載用的檔案
            excel_title = f"年度薪資項目總表 ({'、'.join(selected_item_names)})"
            roc_year = year - 1911
            
            excel_data = dataframe_to_styled_excel(
                display_df, 
                title=excel_title,
                roc_year=roc_year
            )
            
            st.download_button(
                label="📥 下載 Excel 報表",
                data=excel_data,
                file_name=f"年度薪資總表_民國{roc_year}年.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )