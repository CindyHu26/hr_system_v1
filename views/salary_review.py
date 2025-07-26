# views/salary_review.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from services import reporting_logic as logic_report
from db import queries_salary_records as q_records

def show_page(conn):
    st.header("💵 薪資基礎審核")
    st.info("您可以在此預覽並微調每位員工當月份的底薪、勞健保及勞退提撥金額。此處的修改僅影響當前月份。")
    
    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 1, value=last_month.year, key="review_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="review_month")

    if st.button("🔄 讀取/刷新資料", type="primary"):
        with st.spinner("正在讀取薪資基礎資料..."):
            preview_df = logic_report.get_salary_preview_data(conn, year, month)
            st.session_state.salary_preview_df = preview_df
            if preview_df.empty:
                st.warning("資料庫中沒有本月的薪資紀錄，請先至「薪資草稿產生」頁面產生新草稿。")
            st.rerun()

    if 'salary_preview_df' not in st.session_state or st.session_state.salary_preview_df.empty:
        st.info("請點擊「讀取/刷新資料」來開始。")
        return

    st.write("---")
    
    st.markdown("##### 薪資基礎編輯區")
    st.caption("您可以直接在表格中修改數值，修改後的結果將會是本月份薪資單的計算基礎。")
    
    df_to_edit = st.session_state.salary_preview_df
    
    edited_df = st.data_editor(
        df_to_edit,
        use_container_width=True,
        key="salary_preview_editor",
        disabled=["員工姓名"] # 員工姓名不可編輯
    )
    
    if st.button("💾 儲存當月調整", help="將上方表格中的修改儲存至本月份的薪資草稿。"):
        with st.spinner("正在儲存變更..."):
            try:
                # 找出被修改過的行
                comparison_df = df_to_edit.merge(edited_df, on='employee_id', how='left', suffixes=('', '_new'))
                # 檢查是否有任何一欄的值不同
                changed_rows = comparison_df[
                    (comparison_df['底薪'] != comparison_df['底薪_new']) |
                    (comparison_df['勞保費'] != comparison_df['勞保費_new']) |
                    (comparison_df['健保費'] != comparison_df['健保費_new']) |
                    (comparison_df['勞退提撥(公司負擔)'] != comparison_df['勞退提撥(公司負擔)_new'])
                ]

                if not changed_rows.empty:
                    # 只傳遞被修改過的資料到後端進行更新
                    df_to_update = edited_df[edited_df['employee_id'].isin(changed_rows['employee_id'])]
                    count = q_records.update_salary_preview_data(conn, year, month, df_to_update)
                    st.success(f"成功更新了 {count} 位員工的薪資基礎資料！")
                else:
                    st.info("沒有偵測到任何變更。")

            except Exception as e:
                st.error(f"儲存時發生錯誤: {e}")