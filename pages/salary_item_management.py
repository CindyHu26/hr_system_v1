# pages/salary_item_management.py
import streamlit as st
import pandas as pd
import sqlite3

# 導入新的、拆分後的查詢模組
from db import queries_salary_items as q_items

def show_page(conn):
    """
    顯示薪資項目管理頁面 (CRUD)，已適配 v1 架構。
    """
    st.header("⚙️ 薪資項目管理")
    st.info("您可以在此頁面統一管理薪資單中的所有「給付 (earning)」或「扣除 (deduction)」項目。")

    # --- 1. 顯示現有項目 (Read) ---
    st.subheader("目前所有薪資項目")
    try:
        items_df_raw = q_items.get_all_salary_items(conn)
        # 使用中文欄位名稱顯示
        items_df_display = items_df_raw.rename(columns={
            'id': 'ID', 'name': '項目名稱',
            'type': '類型', 'is_active': '是否啟用'
        })
        # 將布林值轉換為更易讀的 '是'/'否'
        if '是否啟用' in items_df_display.columns:
            items_df_display['是否啟用'] = items_df_display['是否啟用'].apply(lambda x: '是' if x else '否')

        st.dataframe(items_df_display, use_container_width=True)
    except Exception as e:
        st.error(f"讀取薪資項目時發生錯誤：{e}")
        return

    st.write("---")

    # --- 2. 新增與修改 (Create / Update) ---
    with st.expander("新增或修改薪資項目", expanded=True):
        if 'editing_item_id' not in st.session_state:
            st.session_state.editing_item_id = None

        # 建立選擇列表
        item_list = {" ✨ 新增一個項目": None}
        item_list.update({f"{row['name']} (ID: {row['id']})": row['id'] for _, row in items_df_raw.iterrows()})

        selected_item_key = st.selectbox("選擇要操作的項目", options=list(item_list.keys()), help="選擇「新增」來建立項目，或選擇一個現有項目進行編輯。")
        st.session_state.editing_item_id = item_list[selected_item_key]

        item_data = {}
        if st.session_state.editing_item_id:
            item_data = items_df_raw[items_df_raw['id'] == st.session_state.editing_item_id].iloc[0].to_dict()
            form_title, button_label = "✏️ 編輯薪資項目", "儲存變更"
        else:
            form_title, button_label = "➕ 新增薪資項目", "確認新增"

        with st.form("salary_item_form"):
            st.markdown(f"**{form_title}**")
            name = st.text_input("項目名稱*", value=item_data.get('name', ''))
            
            type_options = {'earning': '給付 (Earning)', 'deduction': '扣除 (Deduction)'}
            current_type_key = item_data.get('type', 'earning')
            type_index = list(type_options.keys()).index(current_type_key)
            type = st.selectbox("項目類型*", options=list(type_options.keys()), format_func=lambda x: type_options[x], index=type_index)

            is_active = st.checkbox("啟用此項目", value=bool(item_data.get('is_active', True)))

            if st.form_submit_button(button_label, type="primary"):
                if not name.strip():
                    st.error("「項目名稱」為必填欄位！")
                else:
                    new_data = {'name': name.strip(), 'type': type, 'is_active': is_active}
                    try:
                        if st.session_state.editing_item_id:
                            q_items.update_salary_item(conn, st.session_state.editing_item_id, new_data)
                            st.success(f"✅ 成功更新項目：{name}")
                        else:
                            q_items.add_salary_item(conn, new_data)
                            st.success(f"✅ 成功新增項目：{name}")
                        
                        st.session_state.editing_item_id = None
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"❌ 操作失敗：項目名稱「{name.strip()}」可能已存在。")
                    except Exception as e:
                        st.error(f"❌ 操作失敗：{e}")

    # --- 3. 刪除項目 (Delete) ---
    st.write("---")
    st.subheader("🗑️ 刪除薪資項目")
    if not items_df_raw.empty:
        delete_options = {f"{row['name']} (ID: {row['id']})": row['id'] for _, row in items_df_raw.iterrows()}
        item_to_delete_key = st.selectbox("選擇要刪除的項目", options=delete_options.keys(), index=None, placeholder="請選擇...", key="delete_item_select")

        if item_to_delete_key:
            item_to_delete_id = delete_options[item_to_delete_key]
            st.warning(f"⚠️ 您確定要永久刪除「{item_to_delete_key}」嗎？此操作無法復原！")

            if st.button("🔴 我確定，請刪除"):
                try:
                    q_items.delete_salary_item(conn, item_to_delete_id)
                    st.success(f"✅ 已成功刪除項目：{item_to_delete_key}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 刪除失敗：{e}")
    else:
        st.info("目前沒有可刪除的項目。")