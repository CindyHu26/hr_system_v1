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
    
    try:
        history_df = q_ins.get_all_insurance_history(conn)

        # 預處理日期欄位
        history_df['start_date'] = pd.to_datetime(history_df['start_date'], errors='coerce').dt.date
        history_df['end_date'] = pd.to_datetime(history_df['end_date'], errors='coerce').dt.date

        st.info("您可以直接在下表中修改加/退保日期與備註，完成後點擊下方的「儲存變更」按鈕。")
        history_df.set_index('id', inplace=True)
        
        if 'original_insurance_df' not in st.session_state:
            st.session_state.original_insurance_df = history_df.copy()

        COLUMN_MAP = {
            'name_ch': '員工姓名', 'company_name': '加保單位',
            'start_date': '加保日期', 'end_date': '退保日期', 'note': '備註'
        }
        
        edited_df = st.data_editor(
            history_df.rename(columns=COLUMN_MAP),
            use_container_width=True,
            disabled=["員工姓名", "加保單位"]
        )
        
        if st.button("💾 儲存加保資料變更", type="primary"):
            original_df_renamed = st.session_state.original_insurance_df.rename(columns=COLUMN_MAP)
            changed_rows = edited_df[edited_df.ne(original_df_renamed)].dropna(how='all')

            if changed_rows.empty:
                st.info("沒有偵測到任何變更。")
            else:
                updates_count = 0
                with st.spinner("正在儲存變更..."):
                    edited_df_reverted = edited_df.rename(columns={v: k for k, v in COLUMN_MAP.items()})
                    for record_id, row in changed_rows.iterrows():
                        update_data_raw = edited_df_reverted.loc[record_id].dropna().to_dict()
                        # 格式化日期回字串
                        if 'start_date' in update_data_raw:
                            update_data_raw['start_date'] = update_data_raw['start_date'].strftime('%Y-%m-%d')
                        if 'end_date' in update_data_raw:
                            update_data_raw['end_date'] = update_data_raw['end_date'].strftime('%Y-%m-%d')
                        
                        q_common.update_record(conn, 'employee_company_history', record_id, update_data_raw)
                        updates_count += 1

                st.success(f"成功更新了 {updates_count} 筆加保紀錄！")
                del st.session_state.original_insurance_df
                st.rerun()

    except Exception as e:
        st.error(f"讀取加保歷史時發生錯誤: {e}")
        return
        
    st.subheader("資料操作")
    tab1, tab2 = st.tabs([" ✨ 新增紀錄", "🚀 批次匯入 (Excel)"])

    with tab1:
        # ... (新增紀錄的 form 內容保持不變) ...
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
        create_batch_import_section(
            info_text="說明：系統會以「員工姓名」、「加保單位名稱」和「加保日期」為唯一鍵，若紀錄已存在則會更新，否則新增。",
            template_columns=INSURANCE_TEMPLATE_COLUMNS,
            template_file_name="insurance_history_template.xlsx",
            import_logic_func=logic_ins.batch_import_insurance_history,
            conn=conn
        )
