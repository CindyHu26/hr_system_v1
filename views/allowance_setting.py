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

    # [核心修改] 建立新的三頁籤結構
    tab1, tab2, tab3 = st.tabs(["📖 總覽與快速修改", "✨ 批次新增設定", "🚀 批次匯入 (Excel)"])

    # --- TAB 1: 總覽與快速修改 (新功能) ---
    with tab1:
        st.subheader("常態薪資項總覽 (可直接修改)")
        try:
            # 1. 獲取原始的長表資料
            long_df = q_allow.get_all_employee_salary_items(conn)

            if not long_df.empty:
                # 2. 建立一個 (員工ID, 項目名稱) -> 紀錄ID 的查詢字典，供後續更新使用
                id_mapper = {
                    (row['employee_id'], row['項目名稱']): row['id']
                    for _, row in long_df.iterrows()
                }

                # 3. 使用 pivot_table 將長表轉為寬表
                wide_df = long_df.pivot_table(
                    index=['employee_id', '員工姓名'],
                    columns='項目名稱',
                    values='金額'
                ).reset_index()
                
                # 將 employee_id 設為索引，方便後續操作，但不在表格中顯示
                wide_df.set_index('employee_id', inplace=True)

                # 儲存原始資料以供比對
                if 'original_allowance_df' not in st.session_state:
                    st.session_state.original_allowance_df = wide_df.copy()

                # 4. 使用 data_editor 顯示可編輯的表格
                st.caption("您可以直接在下表中修改金額。修改後請點擊下方的「儲存變更」按鈕。")
                edited_df = st.data_editor(wide_df, use_container_width=True)

                # 5. 儲存變更的邏輯
                if st.button("💾 儲存變更", type="primary"):
                    original_df = st.session_state.original_allowance_df
                    # 找出被修改過的儲存格
                    changes = edited_df.compare(original_df)
                    
                    if changes.empty:
                        st.info("沒有偵測到任何變更。")
                    else:
                        updates_count = 0
                        with st.spinner("正在儲存變更..."):
                            # 遍歷所有被修改的儲存格
                            for (emp_id, emp_name), row in changes.iterrows():
                                for item_name, values in row.items():
                                    # `compare` 會顯示 self (修改後) 和 other (修改前)
                                    old_val, new_val = values['other'], values['self']
                                    if pd.notna(new_val): # 只處理有新值的
                                        record_id = id_mapper.get((emp_id, item_name))
                                        if record_id:
                                            q_common.update_record(conn, 'employee_salary_item', record_id, {'amount': new_val})
                                            updates_count += 1
                        
                        st.success(f"成功更新了 {updates_count} 筆設定！")
                        # 清除 session state 以便下次重新載入
                        del st.session_state.original_allowance_df
                        st.rerun()

            else:
                st.info("目前沒有任何常態薪資項設定。")

        except Exception as e:
            st.error(f"載入總覽頁面時發生錯誤: {e}")


    # --- TAB 2: 批次新增設定 (保留舊功能) ---
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
                        start_date = st.date_input("生效日*", value=datetime.now())
                        end_date = st.date_input("結束日 (留空表示持續有效)", value=None)
                        note = st.text_input("備註 (可選填)")
                    with col_emp:
                        st.markdown("##### 2. 選擇要套用的員工")
                        selected_employee_ids = employee_selector(conn, key_prefix="allowance_add")
                    
                    if st.form_submit_button("批次新增/覆蓋設定", type="primary", use_container_width=True):
                        if not selected_item_name or not selected_employee_ids:
                            st.error("請務必選擇「薪資項目」和至少一位「員工」！")
                        else:
                            item_id = item_options[selected_item_name]
                            start_date_str = start_date.strftime('%Y-%m-%d')
                            end_date_str = end_date.strftime('%Y-%m-%d') if end_date else None
                            with st.spinner("正在為選定員工儲存設定..."):
                                count = q_allow.batch_add_or_update_employee_salary_items(
                                    conn, selected_employee_ids, item_id, amount, 
                                    start_date_str, end_date_str, note
                                )
                            st.success(f"成功為 {count} 位員工新增/更新了「{selected_item_name}」的設定！")
                            st.rerun()
            else:
                st.warning("沒有可用的薪資項目。請先至「薪資項目管理」頁面新增項目。")
        except Exception as e:
            st.error(f"載入新增表單時發生錯誤: {e}")

    # --- TAB 3: 批次匯入 (Excel) (保留舊功能) ---
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