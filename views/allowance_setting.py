# views/allowance_setting.py
import streamlit as st
import pandas as pd
from datetime import datetime

from db import queries_salary_items as q_items
from db import queries_allowances as q_allow
from db import queries_common as q_common
from utils.ui_components import employee_selector, create_batch_import_section
from services import allowance_logic as logic_allow

def show_page(conn):
    st.header("➕ 員工常態薪資項設定")
    st.info("您可以在此總覽與快速修改現有設定，或透過批次功能進行大量新增。")

    # 頁籤結構維持不變
    tab1, tab2, tab3 = st.tabs(["📖 總覽與單筆維護", "✨ 批次新增設定", "🚀 批次匯入 (Excel)"])

    # --- TAB 1: 總覽與單筆維護 (整合版) ---
    with tab1:
        st.subheader("常態薪資項總覽 (可直接修改金額)")
        try:
            # 1. 獲取原始的長表資料
            long_df = q_allow.get_all_employee_salary_items(conn)

            if not long_df.empty:
                # 2. 建立查詢字典，供後續更新使用
                id_mapper = {
                    (row['employee_id'], row['項目名稱']): row['id']
                    for _, row in long_df.iterrows()
                }

                # 3. 轉換為寬表 (Pivot Table)
                wide_df = long_df.pivot_table(
                    index=['employee_id', '員工姓名'],
                    columns='項目名稱',
                    values='金額'
                ).reset_index()
                
                wide_df.set_index('employee_id', inplace=True)

                # 儲存原始資料以供比對
                if 'original_allowance_df' not in st.session_state:
                    st.session_state.original_allowance_df = wide_df.copy()

                # 4. 使用 data_editor 顯示表格，用於快速修改金額
                st.caption("您可以直接在下表中修改金額。修改後請點擊下方的「儲存變更」按鈕。")
                edited_df = st.data_editor(wide_df, use_container_width=True, key="allowance_editor")

                # 5. 儲存來自 data_editor 的變更
                if st.button("💾 儲存表格變更", type="primary"):
                    original_df = st.session_state.original_allowance_df
                    changes = edited_df.compare(original_df)
                    
                    if changes.empty:
                        st.info("沒有偵測到任何變更。")
                    else:
                        updates_count = 0
                        with st.spinner("正在儲存變更..."):
                            for emp_id, changed_row in changes.iterrows():
                                changed_columns = changed_row.dropna().index.get_level_values(0).unique()
                                for item_name in changed_columns:
                                    new_value = changed_row.get((item_name, 'self'))
                                    record_id = id_mapper.get((emp_id, item_name))
                                    if record_id is not None:
                                        amount_to_save = 0 if pd.isna(new_value) else new_value
                                        q_common.update_record(conn, 'employee_salary_item', record_id, {'amount': amount_to_save})
                                        updates_count += 1
                        
                        st.success(f"成功更新了 {updates_count} 筆設定！")
                        del st.session_state.original_allowance_df
                        st.rerun()

            else:
                st.info("目前沒有任何常態薪資項設定。")

        except Exception as e:
            st.error(f"載入總覽頁面時發生錯誤: {e}")
            long_df = pd.DataFrame() # 確保 long_df 存在

        st.markdown("---")
        st.subheader("單筆資料操作")

        # --- 新增區塊 ---
        with st.expander("✨ 新增一筆設定"):
            with st.form("add_allowance_form_single", clear_on_submit=True):
                employees = q_common.get_all(conn, 'employee', order_by='hr_code')
                items = q_items.get_all_salary_items(conn, active_only=True)

                emp_options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in employees.iterrows()}
                item_options = {row['name']: row['id'] for _, row in items.iterrows()}

                c1, c2, c3 = st.columns(3)
                emp_key = c1.selectbox("選擇員工*", options=emp_options.keys(), index=None)
                item_key = c2.selectbox("選擇薪資項目*", options=item_options.keys(), index=None)
                amount = c3.number_input("設定金額*", min_value=0, step=100)
                
                c4, c5 = st.columns(2)
                start_date = c4.date_input("生效日*", value=datetime.now().date())
                end_date = c5.date_input("結束日 (留空表示持續有效)", value=None)
                
                note = st.text_area("備註 (可選填)")

                if st.form_submit_button("確認新增", type="primary"):
                    if not all([emp_key, item_key]):
                        st.warning("請務必選擇員工和薪資項目！")
                    else:
                        new_data = {
                            'employee_id': emp_options[emp_key],
                            'salary_item_id': item_options[item_key],
                            'amount': amount,
                            'start_date': start_date.strftime('%Y-%m-%d'),
                            'end_date': end_date.strftime('%Y-%m-%d') if end_date else None,
                            'note': note
                        }
                        q_common.add_record(conn, 'employee_salary_item', new_data)
                        st.success("成功新增一筆設定！")
                        if 'original_allowance_df' in st.session_state:
                            del st.session_state.original_allowance_df
                        st.rerun()

        # --- 刪除區塊 ---
        with st.expander("🗑️ 刪除現有設定"):
            if not long_df.empty:
                # 建立更詳細的選項文字，方便使用者辨識
                record_options = {
                    f"ID:{row['id']} - {row['員工姓名']} / {row['項目名稱']} / 金額:{row['金額']} (生效:{row['生效日']})": row['id']
                    for _, row in long_df.iterrows()
                }
                selected_key = st.selectbox(
                    "選擇一筆設定進行刪除", 
                    options=record_options.keys(), 
                    index=None,
                    placeholder="點此選擇要刪除的舊紀錄或錯誤紀錄..."
                )
                if st.button("🔴 確認刪除所選紀錄", type="primary"):
                    if selected_key:
                        record_id = record_options[selected_key]
                        q_common.delete_record(conn, 'employee_salary_item', record_id)
                        st.warning(f"ID: {record_id} 的紀錄已刪除！")
                        if 'original_allowance_df' in st.session_state:
                            del st.session_state.original_allowance_df
                        st.rerun()
                    else:
                        st.warning("請先選擇一筆要刪除的紀錄。")
            else:
                st.info("目前沒有可供刪除的紀錄。")

    # --- TAB 2: 批次新增設定 (維持不變) ---
    with tab2:
        st.subheader("批次新增設定")
        st.markdown("為一群員工 **新增** 一個新的常態薪資項目。如果員工已存在該項目，原設定將被覆蓋。")
        try:
            item_df = q_items.get_all_salary_items(conn, active_only=True)
            if not item_df.empty:
                item_options = dict(zip(item_df['name'], item_df['id']))

                with st.form("add_allowance_form"):
                    col_item, col_emp = st.columns([1, 2])
                    with col_item:
                        st.markdown("##### 1. 選擇項目與金額")
                        selected_item_name = st.selectbox("薪資項目*", options=item_options.keys())
                        amount = st.number_input("設定金額*", min_value=0, step=100)
                        # 【核心修正】在這裡加入日期選擇
                        start_date_batch = st.date_input("生效日*", value=datetime.now())
                        end_date_batch = st.date_input("結束日 (留空表示持續有效)", value=None)
                        note_batch = st.text_input("備註 (可選填)")
                    with col_emp:
                        st.markdown("##### 2. 選擇要套用的員工")
                        selected_employee_ids = employee_selector(conn, key_prefix="allowance_add")
                    
                    if st.form_submit_button("批次新增/覆蓋設定", type="primary", use_container_width=True):
                        if not selected_item_name or not selected_employee_ids:
                            st.error("請務必選擇「薪資項目」和至少一位「員工」！")
                        else:
                            item_id = item_options[selected_item_name]
                            # 【核心修正】使用新的日期變數
                            start_date_str = start_date_batch.strftime('%Y-%m-%d')
                            end_date_str = end_date_batch.strftime('%Y-%m-%d') if end_date_batch else None
                            with st.spinner("正在為選定員工儲存設定..."):
                                count = q_allow.batch_add_or_update_employee_salary_items(
                                    conn, selected_employee_ids, item_id, amount, 
                                    start_date_str, end_date_str, note_batch
                                )
                            st.success(f"成功為 {count} 位員工新增/更新了「{selected_item_name}」的設定！")
                            if 'original_allowance_df' in st.session_state:
                                del st.session_state.original_allowance_df
                            st.rerun()
            else:
                st.warning("沒有可用的薪資項目。請先至「薪資項目管理」頁面新增項目。")
        except Exception as e:
            st.error(f"載入新增表單時發生錯誤: {e}")

    # --- TAB 3: 批次匯入 (Excel) (維持不變) ---
    with tab3:
        create_batch_import_section(
            info_text="說明：系統會以「員工姓名 + 項目名稱 + 生效日」為唯一鍵，若紀錄已存在則會更新，否則新增。",
            template_columns={
                'name_ch': '員工姓名*', 'item_name': '項目名稱*', 'amount': '金額*',
                'start_date': '生效日*(YYYY-MM-DD)', 'end_date': '結束日(YYYY-MM-DD)', 'note': '備註'
            },
            template_file_name="allowances_template.xlsx",
            import_logic_func=logic_allow.batch_import_allowances,
            conn=conn
        )