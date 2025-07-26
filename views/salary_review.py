# views/salary_review.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from db import queries_salary_records as q_records
from db import queries_employee as q_emp

def show_page(conn):
    st.header("💵 薪資單審核與調整")
    st.info("您可以在此頁面審查、微調由系統產生的薪資草稿，並執行最終的鎖定操作。")
    
    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 1, value=last_month.year, key="review_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="review_month")

    if st.button("🔄 讀取/刷新薪資資料", type="primary"):
        with st.spinner("正在從資料庫讀取薪資報表..."):
            report_df, item_types = q_records.get_salary_report_for_editing(conn, year, month)
            st.session_state.salary_review_df = report_df
            if report_df.empty:
                st.warning("資料庫中沒有本月的薪資紀錄，請先至「薪資草稿產生」頁面產生新草稿。")
            st.rerun()

    if 'salary_review_df' not in st.session_state or st.session_state.salary_review_df.empty:
        st.info("請點擊「讀取/刷新薪資資料」來開始。")
        return

    st.write("---")
    
    df_to_edit = st.session_state.salary_review_df
    
    st.markdown("##### 薪資單編輯區")
    st.caption("您可以直接在表格中修改 `draft` 狀態的紀錄。`final` 狀態的紀錄已鎖定。")
    
    edited_df = st.data_editor(
        df_to_edit.style.apply(lambda row: ['background-color: #f0f2f6'] * len(row) if row.status == 'final' else [''] * len(row), axis=1),
        use_container_width=True,
        key="salary_review_editor"
    )
    
    st.write("---")
    
    btn_c1, btn_c2 = st.columns(2)

    with btn_c1:
        draft_to_save = edited_df[edited_df['status'] == 'draft']
        if st.button("💾 儲存草稿變更", disabled=draft_to_save.empty):
            with st.spinner("正在儲存草稿..."):
                q_records.save_salary_draft(conn, year, month, draft_to_save)
                st.success("草稿已成功儲存！")
                st.rerun()

    with btn_c2:
        draft_to_finalize = edited_df[edited_df['status'] == 'draft']
        if st.button("🔒 儲存並鎖定最終版本", type="primary", disabled=draft_to_finalize.empty):
            with st.spinner("正在寫入並鎖定最終薪資單..."):
                q_records.finalize_salary_records(conn, year, month, draft_to_finalize)
                st.success(f"{year}年{month}月的薪資單已成功定版！")
                st.rerun()

    with st.expander("⚠️ 進階操作 (解鎖)"):
        final_records = edited_df[edited_df['status'] == 'final']
        if not final_records.empty:
            emp_map_df = q_emp.get_all_employees(conn)
            emp_map = emp_map_df.set_index('name_ch')['id'].to_dict()
            final_records['id'] = final_records['員工姓名'].map(emp_map)
            
            options = final_records['員工姓名'].tolist()
            to_unlock = st.multiselect("選擇要解鎖的員工紀錄", options=options)
            
            if st.button("解鎖選定員工紀錄"):
                if not to_unlock:
                    st.warning("請至少選擇一位要解鎖的員工。")
                else:
                    ids_to_unlock = final_records[final_records['員工姓名'].isin(to_unlock)]['id'].tolist()
                    count = q_records.revert_salary_to_draft(conn, year, month, ids_to_unlock)
                    st.success(f"成功解鎖 {count} 筆紀錄！請重新讀取資料。")
                    if 'salary_review_df' in st.session_state:
                         del st.session_state['salary_review_df']
                    st.rerun()
        else:
            st.info("目前沒有已定版的紀錄可供解鎖。")