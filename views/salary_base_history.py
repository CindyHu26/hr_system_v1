# pages/salary_base_history.py
import streamlit as st
import pandas as pd
from datetime import datetime

from db import queries_common as q_common
from db import queries_salary_base as q_base
from db import queries_employee as q_emp
from db import queries_insurance as q_ins
from utils.helpers import to_date
from utils.ui_components import create_batch_import_section
from services import salary_base_logic as logic_base
from services.salary_logic import calculate_single_employee_insurance

# 範本欄位定義
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
    st.header("1️⃣ 薪資基準與保費管理")
    st.info("管理員工的薪資基準歷史，並直接預覽依此計算的勞健保費用。薪資單將以此處的資料為準。")

    # 統一使用頁籤管理功能
    tab1, tab2, tab3 = st.tabs(["📖 歷史紀錄總覽與維護", "🚀 批次匯入 (Excel)", "⚡️ 批次調整基本工資"])

    with tab1:
        st.subheader("歷史紀錄總覽")
        try:
            history_df_raw = q_base.get_salary_base_history(conn)

            if not history_df_raw.empty:
                fees_labor = []
                fees_health = []
                for _, row in history_df_raw.iterrows():
                    # 1. 取得手動覆蓋值
                    labor_override = row.get('labor_insurance_override')
                    health_override = row.get('health_insurance_override')
                    has_labor_override = pd.notna(labor_override)
                    has_health_override = pd.notna(health_override)

                    # 2. 執行自動計算，取得勞保費與「健保費基數」
                    start_date = pd.to_datetime(row['start_date'])
                    # 注意：calculate_single_employee_insurance 回傳的是最終總額，我們需要重新取得基數
                    _, health_fee_base = q_ins.get_employee_insurance_fee(
                        conn, row['insurance_salary'], start_date.year, start_date.month
                    )
                    auto_labor_fee, auto_health_total = calculate_single_employee_insurance(
                        conn, row['insurance_salary'],
                        row.get('dependents_under_18', 0), row.get('dependents_over_18', 0),
                        row.get('nhi_status', '一般'), row.get('nhi_status_expiry'),
                        start_date.year, start_date.month
                    )

                    # 3. 決定勞保費：有手動值就用，沒有就用自動計算值
                    final_labor_fee = int(labor_override) if has_labor_override else auto_labor_fee

                    # 4. 決定健保費
                    if has_health_override:
                        # 如果有手動值，則將其視為基數進行計算
                        final_health_fee_base = int(health_override)
                        dependents_count = float(row.get('dependents_under_18', 0)) + float(row.get('dependents_over_18', 0))
                        final_health_fee = int(round(final_health_fee_base * (1 + dependents_count)))
                        # 如果是自理，健保費應為0
                        if row.get('nhi_status') == '自理':
                            final_health_fee = 0
                    else:
                        # 如果沒有手動值，直接使用已包含眷屬計算的自動總額
                        final_health_fee = auto_health_total

                    fees_labor.append(final_labor_fee)
                    fees_health.append(final_health_fee)

                history_df_raw['預估勞保費'] = fees_labor
                history_df_raw['預估健保費'] = fees_health
                history_df_raw['預估勞健保總額'] = history_df_raw['預估勞保費'] + history_df_raw['預估健保費']

            display_df = history_df_raw.rename(columns={
                'name_ch': '員工姓名', 'base_salary': '底薪', 'insurance_salary': '投保薪資',
                'dependents_under_18': '眷屬(<18)', 'dependents_over_18': '眷屬(>=18)',
                'labor_insurance_override': '勞保費(手動)', 'health_insurance_override': '健保費(手動)',
                'pension_override': '勞退提撥(手動)',
                'start_date': '生效日', 'end_date': '結束日', 'note': '備註'
            })
            st.dataframe(display_df, width='stretch')

        except Exception as e:
            st.error(f"讀取歷史紀錄時發生錯誤: {e}")
            history_df_raw = pd.DataFrame()

        # --- 新增紀錄 ---
        with st.expander("✨ 新增一筆紀錄"):
            emp_df = q_emp.get_all_employees(conn)
            emp_options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in emp_df.iterrows()}

            with st.form("add_base_history", clear_on_submit=True):
                selected_emp_key = st.selectbox("選擇員工*", options=emp_options.keys())
                c1, c2, c3 = st.columns(3)
                base_salary = c1.number_input("底薪*", min_value=0)
                dependents_under_18 = c2.number_input("健保眷屬數(<18歲)*", min_value=0.0, step=1.00, format="%.2f")
                dependents_over_18 = c3.number_input("健保眷屬數(>=18歲)*", min_value=0.0, step=1.00, format="%.2f")
                
                c4, c5 = st.columns(2)
                start_date = c4.date_input("生效日*", value=datetime.now())
                end_date = c5.date_input("結束日 (留空表示持續有效)", value=None)
                note = st.text_area("備註")

                st.markdown("##### 手動調整 (選填，若填寫將覆蓋自動計算)")
                c6, c7, c8 = st.columns(3)
                labor_override = c6.number_input("勞保費(手動)", min_value=0, step=1, value=None, help="若填寫此欄位，薪資計算將優先使用此金額。")
                health_override = c7.number_input("健保費(手動)", min_value=0, step=1, value=None, help="若填寫此欄位，薪資計算將優先使用此金額。")
                pension_override = c8.number_input("勞退提撥(手動)", min_value=0, step=1, value=None, help="若填寫此欄位，薪資計算將優先使用此金額。")

                if st.form_submit_button("確認新增"):
                    insurance_salary = q_ins.get_insurance_salary_level(conn, base_salary)
                    data = {
                        'employee_id': emp_options[selected_emp_key], 'base_salary': base_salary,
                        'insurance_salary': insurance_salary, 'dependents_under_18': dependents_under_18,
                        'dependents_over_18': dependents_over_18, 'labor_insurance_override': labor_override,
                        'health_insurance_override': health_override, 'pension_override': pension_override,
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d') if end_date else None, 'note': note
                    }
                    q_common.add_record(conn, 'salary_base_history', data)
                    st.success("成功新增紀錄！")
                    st.rerun()

# --- 修改/刪除紀錄 ---
        with st.expander("✏️ 修改或刪除現有紀錄"):
            if not history_df_raw.empty:
                # 建立選單：顯示 ID、姓名與生效日
                options = {f"ID:{row['id']} - {row['name_ch']} (生效日: {row['start_date']})": row['id'] for _, row in history_df_raw.iterrows()}
                selected_key = st.selectbox("選擇要操作的紀錄", options.keys(), index=None, placeholder="從上方總覽選擇一筆紀錄...")

                if selected_key:
                    record_id = options[selected_key]
                    record_data = history_df_raw[history_df_raw['id'] == record_id].iloc[0].to_dict()
                    
                    with st.form(f"edit_base_history_{record_id}"):
                        st.write(f"正在編輯 **{record_data['name_ch']}** 的紀錄 (ID: {record_id})")
                        
                        # 1. 薪資與眷屬
                        c1, c2, c3 = st.columns(3)
                        base_salary_edit = c1.number_input("底薪*", min_value=0, value=int(record_data['base_salary']))
                        dependents_under_18_edit = c2.number_input("健保眷屬數(<18歲)*", min_value=0.0, step=1.00, format="%.2f", value=float(record_data.get('dependents_under_18', 0)))
                        dependents_over_18_edit = c3.number_input("健保眷屬數(>=18歲)*", min_value=0.0, step=1.00, format="%.2f", value=float(record_data.get('dependents_over_18', 0)))
                        
                        # 2. 日期與備註
                        c4, c5 = st.columns(2)
                        start_date_edit = c4.date_input("生效日*", value=to_date(record_data.get('start_date')))
                        end_date_edit = c5.date_input("結束日", value=to_date(record_data.get('end_date')))
                        note_edit = st.text_area("備註", value=record_data.get('note') or "")
                        
                        st.markdown("---")
                        st.markdown("##### 🔧 手動費用設定 (勾選代表手動指定，取消代表依系統計算)")
                        
                        # 3. 手動費用邏輯 (Checkbox + NumberInput)
                        
                        # (A) 勞保費手動設定
                        c6_a, c6_b = st.columns([1, 2])
                        labor_val = record_data.get('labor_insurance_override')
                        has_labor_val = pd.notna(labor_val) # 判斷原本是否有值
                        
                        # Checkbox: 決定是否要手動
                        use_labor = c6_a.checkbox("手動勞保費", value=has_labor_val, key=f"chk_labor_{record_id}")
                        if use_labor:
                            # 顯示輸入框 (若原本有值就用原本的，否則預設 0)
                            default_labor = int(labor_val) if has_labor_val else 0
                            labor_override_edit = c6_b.number_input("金額 (勞保)", min_value=0, step=1, value=default_labor, key=f"num_labor_{record_id}")
                        else:
                            # 未勾選 => 設為 None
                            labor_override_edit = None

                        # (B) 健保費手動設定
                        c7_a, c7_b = st.columns([1, 2])
                        health_val = record_data.get('health_insurance_override')
                        has_health_val = pd.notna(health_val)

                        use_health = c7_a.checkbox("手動健保費", value=has_health_val, key=f"chk_health_{record_id}")
                        if use_health:
                            default_health = int(health_val) if has_health_val else 0
                            health_override_edit = c7_b.number_input("金額 (健保)", min_value=0, step=1, value=default_health, key=f"num_health_{record_id}")
                        else:
                            health_override_edit = None

                        # (C) 勞退提撥手動設定
                        c8_a, c8_b = st.columns([1, 2])
                        pension_val = record_data.get('pension_override')
                        has_pension_val = pd.notna(pension_val)

                        use_pension = c8_a.checkbox("手動勞退", value=has_pension_val, key=f"chk_pension_{record_id}")
                        if use_pension:
                            default_pension = int(pension_val) if has_pension_val else 0
                            pension_override_edit = c8_b.number_input("金額 (勞退)", min_value=0, step=1, value=default_pension, key=f"num_pension_{record_id}")
                        else:
                            pension_override_edit = None

                        # 4. 按鈕區
                        c_update, c_delete = st.columns(2)
                        
                        if c_update.form_submit_button("💾 儲存變更", type="primary", width='stretch'):
                            insurance_salary_edit = q_ins.get_insurance_salary_level(conn, base_salary_edit)
                            
                            updated_data = {
                                'base_salary': base_salary_edit, 
                                'insurance_salary': insurance_salary_edit,
                                'dependents_under_18': dependents_under_18_edit, 
                                'dependents_over_18': dependents_over_18_edit,
                                
                                # 這裡的變數已經根據 Checkbox 決定是 數字 還是 None 了
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

                        if c_delete.form_submit_button("🔴 刪除此紀錄", width='stretch'):
                            q_common.delete_record(conn, 'salary_base_history', record_id)
                            st.warning(f"紀錄 ID:{record_id} 已刪除！")
                            st.rerun()
            else:
                st.info("目前沒有可供修改或刪除的紀錄。")

    with tab2:
        create_batch_import_section(
            info_text="說明：系統會以「員工姓名」和「生效日」為唯一鍵，若紀錄已存在則會更新，否則新增。投保薪資將會依據底薪自動從級距表帶入。",
            template_columns=SALARY_BASE_TEMPLATE_COLUMNS,
            template_file_name="salary_base_template.xlsx",
            import_logic_func=logic_base.batch_import_salary_base,
            conn=conn
        )

    with tab3:
        st.subheader("批次調整基本工資")
        st.warning("此功能會為所有目前底薪低於您所設定之「新基本工資」的在職員工，新增一筆調薪紀錄。")

        from db import queries_config as q_config # 局部導入
        
        today = datetime.now()
        current_minimum_wage = q_config.get_minimum_wage_for_year(conn, today.year)
        
        with st.form("batch_update_salary_form"):
            c1, c2 = st.columns(2)
            new_wage = c1.number_input(
                "新基本工資*", 
                min_value=20000, 
                step=100, 
                value=current_minimum_wage
            )
            effective_date = c2.date_input("統一調整生效日*", value=datetime(today.year, 1, 1))
            
            if st.form_submit_button("1. 預覽受影響的員工"):
                with st.spinner("正在查找底薪低於目標的員工..."):
                    df_to_update = q_base.get_employees_below_minimum_wage(conn, new_wage)
                    if df_to_update.empty:
                        st.success("太棒了！目前沒有任何在職員工的薪資低於您設定的金額。")
                        if 'df_to_update_salary' in st.session_state:
                            del st.session_state['df_to_update_salary']
                    else:
                        st.session_state.df_to_update_salary = df_to_update
            
        if 'df_to_update_salary' in st.session_state:
            st.markdown("---")
            st.markdown("#### 預覽與確認")
            df_preview = st.session_state.df_to_update_salary
            st.write(f"系統偵測到以下 {len(df_preview)} 位員工的底薪將從「目前底薪」被調整為 **{new_wage}** 元：")
            
            st.dataframe(df_preview[['員工姓名', '目前底薪', '目前投保薪資']], width='stretch')

            if st.button(f"2. 確認執行 {len(df_preview)} 位員工的批次調薪", type="primary"):
                with st.spinner("正在批次寫入調薪紀錄..."):
                    updated_count = q_base.batch_update_base_salary(conn, df_preview, new_wage, effective_date)
                    st.success(f"成功為 {updated_count} 位員工新增了調薪紀錄！")
                    del st.session_state.df_to_update_salary
                    st.rerun()