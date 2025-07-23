# page_special_attendance.py
import streamlit as st
import pandas as pd
from datetime import datetime, time
from utils import get_all_employees
from utils_special_overtime import get_special_attendance, add_special_attendance, delete_special_attendance

def show_page(conn):
    st.header("特別出勤紀錄管理 (津貼加班)")
    st.info("此處用於登記非正常上班日的出勤紀錄，例如假日加班。這些紀錄將用於計算「津貼加班」薪資項目，且不會出現在常規的打卡日報表中。")

    c1, c2 = st.columns(2)
    year = c1.number_input("選擇年份", min_value=2020, max_value=datetime.now().year + 5, value=datetime.now().year, key="sa_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=datetime.now().month, key="sa_month")

    try:
        sa_df = get_special_attendance(conn, year, month)
        st.dataframe(sa_df, use_container_width=True)
    except Exception as e:
        st.error(f"讀取特別出勤紀錄時發生錯誤: {e}")

    st.write("---")
    with st.expander("新增一筆特別出勤紀錄"):
        with st.form("add_special_attendance_form", clear_on_submit=True):
            all_employees = get_all_employees(conn)
            emp_options = {f"{name} ({code})": emp_id for name, code, emp_id in zip(all_employees['name_ch'], all_employees['hr_code'], all_employees['id'])}
            
            selected_emp_display = st.selectbox("選擇員工*", options=emp_options.keys())
            att_date = st.date_input("出勤日期*")
            
            c1_form, c2_form = st.columns(2)
            checkin = c1_form.time_input("上班時間*", value=time(9, 0))
            checkout = c2_form.time_input("下班時間*", value=time(18, 0))

            note = st.text_input("備註 (例如：專案趕工)")
            
            if st.form_submit_button("新增紀錄"):
                if not all([selected_emp_display, att_date, checkin, checkout]):
                    st.error("員工、日期與上下班時間為必填項！")
                else:
                    new_data = {
                        'employee_id': emp_options[selected_emp_display],
                        'date': att_date.strftime('%Y-%m-%d'),
                        'checkin_time': checkin.strftime('%H:%M:%S'),
                        'checkout_time': checkout.strftime('%H:%M:%S'),
                        'note': note
                    }
                    add_special_attendance(conn, new_data)
                    st.success("新增成功！")
                    st.rerun()

    if not sa_df.empty:
        with st.expander("刪除紀錄"):
            record_options = {f"ID: {row.id} - {row.員工姓名} @ {row.日期}": row.id for _, row in sa_df.iterrows()}
            selected_record_display = st.selectbox("選擇要刪除的紀錄", options=record_options.keys())
            if st.button("確認刪除", type="primary"):
                record_id_to_delete = record_options[selected_record_display]
                delete_special_attendance(conn, record_id_to_delete)
                st.success(f"已成功刪除紀錄 ID: {record_id_to_delete}")
                st.rerun()