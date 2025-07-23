# page_salary_base_history.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
from utils import (
    get_all_employees,
)
from utils_salary_crud import (
    get_salary_base_history,
    add_salary_base_history,
    update_salary_base_history,
    delete_salary_base_history,
    get_employees_below_minimum_wage,
    batch_update_basic_salary,
    SALARY_BASE_HISTORY_COLUMNS_MAP
)

def show_page(conn):
    """
    顯示員工底薪與眷屬異動管理頁面 (CRUD)
    """
    st.header("員工底薪／眷屬異動管理")
    st.info("管理每位員工的歷次調薪、眷屬數量變更紀錄。所有異動都應在此留下歷史軌跡。")

    # ---【新功能】一鍵更新基本工資 ---
    st.write("---")
    st.subheader("一鍵更新基本工資")
    
    # 根據搜尋結果，設定 2025 年基本工資
    LEGAL_MINIMUM_WAGE_2025 = 28590
    
    c1, c2 = st.columns([1, 1])
    new_wage = c1.number_input(
        "設定新的基本工資", 
        min_value=0, 
        value=LEGAL_MINIMUM_WAGE_2025,
        help=f"根據勞動部公告，2025年基本工資為 NT$ {LEGAL_MINIMUM_WAGE_2025}"
    )
    effective_date = c2.date_input("設定新制生效日", value=date(2025, 1, 1))

    if st.button("Step 1: 預覽將被更新的員工"):
        with st.spinner("正在篩選底薪低於新標準的員工..."):
            preview_df = get_employees_below_minimum_wage(conn, new_wage)
            st.session_state.salary_update_preview = preview_df
    
    if 'salary_update_preview' in st.session_state and not st.session_state.salary_update_preview.empty:
        st.write("##### 預覽清單：")
        st.dataframe(st.session_state.salary_update_preview, use_container_width=True)
        st.warning(f"共有 {len(st.session_state.salary_update_preview)} 位員工的底薪將從「目前底薪」調整為 NT$ {new_wage}。")
        
        if st.button("Step 2: 確認執行更新", type="primary"):
            with st.spinner("正在為以上員工批次新增調薪紀錄..."):
                count = batch_update_basic_salary(conn, st.session_state.salary_update_preview, new_wage, effective_date)
                st.success(f"成功為 {count} 位員工更新了基本工資！")
                # 清除預覽，避免重複操作
                del st.session_state.salary_update_preview
                st.rerun()

    # --- 1. 顯示所有歷史紀錄 (Read) ---
    st.subheader("歷史異動總覽")
    try:
        history_df_raw = get_salary_base_history(conn)
        history_df_display = history_df_raw.rename(columns=SALARY_BASE_HISTORY_COLUMNS_MAP)
        # 格式化眷屬數欄位以顯示小數
        if '眷屬數' in history_df_display.columns:
            history_df_display['眷屬數'] = history_df_display['眷屬數'].map('{:,.2f}'.format)
        st.dataframe(history_df_display, use_container_width=True)
    except Exception as e:
        st.error(f"讀取歷史紀錄時發生錯誤: {e}")
        return

    st.write("---")

    # --- 2. 操作區塊 (Create, Update, Delete) ---
    st.subheader("資料操作")
    
    # 使用選項卡區分操作
    tab1, tab2, tab3 = st.tabs([" ✨ 新增紀錄", "✏️ 修改紀錄", "🗑️ 刪除紀錄"])

    # --- 新增紀錄 ---
    with tab1:
        st.markdown("#### 新增一筆異動紀錄")
        try:
            emp_df = get_all_employees(conn)[['id', 'name_ch', 'hr_code']]
            emp_df['display'] = emp_df['name_ch'] + " (" + emp_df['hr_code'].astype(str) + ")"
            emp_options = dict(zip(emp_df['display'], emp_df['id']))

            with st.form("add_history_form", clear_on_submit=True):
                selected_emp_display = st.selectbox("選擇員工*", options=emp_options.keys())
                
                c1, c2 = st.columns(2)
                base_salary = c1.number_input("底薪*", min_value=0, step=100)
                dependents = c2.number_input("眷屬數*", min_value=0.0, step=0.01, format="%.2f")
                
                c3, c4 = st.columns(2)
                start_date = c3.date_input("生效日*", value=datetime.now())
                end_date = c4.date_input("結束日 (非必填)", value=None)
                
                note = st.text_area("備註 (可留空)")

                submitted = st.form_submit_button("確認新增")
                if submitted:
                    if not selected_emp_display:
                        st.error("請務必選擇一位員工！")
                    else:
                        employee_id = emp_options[selected_emp_display]
                        data = {
                            'employee_id': employee_id,
                            'base_salary': base_salary,
                            'dependents': dependents,
                            'start_date': start_date,
                            'end_date': end_date,
                            'note': note
                        }
                        add_salary_base_history(conn, data)
                        st.success(f"已成功為 {selected_emp_display.split(' ')[0]} 新增一筆異動紀錄！")
                        st.rerun()

        except Exception as e:
            st.error(f"準備新增表單時出錯: {e}")

    # --- 修改紀錄 ---
    with tab2:
        st.markdown("#### 修改現有紀錄")
        if not history_df_raw.empty:
            edit_options_df = history_df_raw.copy()
            edit_options_df['display'] = edit_options_df['name_ch'] + " (底薪: " + edit_options_df['base_salary'].astype(str) + ", 生效日: " + edit_options_df['start_date'] + ")"
            edit_options = dict(zip(edit_options_df['display'], edit_options_df['id']))

            selected_record_key = st.selectbox("選擇要修改的紀錄", options=edit_options.keys(), index=None, placeholder="請從列表中選擇...")

            if selected_record_key:
                record_id = edit_options[selected_record_key]
                record_data = history_df_raw[history_df_raw['id'] == record_id].iloc[0]

                with st.form("edit_history_form"):
                    st.write(f"正在編輯 **{record_data['name_ch']}** 的紀錄")
                    
                    c1, c2 = st.columns(2)
                    base_salary_edit = c1.number_input("底薪", min_value=0, step=100, value=int(record_data['base_salary']))
                    dependents_edit = c2.number_input("眷屬數", min_value=0.0, step=0.01, format="%.2f", value=float(record_data['dependents']))

                    # 安全地轉換日期
                    start_date_val = pd.to_datetime(record_data['start_date']).date() if pd.notna(record_data['start_date']) else None
                    end_date_val = pd.to_datetime(record_data['end_date']).date() if pd.notna(record_data['end_date']) else None

                    c3, c4 = st.columns(2)
                    start_date_edit = c3.date_input("生效日", value=start_date_val)
                    end_date_edit = c4.date_input("結束日 (非必填)", value=end_date_val)
                    
                    note_edit = st.text_area("備註", value=record_data.get('note', '') or '')
                    
                    update_submitted = st.form_submit_button("儲存變更")
                    if update_submitted:
                        updated_data = {
                            'base_salary': base_salary_edit,
                            'dependents': dependents_edit,
                            'start_date': start_date_edit,
                            'end_date': end_date_edit,
                            'note': note_edit
                        }
                        update_salary_base_history(conn, record_id, updated_data)
                        st.success(f"紀錄 ID: {record_id} 已成功更新！")
                        st.rerun()
        else:
            st.info("目前沒有可供修改的歷史紀錄。")

    # --- 刪除紀錄 ---
    with tab3:
        st.markdown("#### 刪除異動紀錄")
        if not history_df_raw.empty:
            delete_options_df = history_df_raw.copy()
            delete_options_df['display'] = delete_options_df['name_ch'] + " (底薪: " + delete_options_df['base_salary'].astype(str) + ", 生效日: " + delete_options_df['start_date'] + ")"
            delete_options = dict(zip(delete_options_df['display'], delete_options_df['id']))

            record_to_delete_key = st.selectbox("選擇要刪除的紀錄", options=delete_options.keys(), index=None, placeholder="請從列表中選擇...", key="delete_select")
            
            if record_to_delete_key:
                record_to_delete_id = delete_options[record_to_delete_key]
                st.warning(f"⚠️ 您確定要永久刪除此筆紀錄嗎？\n> {record_to_delete_key}")
                
                if st.button("🔴 我確定，請刪除", type="primary"):
                    try:
                        delete_salary_base_history(conn, record_to_delete_id)
                        st.success(f"已成功刪除紀錄 ID: {record_to_delete_id}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"刪除時發生錯誤: {e}")
        else:
            st.info("目前沒有可供刪除的歷史紀錄。")