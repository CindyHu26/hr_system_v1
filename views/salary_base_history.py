# pages/salary_base_history.py
import streamlit as st
import pandas as pd
from datetime import datetime, date

from db import queries_salary_base as q_base 
from db import queries_employee as q_emp
from utils.helpers import to_date
from utils.ui_components import create_batch_import_section
from services import salary_base_logic as logic_base

SALARY_BASE_TEMPLATE_COLUMNS = {
    'name_ch': '員工姓名*', 'base_salary': '底薪*', 'insurance_salary': '勞健保投保薪資*',
    'dependents': '健保眷屬數*', 'start_date': '生效日*(YYYY-MM-DD)', 
    'end_date': '結束日(YYYY-MM-DD)', 'note': '備註'
}

def show_page(conn):
    st.header("📈 薪資基準管理")
    st.info("管理每位員工的歷次調薪、投保薪資與眷屬數量變更紀錄。")

    # --- 功能區 1: 一鍵更新基本工資 ---
    st.subheader("批次更新基本工資")
    
    # 根據勞動部公告，設定 2025 年基本工資作為預設值 (此為假設值，實際使用時應確認)
    LEGAL_MINIMUM_WAGE_2025 = 28590
    
    c1, c2 = st.columns([1, 1])
    new_wage = c1.number_input(
        "設定新的基本工資", 
        min_value=0, 
        value=LEGAL_MINIMUM_WAGE_2025,
        help=f"可依據勞動部公告調整，例如 2025 年基本工資為 NT$ {LEGAL_MINIMUM_WAGE_2025}"
    )
    effective_date = c2.date_input("設定新制生效日", value=date(2025, 1, 1))

    if st.button("Step 1: 預覽將被更新的員工"):
        with st.spinner("正在篩選底薪低於新標準的員工..."):
            # 【關鍵修正】改用 q_base
            preview_df = q_base.get_employees_below_minimum_wage(conn, new_wage)
            st.session_state.salary_update_preview = preview_df
    
    if 'salary_update_preview' in st.session_state:
        preview_df = st.session_state.salary_update_preview
        if not preview_df.empty:
            st.write("##### 預覽清單：")
            st.dataframe(preview_df, use_container_width=True)
            st.warning(f"共有 {len(preview_df)} 位員工的底薪將從「目前底薪」調整為 NT$ {new_wage}，且投保薪資將同步更新。")
            
            if st.button("Step 2: 確認執行更新", type="primary"):
                with st.spinner("正在為以上員工批次新增調薪紀錄..."):
                    # 【關鍵修正】改用 q_base
                    count = q_base.batch_update_base_salary(conn, preview_df, new_wage, effective_date)
                    st.success(f"成功為 {count} 位員工更新了基本工資！")
                    del st.session_state.salary_update_preview
                    st.rerun()
        else:
            st.success("所有在職員工的目前底薪均已高於或等於新標準，無需調整！")
            del st.session_state.salary_update_preview

    st.markdown("---")

    # --- 功能區 2: 歷史紀錄總覽與手動操作 ---
    st.subheader("歷史紀錄總覽與手動操作")
    
    try:
        # 【關鍵修正】改用 q_base
        history_df_raw = q_base.get_salary_base_history(conn)
        history_df_display = history_df_raw.rename(columns={
            'name_ch': '員工姓名', 'base_salary': '底薪', 'insurance_salary': '投保薪資',
            'dependents': '眷屬數', 'start_date': '生效日', 'end_date': '結束日', 'note': '備註'
        })
        st.dataframe(history_df_display, use_container_width=True)
    except Exception as e:
        st.error(f"讀取歷史紀錄時發生錯誤: {e}")
        return

    st.write("---")
    
    tab1, tab2, tab3 = st.tabs([" ✨ 新增紀錄", "✏️ 修改/刪除紀錄", "🚀 批次匯入 (Excel)"])

    with tab1:
        emp_df = q_emp.get_all_employees(conn)
        emp_options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in emp_df.iterrows()}

        with st.form("add_base_history", clear_on_submit=True):
            selected_emp_key = st.selectbox("選擇員工*", options=emp_options.keys())
            c1, c2, c3 = st.columns(3)
            base_salary = c1.number_input("底薪*", min_value=0)
            insurance_salary = c2.number_input("勞健保投保薪資*", min_value=0, help="若為 0，將預設等同底薪")
            dependents = c3.number_input("健保眷屬數*", min_value=0, step=1, format="%d")
            
            c4, c5 = st.columns(2)
            start_date = c4.date_input("生效日*", value=datetime.now())
            end_date = c5.date_input("結束日 (留空表示持續有效)", value=None)
            note = st.text_area("備註")

            if st.form_submit_button("確認新增"):
                data = {
                    'employee_id': emp_options[selected_emp_key], 
                    'base_salary': base_salary,
                    'insurance_salary': insurance_salary if insurance_salary > 0 else base_salary, 
                    'dependents': dependents,
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d') if end_date else None,
                    'note': note
                }
                # 注意：這裡呼叫的是 q_emp.add_record，這是通用的函式，不需更動
                q_emp.add_record(conn, 'salary_base_history', data)
                st.success("成功新增紀錄！")
                st.rerun()

    with tab2:
        if not history_df_raw.empty:
            options = {f"ID:{row['id']} - {row['name_ch']} (生效日: {row['start_date']})": row['id'] for _, row in history_df_raw.iterrows()}
            selected_key = st.selectbox("選擇要操作的紀錄", options.keys(), index=None, placeholder="請選擇一筆紀錄...")

            if selected_key:
                record_id = options[selected_key]
                record_data = history_df_raw[history_df_raw['id'] == record_id].iloc[0].to_dict()
                
                with st.form(f"edit_base_history_{record_id}"):
                    st.write(f"正在編輯 **{record_data['name_ch']}** 的紀錄 (ID: {record_id})")
                    c1, c2, c3 = st.columns(3)
                    base_salary_edit = c1.number_input("底薪*", min_value=0, value=int(record_data['base_salary']))
                    ins_salary_edit = c2.number_input("勞健保投保薪資*", min_value=0, value=int(record_data.get('insurance_salary') or record_data['base_salary']))
                    dependents_edit = c3.number_input("健保眷屬數*", min_value=0, step=1, format="%d", value=int(record_data.get('dependents', 0)))
                    
                    c4, c5 = st.columns(2)
                    start_date_edit = c4.date_input("生效日*", value=to_date(record_data.get('start_date')))
                    end_date_edit = c5.date_input("結束日", value=to_date(record_data.get('end_date')))
                    note_edit = st.text_area("備註", value=record_data.get('note') or "")
                    
                    c_update, c_delete = st.columns(2)
                    if c_update.form_submit_button("儲存變更", use_container_width=True):
                        updated_data = {
                            'base_salary': base_salary_edit,
                            'insurance_salary': ins_salary_edit if ins_salary_edit > 0 else base_salary_edit,
                            'dependents': dependents_edit,
                            'start_date': start_date_edit.strftime('%Y-%m-%d') if start_date_edit else None,
                            'end_date': end_date_edit.strftime('%Y-%m-%d') if end_date_edit else None,
                            'note': note_edit
                        }
                        q_emp.update_record(conn, 'salary_base_history', record_id, updated_data)
                        st.success(f"紀錄 ID:{record_id} 已更新！")
                        st.rerun()

                    if c_delete.form_submit_button("🔴 刪除此紀錄", use_container_width=True, type="primary"):
                        q_emp.delete_record(conn, 'salary_base_history', record_id)
                        st.warning(f"紀錄 ID:{record_id} 已刪除！")
                        st.rerun()
        else:
            st.info("目前沒有可供修改或刪除的紀錄。")

    with tab3:
        create_batch_import_section(
            info_text="說明：系統會以「員工姓名」和「生效日」為唯一鍵，若紀錄已存在則會更新，否則新增。",
            template_columns=SALARY_BASE_TEMPLATE_COLUMNS,
            template_file_name="salary_base_template.xlsx",
            import_logic_func=logic_base.batch_import_salary_base,
            conn=conn
        )