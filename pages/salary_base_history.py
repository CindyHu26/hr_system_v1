# pages/salary_base_history.py
import streamlit as st
import pandas as pd
from datetime import datetime
from db import queries as q

def show_page(conn):
    st.header("📈 薪資基準管理")
    st.info("管理每位員工的歷次調薪、投保薪資與眷屬數量變更紀錄。")

    try:
        history_df_raw = q.get_salary_base_history(conn)
        if 'insurance_salary' not in history_df_raw.columns:
            history_df_raw['insurance_salary'] = None
            
        history_df_display = history_df_raw.rename(columns={
            'name_ch': '員工姓名', 'base_salary': '底薪', 'insurance_salary': '投保薪資',
            'dependents': '眷屬數', 'start_date': '生效日', 'end_date': '結束日', 'note': '備註'
        })
        st.dataframe(history_df_display, use_container_width=True)
    except Exception as e:
        st.error(f"讀取歷史紀錄時發生錯誤: {e}")
        return

    st.write("---")
    st.subheader("資料操作")
    
    tab1, tab2 = st.tabs([" ✨ 新增紀錄", "✏️ 修改/刪除紀錄"])

    with tab1:
        emp_df = q.get_all_employees(conn)
        emp_options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in emp_df.iterrows()}

        with st.form("add_base_history", clear_on_submit=True):
            selected_emp_key = st.selectbox("選擇員工*", options=emp_options.keys())
            c1, c2, c3 = st.columns(3)
            base_salary = c1.number_input("底薪*", min_value=0)
            insurance_salary = c2.number_input("勞健保投保薪資*", min_value=0)
            dependents = c3.number_input("眷屬數*", min_value=0.0, step=0.01, format="%.2f")
            
            c4, c5 = st.columns(2)
            start_date = c4.date_input("生效日*", value=datetime.now())
            end_date = c5.date_input("結束日", value=None)
            note = st.text_area("備註")

            if st.form_submit_button("確認新增"):
                data = {
                    'employee_id': emp_options[selected_emp_key], 'base_salary': base_salary,
                    'insurance_salary': insurance_salary, 'dependents': dependents,
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d') if end_date else None,
                    'note': note
                }
                q.add_record(conn, 'salary_base_history', data)
                st.success("成功新增紀錄！")
                st.rerun()

    with tab2:
        if not history_df_raw.empty:
            options = {f"ID:{row['id']} - {row['name_ch']} (生效日: {row['start_date']})": row['id'] for _, row in history_df_raw.iterrows()}
            selected_key = st.selectbox("選擇要操作的紀錄", options.keys(), index=None)

            if selected_key:
                record_id = options[selected_key]
                record_data = q.get_by_id(conn, 'salary_base_history', record_id)
                
                with st.form(f"edit_base_history_{record_id}"):
                    # ... (與新增表單類似的 UI 邏輯) ...
                    pass
