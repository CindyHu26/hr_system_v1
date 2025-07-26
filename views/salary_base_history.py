# pages/salary_base_history.py
import streamlit as st
import pandas as pd
from datetime import datetime, date

from db import queries_common as q_common
from db import queries_salary_base as q_base 
from db import queries_employee as q_emp
from db import queries_insurance as q_ins
from utils.helpers import to_date
from utils.ui_components import create_batch_import_section
from services import salary_base_logic as logic_base
from services.salary_logic import calculate_single_employee_insurance 

SALARY_BASE_TEMPLATE_COLUMNS = {
    'name_ch': '員工姓名*', 'base_salary': '底薪*', 
    'dependents_under_18': '健保眷屬數(<18歲)*', 
    'dependents_over_18': '健保眷屬數(>=18歲)*', 
    'labor_insurance_override': '勞保費(手動)',
    'health_insurance_override': '健保費(手動)',
    'pension_override': '勞退提撥(手動)',
    'start_date': '生效日*(YYYY-MM-DD)', 
    'end_date': '結束日(YYYY-MM-DD)', 'note': '備註'
}

def show_page(conn):
    st.header("📈 薪資基準管理")
    st.info("管理每位員工的歷次調薪、投保薪資與眷屬數量變更紀錄。系統會根據底薪自動帶入勞健保投保薪資。")

    # --- 功能區 1: 批次更新基本工資 ---
    st.subheader("批次更新基本工資")
    
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
        with st.spinner("正在篩選並預估保費..."):
            preview_df = q_base.get_employees_below_minimum_wage(conn, new_wage)
            if not preview_df.empty:
                estimated_fees = []
                for _, row in preview_df.iterrows():
                    new_insurance_salary = q_ins.get_insurance_salary_level(conn, new_wage)
                    fee = calculate_single_employee_insurance(
                        conn=conn,
                        insurance_salary=new_insurance_salary,
                        dependents_under_18=row['dependents_under_18'],
                        dependents_over_18=row['dependents_over_18'],
                        nhi_status=row['nhi_status'],
                        nhi_status_expiry=row['nhi_status_expiry'],
                        year=effective_date.year,
                        month=effective_date.month
                    )
                    estimated_fees.append(fee)
                preview_df['預估勞健保費'] = estimated_fees
            st.session_state.salary_update_preview = preview_df
    
    if 'salary_update_preview' in st.session_state:
        preview_df = st.session_state.salary_update_preview
        if not preview_df.empty:
            st.write("##### 預覽清單：")
            display_cols = ["員工姓名", "目前底薪", "目前投保薪資", "預估勞健保費"]
            st.dataframe(preview_df[display_cols], use_container_width=True)
            st.warning(f"共有 {len(preview_df)} 位員工的底薪將從「目前底薪」調整為 NT$ {new_wage}，且投保薪資將同步更新。")
            
            if st.button("Step 2: 確認執行更新", type="primary"):
                with st.spinner("正在為以上員工批次新增調薪紀錄..."):
                    count = q_base.batch_update_base_salary(conn, preview_df, new_wage, effective_date)
                    st.success(f"成功為 {count} 位員工更新了基本工資！")
                    del st.session_state.salary_update_preview
                    st.rerun()
        else:
            st.success("所有在職員工的目前底薪均已高於或等於新標準，無需調整！")
            del st.session_state.salary_update_preview

    st.markdown("---")

    # --- [核心修改] 功能區 2: 歷史紀錄總覽與手動操作 ---
    st.subheader("歷史紀錄總覽與手動操作")
    
    try:
        history_df_raw = q_base.get_salary_base_history(conn)
        
        # 為總覽表格計算當期保費
        if not history_df_raw.empty:
            fees = []
            for _, row in history_df_raw.iterrows():
                start_date = pd.to_datetime(row['start_date'])
                fee = calculate_single_employee_insurance(
                    conn,
                    row['insurance_salary'],
                    row['dependents_under_18'],
                    row['dependents_over_18'],
                    row['nhi_status'],
                    row['nhi_status_expiry'],
                    start_date.year,
                    start_date.month
                )
                fees.append(sum(fee))
            history_df_raw['當期勞健保費'] = fees

        history_df_display = history_df_raw.rename(columns={
            'name_ch': '員工姓名', 'base_salary': '底薪', 'insurance_salary': '投保薪資',
            'dependents_under_18': '眷屬(<18)', 'dependents_over_18': '眷屬(>=18)',
            'labor_insurance_override': '勞保費(手動)', 'health_insurance_override': '健保費(手動)',
            'pension_override': '勞退提撥(手動)',
            'start_date': '生效日', 'end_date': '結束日', 'note': '備註'
        })
        st.dataframe(history_df_display, use_container_width=True)
    except Exception as e:
        st.error(f"讀取歷史紀錄時發生錯誤: {e}")
        return

    st.write("---")
    
    # [核心修改] 恢復頁籤 UI
    tab1, tab2, tab3 = st.tabs([" ✨ 新增紀錄", "✏️ 修改/刪除紀錄", "🚀 批次匯入 (Excel)"])

    with tab1:
        emp_df = q_emp.get_all_employees(conn)
        emp_options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in emp_df.iterrows()}

        with st.form("add_base_history", clear_on_submit=True):
            selected_emp_key = st.selectbox("選擇員工*", options=emp_options.keys())
            c1, c2, c3 = st.columns(3)
            base_salary = c1.number_input("底薪*", min_value=0)
            dependents_under_18 = c2.number_input("健保眷屬數(<18歲)*", min_value=0.0, step=0.5, format="%.2f")
            dependents_over_18 = c3.number_input("健保眷屬數(>=18歲)*", min_value=0.0, step=0.5, format="%.2f")
            
            c4, c5 = st.columns(2)
            start_date = c4.date_input("生效日*", value=datetime.now())
            end_date = c5.date_input("結束日 (留空表示持續有效)", value=None)
            note = st.text_area("備註")

            st.markdown("##### 手動調整 (選填，若填寫將覆蓋自動計算)")
            c6, c7, c8 = st.columns(3)
            labor_override = c6.number_input("勞保費(手動)", min_value=0, step=1, value=None)
            health_override = c7.number_input("健保費(手動)", min_value=0, step=1, value=None)
            pension_override = c8.number_input("勞退提撥(手動)", min_value=0, step=1, value=None)

            if st.form_submit_button("確認新增"):
                insurance_salary = q_ins.get_insurance_salary_level(conn, base_salary)
                data = {
                    'employee_id': emp_options[selected_emp_key], 
                    'base_salary': base_salary,
                    'insurance_salary': insurance_salary, 
                    'dependents_under_18': dependents_under_18,
                    'dependents_over_18': dependents_over_18,
                    'labor_insurance_override': labor_override,
                    'health_insurance_override': health_override,
                    'pension_override': pension_override,
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d') if end_date else None,
                    'note': note
                }
                q_common.add_record(conn, 'salary_base_history', data)
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
                    dependents_under_18_edit = c2.number_input("健保眷屬數(<18歲)*", min_value=0.0, step=0.5, format="%.2f", value=float(record_data.get('dependents_under_18', 0)))
                    dependents_over_18_edit = c3.number_input("健保眷屬數(>=18歲)*", min_value=0.0, step=0.5, format="%.2f", value=float(record_data.get('dependents_over_18', 0)))
                    
                    c4, c5 = st.columns(2)
                    start_date_edit = c4.date_input("生效日*", value=to_date(record_data.get('start_date')))
                    end_date_edit = c5.date_input("結束日", value=to_date(record_data.get('end_date')))
                    note_edit = st.text_area("備註", value=record_data.get('note') or "")
                    
                    st.markdown("##### 手動調整 (選填，若填寫將覆蓋自動計算)")
                    c6, c7, c8 = st.columns(3)
                    labor_override_edit = c6.number_input("勞保費(手動)", min_value=0, step=1, value=record_data.get('labor_insurance_override'))
                    health_override_edit = c7.number_input("健保費(手動)", min_value=0, step=1, value=record_data.get('health_insurance_override'))
                    pension_override_edit = c8.number_input("勞退提撥(手動)", min_value=0, step=1, value=record_data.get('pension_override'))

                    c_update, c_delete = st.columns(2)
                    if c_update.form_submit_button("儲存變更", use_container_width=True):
                        insurance_salary_edit = q_ins.get_insurance_salary_level(conn, base_salary_edit)
                        updated_data = {
                            'base_salary': base_salary_edit,
                            'insurance_salary': insurance_salary_edit,
                            'dependents_under_18': dependents_under_18_edit,
                            'dependents_over_18': dependents_over_18_edit,
                            'dependents_over_18': dependents_over_18_edit,
                            'labor_insurance_override': labor_override_edit,
                            'health_insurance_override': health_override_edit,
                            'pension_override': pension_override_edit,
                            'start_date': start_date_edit.strftime('%Y-%m-%d') if start_date_edit else None,
                            'end_date': end_date_edit.strftime('%Y-%m-%d') if end_date_edit else None,
                            'note': note_edit
                        }
                        q_common.update_record(conn, 'salary_base_history', record_id, updated_data)
                        st.success(f"紀錄 ID:{record_id} 已更新！")
                        st.rerun()

                    if c_delete.form_submit_button("🔴 刪除此紀錄", use_container_width=True, type="primary"):
                        q_common.delete_record(conn, 'salary_base_history', record_id)
                        st.warning(f"紀錄 ID:{record_id} 已刪除！")
                        st.rerun()
        else:
            st.info("目前沒有可供修改或刪除的紀錄。")

    with tab3:
        create_batch_import_section(
            info_text="說明：系統會以「員工姓名」和「生效日」為唯一鍵，若紀錄已存在則會更新，否則新增。投保薪資將會依據底薪自動從級距表帶入。",
            template_columns=SALARY_BASE_TEMPLATE_COLUMNS,
            template_file_name="salary_base_template.xlsx",
            import_logic_func=logic_base.batch_import_salary_base,
            conn=conn
        )