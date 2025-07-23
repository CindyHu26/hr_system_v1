# page_allowance_setting.py (已整合批次修改功能的完整版)
import streamlit as st
import pandas as pd
from datetime import datetime, date
from utils import get_all_employees
from utils_salary_crud import (
    get_all_salary_items,
    get_employee_salary_items,
    get_settings_grouped_by_amount,
    batch_add_employee_salary_items,
    update_employee_salary_item,
    batch_update_employee_salary_items,
    delete_employee_salary_item
)
from components import employee_selector

def show_page(conn):
    st.header("員工常態薪資項設定")
    st.info("您可以在此批次新增、批次修改或編輯單筆固定的津貼/扣款項目。")

    # --- 讀取所有設定，供後續使用 ---
    try:
        all_settings_df = get_employee_salary_items(conn)
    except Exception as e:
        st.error(f"讀取設定總覽時發生錯誤: {e}")
        all_settings_df = pd.DataFrame()

    # --- 使用 Tabs 分隔主要操作 ---
    tab1, tab2 = st.tabs([" ✨ 新增/修改設定", "📖 所有設定總覽"])

    with tab1:
        st.subheader("新增或修改設定")
        
        # 建立操作模式選項
        mode = st.radio("選擇操作模式", ("批次新增", "批次修改", "編輯單筆"), horizontal=True, key="allowance_mode")

        # --- 模式一：批次新增 ---
        if mode == "批次新增":
            st.markdown("##### 為一群員工 **新增** 一個新的項目")
            try:
                item_df = get_all_salary_items(conn, active_only=True)
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
                    
                    submitted = st.form_submit_button("批次新增設定", type="primary", use_container_width=True)
                    if submitted:
                        if not selected_item_name or not selected_employee_ids:
                            st.error("請務必選擇「薪資項目」和至少一位「員工」！")
                        else:
                            item_id = item_options[selected_item_name]
                            with st.spinner("正在為選定員工儲存設定..."):
                                count = batch_add_employee_salary_items(conn, selected_employee_ids, item_id, amount, start_date, end_date, note)
                            st.success(f"成功為 {count} 位員工新增了「{selected_item_name}」的設定！")
                            st.rerun()
            except Exception as e:
                st.error(f"載入新增表單時發生錯誤: {e}")

        # --- 模式二：批次修改 ---
        elif mode == "批次修改":
            st.markdown("##### 對擁有 **同項目、同金額** 的一群員工進行統一修改")
            try:
                item_df = get_all_salary_items(conn, active_only=True)
                item_options = dict(zip(item_df['name'], item_df['id']))
                
                # 步驟 1: 選擇要修改的項目
                selected_item_name = st.selectbox(
                    "1. 請先選擇要修改的薪資項目*", 
                    options=[None] + list(item_options.keys())
                )

                if selected_item_name:
                    item_id = item_options[selected_item_name]
                    # 獲取按金額分組的員工資料
                    grouped_settings = get_settings_grouped_by_amount(conn, item_id)

                    if not grouped_settings:
                        st.warning(f"目前沒有任何員工被設定「{selected_item_name}」。")
                    else:
                        # 步驟 2: 選擇要修改的金額群組
                        amount_options = {
                            f"金額: {amount} (共 {len(employees)} 人)": amount
                            for amount, employees in grouped_settings.items()
                        }
                        selected_amount_key = st.selectbox(
                            "2. 選擇要修改的金額群組*",
                            options=[None] + list(amount_options.keys())
                        )
                        
                        if selected_amount_key:
                            selected_amount = amount_options[selected_amount_key]
                            employees_in_group = grouped_settings[selected_amount]
                            employee_ids_in_group = [emp['employee_id'] for emp in employees_in_group]

                            st.markdown("##### 屬於此群組的員工：")
                            names = ", ".join([emp['name_ch'] for emp in employees_in_group])
                            st.info(names)
                            
                            # 步驟 3: 輸入新設定並提交
                            with st.form("batch_update_allowance_form"):
                                st.markdown("##### 3. 輸入新的設定")
                                new_amount = st.number_input("統一修改為此金額*", min_value=0, step=100, value=int(selected_amount))
                                new_start_date = st.date_input("統一修改為此生效日*", value=datetime.now())
                                new_end_date = st.date_input("統一修改為此結束日", value=None)
                                new_note = st.text_input("統一修改為此備註")
                                
                                submitted = st.form_submit_button("確認批次修改此群組", type="primary", use_container_width=True)
                                if submitted:
                                    new_data = {
                                        'amount': new_amount,
                                        'start_date': new_start_date,
                                        'end_date': new_end_date,
                                        'note': new_note
                                    }
                                    count = batch_update_employee_salary_items(conn, employee_ids_in_group, item_id, new_data)
                                    st.success(f"成功更新了 {count} 筆「{selected_item_name}」的設定！")
                                    st.rerun()

            except Exception as e:
                st.error(f"載入批次修改表單時發生錯誤: {e}")

        # --- 模式三：編輯單筆 ---
        elif mode == "編輯單筆":
            st.markdown("##### 編輯單一筆特定的設定紀錄")
            if not all_settings_df.empty:
                options_to_edit = {
                    f"ID:{row.id} - {row.員工姓名} - {row.項目名稱} ({row.金額})": row.id
                    for index, row in all_settings_df.iterrows()
                }
                selected_to_edit_key = st.selectbox("選擇要編輯的紀錄", options=options_to_edit.keys(), index=None, placeholder="請從下方總覽中選擇一筆紀錄...")

                if selected_to_edit_key:
                    record_id = options_to_edit[selected_to_edit_key]
                    record_data = all_settings_df[all_settings_df['id'] == record_id].iloc[0]

                    with st.form("edit_allowance_form"):
                        st.markdown(f"#### 正在編輯 ID: {record_id}")
                        st.info(f"員工：**{record_data['員工姓名']}**\n\n項目：**{record_data['項目名稱']}**")

                        # 將日期字串安全地轉換為 date 物件
                        start_date_val = pd.to_datetime(record_data['生效日']).date() if pd.notna(record_data['生效日']) else None
                        end_date_val = pd.to_datetime(record_data['結束日']).date() if pd.notna(record_data['結束日']) else None

                        amount_edit = st.number_input("設定金額", min_value=0, step=100, value=int(record_data['金額']))
                        start_date_edit = st.date_input("生效日", value=start_date_val)
                        end_date_edit = st.date_input("結束日 (可設為空)", value=end_date_val)
                        note_edit = st.text_input("備註", value=str(record_data.get('備註', '') or ''))

                        submitted_edit = st.form_submit_button("儲存變更", type="primary")
                        if submitted_edit:
                            updated_data = {
                                'amount': amount_edit,
                                'start_date': start_date_edit,
                                'end_date': end_date_edit,
                                'note': note_edit
                            }
                            update_employee_salary_item(conn, record_id, updated_data)
                            st.success(f"紀錄 ID:{record_id} 已成功更新！")
                            st.rerun()
            else:
                st.info("目前沒有可供編輯的紀錄。")
    
    with tab2:
        st.subheader("目前所有常態設定總覽")
        if not all_settings_df.empty:
            st.dataframe(all_settings_df, use_container_width=True)
            
            with st.expander("🗑️ 刪除單筆設定"):
                options_to_delete = {
                    f"ID:{row.id} - {row.員工姓名} - {row.項目名稱} ({row.金額})": row.id
                    for index, row in all_settings_df.iterrows()
                }
                selected_to_delete_key = st.selectbox("選擇要刪除的紀錄", options=options_to_delete.keys(), key="delete_select")
                if st.button("確認刪除選定紀錄", type="primary", key="delete_button"):
                    record_id_to_delete = options_to_delete[selected_to_delete_key]
                    delete_employee_salary_item(conn, record_id_to_delete)
                    st.success(f"紀錄 ID:{record_id_to_delete} 已成功刪除！")
                    st.rerun()
        else:
            st.info("目前沒有任何常態薪資項設定。")