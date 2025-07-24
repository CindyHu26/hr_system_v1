# pages/allowance_setting.py
import streamlit as st
import pandas as pd
from datetime import datetime

# 導入新架構的模組
from db import queries_salary_items as q_items
from db import queries_allowances as q_allow
from db import queries_common as q_common
from utils.ui_components import employee_selector

def show_page(conn):
    st.header("➕ 員工常態薪資項設定")
    st.info("您可以在此批次新增、或單獨編輯員工固定的津貼/扣款項目。")

    try:
        all_settings_df = q_allow.get_all_employee_salary_items(conn)
    except Exception as e:
        st.error(f"讀取設定總覽時發生錯誤: {e}")
        all_settings_df = pd.DataFrame()

    tab1, tab2 = st.tabs([" ✨ 新增/修改設定", "📖 所有設定總覽"])

    with tab1:
        st.subheader("批次新增設定")
        st.markdown("為一群員工 **新增** 一個新的常態薪資項目。如果員工已存在該項目，原設定將被覆蓋。")
        try:
            item_df = q_items.get_all_salary_items(conn, active_only=True)
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
        except Exception as e:
            st.error(f"載入新增表單時發生錯誤: {e}")

    with tab2:
        st.subheader("目前所有常態設定總覽")
        if not all_settings_df.empty:
            st.dataframe(all_settings_df, use_container_width=True)
            
            with st.expander("🗑️ 刪除單筆設定"):
                options_to_delete = {
                    f"ID:{row['id']} - {row['員工姓名']} - {row['項目名稱']} ({row['金額']})": row['id']
                    for _, row in all_settings_df.iterrows()
                }
                selected_key = st.selectbox("選擇要刪除的紀錄", options=options_to_delete.keys(), key="delete_select", index=None)
                if st.button("確認刪除選定紀錄", type="primary", key="delete_button"):
                    if selected_key:
                        record_id_to_delete = options_to_delete[selected_key]
                        q_common.delete_record(conn, 'employee_salary_item', record_id_to_delete)
                        st.success(f"紀錄 ID:{record_id_to_delete} 已成功刪除！")
                        st.rerun()
                    else:
                        st.warning("請先選擇一筆要刪除的紀錄。")
        else:
            st.info("目前沒有任何常態薪資項設定。")