# views/loan_management.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from db import queries_loan as q_loan
from db import queries_common as q_common

def show_page(conn):
    st.header("📝 借支管理")
    st.info("您可以在此維護特定月份的員工借支紀錄。此處的資料將會自動整合進該月份的薪資單計算中。")

    # --- 月份選擇 ---
    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year, key="loan_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="loan_month")

    st.markdown("---")

    # --- 顯示與編輯現有紀錄 ---
    try:
        loan_df = q_loan.get_loans_by_month(conn, year, month)
        st.subheader(f"{year} 年 {month} 月 借支紀錄總覽")
        
        if 'original_loan_df' not in st.session_state:
            st.session_state.original_loan_df = loan_df.copy()

        edited_df = st.data_editor(
            loan_df,
            use_container_width=True,
            num_rows="dynamic",
            disabled=['員工編號', '員工姓名', 'id'],
            key="loan_editor"
        )
        
        if st.button("💾 儲存上方表格的變更", type="primary"):
            # 找出有變更的行
            changes = edited_df.compare(st.session_state.original_loan_df)
            if not changes.empty:
                with st.spinner("正在儲存變更..."):
                    for record_id, changed_row in edited_df.iterrows():
                        original_row = st.session_state.original_loan_df.loc[record_id]
                        if not changed_row.equals(original_row):
                            update_data = {
                                'employee_id': changed_row['employee_id'],
                                'year': year, 'month': month,
                                'amount': changed_row['借支金額'],
                                'note': changed_row['備註']
                            }
                            q_loan.upsert_loan_record(conn, update_data)
                st.success("變更已儲存！")
                del st.session_state.original_loan_df
                st.rerun()
            else:
                st.info("沒有偵測到任何變更。")

    except Exception as e:
        st.error(f"讀取借支紀錄時發生錯誤: {e}")
        loan_df = pd.DataFrame()

    st.markdown("---")
    # --- 新增/刪除操作 ---
    with st.expander("✨ 新增或刪除單筆紀錄"):
        employees = q_common.get_all(conn, 'employee', order_by='hr_code')
        emp_options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in employees.iterrows()}

        st.markdown("##### 新增/修改一筆紀錄")
        with st.form("upsert_loan_form", clear_on_submit=True):
            selected_emp_key = st.selectbox("選擇員工*", options=emp_options.keys(), index=None)
            amount = st.number_input("借支金額*", min_value=0, step=100)
            note = st.text_input("備註 (可選填)")

            if st.form_submit_button("確認新增/修改", type="primary"):
                if not selected_emp_key:
                    st.warning("請選擇一位員工！")
                else:
                    data = {
                        'employee_id': emp_options[selected_emp_key],
                        'year': year, 'month': month,
                        'amount': amount, 'note': note
                    }
                    q_loan.upsert_loan_record(conn, data)
                    st.success(f"已成功為 {selected_emp_key} 新增/修改 {year}年{month}月 的借支紀錄。")
                    st.rerun()

        st.markdown("---")
        st.markdown("##### 刪除一筆紀錄")
        if not loan_df.empty:
            record_options = {f"ID:{row['id']} - {row['員工姓名']}": row['id'] for _, row in loan_df.iterrows()}
            key_to_delete = st.selectbox("選擇要刪除的紀錄", options=record_options.keys(), index=None)
            if st.button("🔴 確認刪除", type="primary"):
                if key_to_delete:
                    record_id = record_options[key_to_delete]
                    q_common.delete_record(conn, 'monthly_loan', record_id)
                    st.warning("紀錄已刪除！")
                    st.rerun()
                else:
                    st.warning("請選擇一筆要刪除的紀錄。")