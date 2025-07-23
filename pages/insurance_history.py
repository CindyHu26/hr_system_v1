# page_insurance_history.py
import streamlit as st
import pandas as pd
from datetime import datetime
from utils import get_all_employees, get_all_companies

# --- CRUD Functions for employee_company_history ---

def get_all_insurance_history(conn):
    query = """
    SELECT 
        ech.id,
        e.name_ch as '員工姓名',
        c.name as '加保單位',
        ech.start_date as '加保日期',
        ech.end_date as '退保日期',
        ech.note as '備註'
    FROM employee_company_history ech
    JOIN employee e ON ech.employee_id = e.id
    JOIN company c ON ech.company_id = c.id
    ORDER BY ech.start_date DESC
    """
    return pd.read_sql_query(query, conn)

def add_insurance_history(conn, data):
    cursor = conn.cursor()
    sql = "INSERT INTO employee_company_history (employee_id, company_id, start_date, end_date, note) VALUES (?, ?, ?, ?, ?)"
    cursor.execute(sql, (data['employee_id'], data['company_id'], data['start_date'], data['end_date'], data['note']))
    conn.commit()

def update_insurance_history(conn, record_id, data):
    cursor = conn.cursor()
    sql = "UPDATE employee_company_history SET start_date = ?, end_date = ?, note = ? WHERE id = ?"
    cursor.execute(sql, (data['start_date'], data['end_date'], data['note'], record_id))
    conn.commit()

def delete_insurance_history(conn, record_id):
    cursor = conn.cursor()
    sql = "DELETE FROM employee_company_history WHERE id = ?"
    cursor.execute(sql, (record_id,))
    conn.commit()

def show_page(conn):
    st.header("員工加保異動管理")
    st.info("您可以在此管理每位員工的投保單位、加保與退保日期。")

    try:
        history_df = get_all_insurance_history(conn)
        st.dataframe(history_df, use_container_width=True)
    except Exception as e:
        st.error(f"讀取加保歷史時發生錯誤: {e}")
        return
        
    st.write("---")
    st.subheader("資料操作")
    
    tab1, tab2 = st.tabs([" ✨ 新增紀錄", "✏️ 修改/刪除紀錄"])

    with tab1:
        st.markdown("#### 新增一筆加保紀錄")
        employees = get_all_employees(conn)
        companies = get_all_companies(conn)
        emp_options = {f"{name} ({code})": eid for eid, name, code in zip(employees['id'], employees['name_ch'], employees['hr_code'])}
        comp_options = {name: cid for cid, name in zip(companies['id'], companies['name'])}

        with st.form("add_insurance_form", clear_on_submit=True):
            selected_emp_key = st.selectbox("選擇員工*", options=emp_options.keys())
            selected_comp_key = st.selectbox("選擇加保單位*", options=comp_options.keys())
            start_date = st.date_input("加保日期*", value=datetime.now())
            end_date = st.date_input("退保日期 (可留空)", value=None)
            note = st.text_input("備註")

            if st.form_submit_button("確認新增"):
                new_data = {
                    'employee_id': emp_options[selected_emp_key],
                    'company_id': comp_options[selected_comp_key],
                    'start_date': start_date,
                    'end_date': end_date,
                    'note': note
                }
                add_insurance_history(conn, new_data)
                st.success("成功新增加保紀錄！")
                st.rerun()

    with tab2:
        st.markdown("#### 修改或刪除現有紀錄")
        if not history_df.empty:
            record_options = {f"ID:{row.id} - {row.員工姓名} @ {row.加保單位}": row.id for _, row in history_df.iterrows()}
            selected_record_key = st.selectbox("選擇要操作的紀錄", options=record_options.keys(), index=None)
            
            if selected_record_key:
                record_id = record_options[selected_record_key]
                record_data = history_df[history_df['id'] == record_id].iloc[0]

                with st.form(f"edit_insurance_form_{record_id}"):
                    st.write(f"正在編輯 **{record_data['員工姓名']}** 的紀錄 (ID: {record_id})")
                    
                    start_date_edit = st.date_input("加保日期", value=pd.to_datetime(record_data['加保日期']))
                    end_date_val = pd.to_datetime(record_data['退保日期']) if pd.notna(record_data['退保日期']) else None
                    end_date_edit = st.date_input("退保日期", value=end_date_val)
                    note_edit = st.text_input("備註", value=record_data['備註'] or "")
                    
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("儲存變更"):
                        updated_data = {
                            'start_date': start_date_edit,
                            'end_date': end_date_edit,
                            'note': note_edit
                        }
                        update_insurance_history(conn, record_id, updated_data)
                        st.success(f"紀錄 ID:{record_id} 已更新！")
                        st.rerun()
                    
                    if c2.form_submit_button("🔴 刪除此紀錄", type="primary"):
                        delete_insurance_history(conn, record_id)
                        st.warning(f"紀錄 ID:{record_id} 已刪除！")
                        st.rerun()
        else:
            st.info("目前沒有可操作的紀錄。")