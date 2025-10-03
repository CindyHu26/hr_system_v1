# views/monthly_adjustments.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from db import queries_salary_items as q_items
from db import queries_allowances as q_allow
from db import queries_common as q_common
from utils.helpers import get_monthly_dates

def show_page(conn):
    st.header("➕ 單次薪資項目調整")
    st.info(
        "此處用於新增或管理特定月份的、非經常性的薪資項目（例如單次獎金、費用）。"
        "這裡的紀錄會被永久保存，並自動加入薪資計算，且 **不會** 因為重新「產生草稿」而被覆蓋。"
    )

    # --- 1. 月份選擇 ---
    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year, key="adj_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="adj_month")

    st.markdown("---")

    # --- 2. 顯示現有紀錄 ---
    try:
        st.subheader(f"{year} 年 {month} 月 單次調整紀錄總覽")
        adjustments_df = q_allow.get_monthly_adjustments(conn, year, month)
        st.dataframe(adjustments_df, width='stretch')
    except Exception as e:
        st.error(f"讀取調整紀錄時發生錯誤: {e}")
        adjustments_df = pd.DataFrame()

    st.markdown("---")

    # --- 3. 新增與刪除操作 ---
    with st.expander("✨ 新增或刪除單筆紀錄"):
        # --- 新增表單 ---
        st.markdown("##### 新增一筆紀錄")
        with st.form("add_adjustment_form", clear_on_submit=True):
            employees = q_common.get_all(conn, 'employee', order_by='hr_code')
            items = q_items.get_all_salary_items(conn, active_only=True)

            emp_options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in employees.iterrows()}
            item_options = {row['name']: row['id'] for _, row in items.iterrows()}

            c1_form, c2_form, c3_form = st.columns(3)
            emp_key = c1_form.selectbox("選擇員工*", options=emp_options.keys(), index=None)
            item_key = c2_form.selectbox("選擇薪資項目*", options=item_options.keys(), index=None)
            amount = c3_form.number_input("設定金額*", min_value=0, step=100)
            note = st.text_input("備註 (可選填)", placeholder="例如：五月份專案獎金")

            if st.form_submit_button("確認新增", type="primary"):
                if not all([emp_key, item_key]):
                    st.warning("請務必選擇員工和薪資項目！")
                else:
                    start_date, end_date = get_monthly_dates(year, month)
                    new_data = {
                        'employee_id': emp_options[emp_key],
                        'salary_item_id': item_options[item_key],
                        'amount': amount,
                        'start_date': start_date,
                        'end_date': end_date,
                        'note': note
                    }
                    try:
                        q_common.add_record(conn, 'employee_salary_item', new_data)
                        st.success("成功新增一筆單次調整紀錄！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗，可能是該員工已存在相同的項目: {e}")

        st.markdown("---")
        # --- 刪除區塊 ---
        st.markdown("##### 刪除一筆紀錄")
        if not adjustments_df.empty:
            record_options = {
                f"ID:{row['id']} - {row['員工姓名']} / {row['項目名稱']} / 金額:{row['金額']}": row['id']
                for _, row in adjustments_df.iterrows()
            }
            key_to_delete = st.selectbox("選擇要刪除的紀錄*", options=record_options.keys(), index=None)
            
            if st.button("🔴 確認刪除", type="primary"):
                if key_to_delete:
                    record_id = record_options[key_to_delete]
                    q_common.delete_record(conn, 'employee_salary_item', record_id)
                    st.warning("紀錄已刪除！")
                    st.rerun()
                else:
                    st.warning("請選擇一筆要刪除的紀錄。")
        else:
            st.info("目前沒有可供刪除的紀錄。")