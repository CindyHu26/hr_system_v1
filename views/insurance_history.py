# pages/insurance_history.py
import streamlit as st
import pandas as pd

from datetime import datetime
from db import queries_insurance as q_ins
from db import queries_employee as q_emp
from db import queries_common as q_common

from utils.ui_components import create_batch_import_section
from services import insurance_logic as logic_ins

# 定義範本欄位
INSURANCE_TEMPLATE_COLUMNS = {
    'name_ch': '員工姓名*',
    'company_name': '加保單位名稱*',
    'start_date': '加保日期*(YYYY-MM-DD)',
    'end_date': '退保日期(YYYY-MM-DD)',
    'note': '備註'
}

def show_page(conn):
    st.header("📄 員工加保管理")
    st.info("管理每位員工的投保單位、加保與退保日期。")

    try:
        history_df = q_ins.get_all_insurance_history(conn)
        st.dataframe(history_df.rename(columns={
            'name_ch': '員工姓名', 'company_name': '加保單位',
            'start_date': '加保日期', 'end_date': '退保日期', 'note': '備註'
        }), use_container_width=True)
    except Exception as e:
        st.error(f"讀取加保歷史時發生錯誤: {e}")
        return
        
    st.write("---")
    st.subheader("資料操作")
    
    tab1, tab2, tab3 = st.tabs([" ✨ 新增紀錄", "✏️ 修改/刪除紀錄", "🚀 批次匯入 (Excel)"])

    with tab1:
        st.markdown("#### 新增一筆加保紀錄")
        employees = q_emp.get_all_employees(conn)
        companies = q_emp.get_all_companies(conn)
        
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
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d') if end_date else None,
                    'note': note
                }
                q_common.add_record(conn, 'employee_company_history', new_data)
                st.success("成功新增加保紀錄！")
                st.rerun()

    with tab2:
        st.markdown("#### 修改或刪除現有紀錄")
        if not history_df.empty:
            options = {f"ID:{row['id']} - {row['name_ch']} @ {row['company_name']}": row['id'] for _, row in history_df.iterrows()}
            selected_key = st.selectbox("選擇要操作的紀錄", options.keys(), index=None)
            
            if selected_key:
                record_id = options[selected_key]
                record_data = history_df[history_df['id'] == record_id].iloc[0]

                with st.form(f"edit_insurance_{record_id}"):
                    st.write(f"正在編輯 **{record_data['name_ch']}** 的紀錄")
                    start_date_edit = st.date_input("加保日期", value=pd.to_datetime(record_data['start_date']))
                    end_date_val = pd.to_datetime(record_data['end_date']) if pd.notna(record_data['end_date']) else None
                    end_date_edit = st.date_input("退保日期", value=end_date_val)
                    note_edit = st.text_input("備註", value=record_data['note'] or "")
                    
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("儲存變更"):
                        updated_data = {
                            'start_date': start_date_edit.strftime('%Y-%m-%d'),
                            'end_date': end_date_edit.strftime('%Y-%m-%d') if end_date_edit else None,
                            'note': note_edit
                        }
                        q_common.update_record(conn, 'employee_company_history', record_id, updated_data)
                        st.success(f"紀錄 ID:{record_id} 已更新！")
                        st.rerun()
                    
                    if c2.form_submit_button("🔴 刪除此紀錄", type="primary"):
                        q_common.delete_record(conn, 'employee_company_history', record_id)
                        st.warning(f"紀錄 ID:{record_id} 已刪除！")
                        st.rerun()
    with tab3:
        create_batch_import_section(
            info_text="說明：系統會以「員工姓名」、「加保單位名稱」和「加保日期」為唯一鍵，若紀錄已存在則會更新，否則新增。",
            template_columns=INSURANCE_TEMPLATE_COLUMNS,
            template_file_name="insurance_history_template.xlsx",
            import_logic_func=logic_ins.batch_import_insurance_history,
            conn=conn
        )