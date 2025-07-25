# pages/special_attendance.py
import streamlit as st
import pandas as pd
from datetime import datetime, time
from dateutil.relativedelta import relativedelta
# 導入新的、拆分後的查詢模組
from db import queries_attendance as q_att
from db import queries_employee as q_emp
from db import queries_common as q_common

def show_page(conn):
    st.header("📝 特別出勤管理 (津貼加班)")
    st.info("此處用於登記非正常上班日的出勤紀錄，例如假日加班。這些紀錄將用於計算「津貼加班」薪資項目，且不會出現在常規的打卡日報表中。")

    # --- 1. 查詢與顯示 ---
    c1, c2 = st.columns(2)
    today = datetime.now()
    # 計算上一個月的年份和月份
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year, key="sa_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="sa_month")

    try:
        sa_df = q_att.get_special_attendance_by_month(conn, year, month)
        st.dataframe(sa_df, use_container_width=True)
    except Exception as e:
        st.error(f"讀取特別出勤紀錄時發生錯誤: {e}")
        sa_df = pd.DataFrame() # 確保 df 存在

    st.write("---")
    
    # --- 2. 新增與刪除操作 ---
    with st.expander("新增或刪除紀錄"):
        
        # --- 新增表單 ---
        st.markdown("##### ✨ 新增一筆特別出勤紀錄")
        with st.form("add_special_attendance_form", clear_on_submit=True):
            all_employees = q_emp.get_all_employees(conn)
            emp_options = {f"{name} ({code})": emp_id for name, code, emp_id in zip(all_employees['name_ch'], all_employees['hr_code'], all_employees['id'])}
            
            selected_emp_display = st.selectbox("選擇員工*", options=emp_options.keys())
            att_date = st.date_input("出勤日期*")
            
            c1_form, c2_form = st.columns(2)
            checkin = c1_form.time_input("上班時間*", value=time(9, 0))
            checkout = c2_form.time_input("下班時間*", value=time(18, 0))
            note = st.text_input("備註 (例如：專案趕工)")
            
            if st.form_submit_button("新增紀錄", type="primary"):
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
                    q_common.add_record(conn, 'special_attendance', new_data)
                    st.success("新增成功！")
                    st.rerun()

        st.markdown("---")
        
        # --- 刪除區塊 ---
        st.markdown("##### 🗑️ 刪除紀錄")
        if not sa_df.empty:
            record_options = {f"ID: {row.id} - {row.員工姓名} @ {row.日期}": row.id for _, row in sa_df.iterrows()}
            selected_record_display = st.selectbox("從上方列表選擇要刪除的紀錄", options=record_options.keys(), index=None)
            
            if st.button("確認刪除", type="primary"):
                if selected_record_display:
                    record_id_to_delete = record_options[selected_record_display]
                    q_common.delete_record(conn, 'special_attendance', record_id_to_delete)
                    st.success(f"已成功刪除紀錄 ID: {record_id_to_delete}")
                    st.rerun()
                else:
                    st.warning("請先選擇一筆要刪除的紀錄。")
        else:
            st.info("目前沒有可供刪除的紀錄。")