# views/insurance_history.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from db import queries_insurance as q_ins
from db import queries_employee as q_emp
from db import queries_common as q_common
from utils.ui_components import create_batch_import_section
from services import insurance_logic as logic_ins
from utils.helpers import to_date # 引入 to_date 輔助函式

INSURANCE_TEMPLATE_COLUMNS = {
    'name_ch': '員工姓名*',
    'company_name': '加保單位名稱*',
    'start_date': '加保日期*(YYYY-MM-DD)',
    'end_date': '退保日期(YYYY-MM-DD)',
    'note': '備註'
}

def show_page(conn):
    st.header("📄 員工加保管理")
    
    try:
        history_df = q_ins.get_all_insurance_history(conn)
        
        st.info("您可以直接在下表中快速修改加/退保日期與備註，或使用下方的「單筆修改」功能進行操作。")
        
        df_display = history_df.copy()
        df_display['start_date'] = pd.to_datetime(df_display['start_date'], errors='coerce').dt.date
        df_display['end_date'] = pd.to_datetime(df_display['end_date'], errors='coerce').dt.date
        df_display.set_index('id', inplace=True)
        
        if 'original_insurance_df' not in st.session_state:
            st.session_state.original_insurance_df = df_display.copy()

        COLUMN_MAP = {
            'name_ch': '員工姓名', 'company_name': '加保單位',
            'start_date': '加保日期', 'end_date': '退保日期', 'note': '備註'
        }
        
        edited_df = st.data_editor(
            df_display.rename(columns=COLUMN_MAP),
            width='stretch',
            column_config={
                "加保日期": st.column_config.DateColumn("加保日期", format="YYYY-MM-DD"),
                "退保日期": st.column_config.DateColumn("退保日期", format="YYYY-MM-DD"),
            },
            disabled=["員工姓名", "加保單位"]
        )
        
        if st.button("💾 儲存表格變更", type="primary"):
            original_df_renamed = st.session_state.original_insurance_df.rename(columns=COLUMN_MAP)
            changed_rows = edited_df[edited_df.ne(original_df_renamed)].dropna(how='all')

            if changed_rows.empty:
                st.info("沒有偵測到任何變更。")
            else:
                updates_count = 0
                with st.spinner("正在儲存變更..."):
                    for record_id, row in changed_rows.iterrows():
                        update_data = row.dropna().to_dict()
                        update_data_reverted = {
                            (k for k, v in COLUMN_MAP.items() if v == col_name).__next__(): val 
                            for col_name, val in update_data.items()
                        }

                        for key, value in update_data_reverted.items():
                            if isinstance(value, (pd.Timestamp, date)):
                                update_data_reverted[key] = value.strftime('%Y-%m-%d')
                        
                        q_common.update_record(conn, 'employee_company_history', record_id, update_data_reverted)
                        updates_count += 1

                st.success(f"成功更新了 {updates_count} 筆加保紀錄！")
                del st.session_state.original_insurance_df
                st.rerun()

    except Exception as e:
        st.error(f"讀取加保歷史時發生錯誤: {e}")
        history_df = pd.DataFrame()

    st.write("---")
    st.subheader("資料操作")
    
    with st.expander("✨ 新增一筆加保紀錄"):
        employees = q_emp.get_all_employees(conn)
        companies = q_emp.get_all_companies(conn)
        emp_options = {f"{name} ({code})": eid for eid, name, code in zip(employees['id'], employees['name_ch'], employees['hr_code'])}
        comp_options = {name: cid for cid, name in zip(companies['id'], companies['name'])}

        with st.form("add_insurance_form", clear_on_submit=True):
            selected_emp_key = st.selectbox("選擇員工*", options=emp_options.keys(), index=None)
            selected_comp_key = st.selectbox("選擇加保單位*", options=comp_options.keys(), index=None)
            min_date = date(2000, 1, 1)
            start_date = st.date_input("加保日期*", value=datetime.now(), min_value=min_date, max_value=date.today().replace(year=date.today().year + 5))
            end_date = st.date_input("退保日期 (可留空)", value=None, min_value=min_date)
            note = st.text_input("備註")

            if st.form_submit_button("確認新增"):
                if not selected_emp_key or not selected_comp_key:
                    st.warning("請選擇員工和加保單位。")
                else:
                    new_data = {
                        'employee_id': emp_options[selected_emp_key],
                        'company_id': comp_options[selected_comp_key],
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d') if end_date else None,
                        'note': note
                    }
                    q_common.add_record(conn, 'employee_company_history', new_data)
                    st.success("成功新增加保紀錄！")
                    if 'original_insurance_df' in st.session_state:
                        del st.session_state.original_insurance_df
                    st.rerun()

    with st.expander("✏️ 修改或刪除現有紀錄"):
        if not history_df.empty:
            record_options = {
                f"ID:{row['id']} - {row['name_ch']} / {row['company_name']} ({row['start_date']})": row['id']
                for _, row in history_df.iterrows()
            }
            selected_key = st.selectbox(
                "從總覽列表選擇要操作的紀錄", 
                options=record_options.keys(), 
                index=None,
                placeholder="請選擇..."
            )
            if selected_key:
                record_id = record_options[selected_key]
                record_data = q_common.get_by_id(conn, 'employee_company_history', record_id)
                
                with st.form(f"edit_insurance_form_{record_id}"):
                    st.write(f"**正在編輯 ID: {record_id}**")
                    start_date_edit = st.date_input("加保日期*", value=to_date(record_data.get('start_date')))
                    end_date_edit = st.date_input("退保日期 (可留空)", value=to_date(record_data.get('end_date')))
                    note_edit = st.text_input("備註", value=record_data.get('note', '') or '')

                    col_update, col_delete = st.columns(2)
                    if col_update.form_submit_button("儲存變更", width='stretch'):
                        update_data = {
                            'start_date': start_date_edit.strftime('%Y-%m-%d') if start_date_edit else None,
                            'end_date': end_date_edit.strftime('%Y-%m-%d') if end_date_edit else None,
                            'note': note_edit
                        }
                        q_common.update_record(conn, 'employee_company_history', record_id, update_data)
                        st.success("紀錄已更新！")
                        if 'original_insurance_df' in st.session_state:
                            del st.session_state.original_insurance_df
                        st.rerun()
                    
                    if col_delete.form_submit_button("🔴 刪除此紀錄", type="primary", width='stretch'):
                        q_common.delete_record(conn, 'employee_company_history', record_id)
                        st.warning(f"紀錄 ID: {record_id} 已被刪除！")
                        if 'original_insurance_df' in st.session_state:
                            del st.session_state.original_insurance_df
                        st.rerun()
        else:
            st.info("目前沒有可供修改或刪除的紀錄。")


    st.write("---")
    st.subheader("🚀 批次匯入 (Excel)")
    create_batch_import_section(
        info_text="說明：系統會以「員工姓名」、「加保單位名稱」和「加保日期」為唯一鍵，若紀錄已存在則會更新，否則新增。",
        template_columns=INSURANCE_TEMPLATE_COLUMNS,
        template_file_name="insurance_history_template.xlsx",
        import_logic_func=logic_ins.batch_import_insurance_history,
        conn=conn
    )