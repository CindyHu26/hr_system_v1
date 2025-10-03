# views/special_attendance.py
import streamlit as st
import pandas as pd
from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from db import queries_attendance as q_att
from db import queries_employee as q_emp
from db import queries_common as q_common

def show_page(conn):
    st.header("📝 特別出勤管理 (津貼加班)")
    st.info("此處用於登記非正常上班日的出勤紀錄，例如假日加班。這些紀錄將用於計算「津貼加班」薪資項目，且不會出現在常規的打卡日報表中。")

    # --- 1. 查詢與顯示 ---
    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year, key="sa_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="sa_month")

    try:
        sa_df = q_att.get_special_attendance_by_month(conn, year, month)
        st.dataframe(sa_df, width='stretch')
    except Exception as e:
        st.error(f"讀取特別出勤紀錄時發生錯誤: {e}")
        sa_df = pd.DataFrame() 

    st.write("---")
    
    # --- 2. 新增、修改、刪除操作 ---
    with st.expander("新增、修改或刪除紀錄"):
        
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
        
        # --- 修改表單 ---
        st.markdown("##### ✏️ 修改現有紀錄")
        if not sa_df.empty:
            record_options_edit = {f"ID: {row.id} - {row.員工姓名} @ {row.日期}": row.id for _, row in sa_df.iterrows()}
            selected_record_to_edit = st.selectbox("從上方列表選擇要修改的紀錄", options=record_options_edit.keys(), index=None, key="edit_selector")

            if selected_record_to_edit:
                record_id_to_edit = record_options_edit[selected_record_to_edit]
                # 從 DataFrame 中找到原始資料
                record_data = sa_df[sa_df['id'] == record_id_to_edit].iloc[0]

                with st.form(f"edit_form_{record_id_to_edit}"):
                    st.write(f"正在編輯 **{record_data.員工姓名}** 於 **{record_data.日期}** 的紀錄")
                    
                    edit_date = st.date_input("修改日期*", value=pd.to_datetime(record_data.日期).date())
                    
                    c1_edit, c2_edit = st.columns(2)
                    current_checkin = datetime.strptime(record_data.上班時間, '%H:%M:%S').time()
                    current_checkout = datetime.strptime(record_data.下班時間, '%H:%M:%S').time()
                    edit_checkin = c1_edit.time_input("修改上班時間*", value=current_checkin, step=60)
                    edit_checkout = c2_edit.time_input("修改下班時間*", value=current_checkout, step=60)
                    
                    edit_note = st.text_input("修改備註", value=record_data.備註)

                    if st.form_submit_button("儲存變更", type="primary"):
                        updated_data = {
                            'date': edit_date.strftime('%Y-%m-%d'),
                            'checkin_time': edit_checkin.strftime('%H:%M:%S'),
                            'checkout_time': edit_checkout.strftime('%H:%M:%S'),
                            'note': edit_note
                        }
                        q_common.update_record(conn, 'special_attendance', record_id_to_edit, updated_data)
                        st.success(f"已成功更新紀錄 ID: {record_id_to_edit}")
                        st.rerun()
        else:
            st.info("目前沒有可供修改的紀錄。")

        st.markdown("---")
        
        # --- 刪除區塊 ---
        st.markdown("##### 🗑️ 刪除紀錄")
        if not sa_df.empty:
            record_options_delete = {f"ID: {row.id} - {row.員工姓名} @ {row.日期}": row.id for _, row in sa_df.iterrows()}
            selected_record_to_delete = st.selectbox("從上方列表選擇要刪除的紀錄", options=record_options_delete.keys(), index=None, key="delete_selector")
            
            if st.button("確認刪除", type="primary"):
                if selected_record_to_delete:
                    record_id_to_delete = record_options_delete[selected_record_to_delete]
                    q_common.delete_record(conn, 'special_attendance', record_id_to_delete)
                    st.success(f"已成功刪除紀錄 ID: {record_id_to_delete}")
                    st.rerun()
                else:
                    st.warning("請先選擇一筆要刪除的紀錄。")
        else:
            st.info("目前沒有可供刪除的紀錄。")