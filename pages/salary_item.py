# page_salary_item.py
import streamlit as st
import pandas as pd
import sqlite3
from utils_salary_crud import (
    get_all_salary_items,
    add_salary_item,
    update_salary_item,
    delete_salary_item,
    SALARY_ITEM_COLUMNS_MAP
)

def show_page(conn):
    """
    顯示薪資項目管理頁面 (CRUD)
    """
    st.header("薪資項目管理 (Salary Item)")
    st.info("您可以在此頁面統一管理薪資單中的所有「給付」或「扣除」項目。")

    # --- 1. 顯示現有項目 (Read) ---
    st.subheader("目前所有薪資項目")
    try:
        items_df_raw = get_all_salary_items(conn)
        # 使用中文欄位名稱顯示
        items_df_display = items_df_raw.rename(columns=SALARY_ITEM_COLUMNS_MAP)
        st.dataframe(items_df_display, use_container_width=True)
    except Exception as e:
        st.error(f"讀取薪資項目時發生錯誤：{e}")
        return

    st.write("---")

    # --- 2. 新增與修改 (Create / Update) ---
    with st.expander("新增或修改薪資項目", expanded=True):
        # 使用 session state 來儲存正在編輯的項目
        if 'editing_item_id' not in st.session_state:
            st.session_state.editing_item_id = None

        # 建立選擇列表，讓使用者選擇要編輯的項目或新增
        item_list = {" ✨ 新增一個項目": None}
        item_list.update({f"{row['name']} (ID: {row['id']})": row['id'] for _, row in items_df_raw.iterrows()})

        selected_item_key = st.selectbox("選擇要操作的項目", options=item_list.keys(), help="選擇「新增」來建立項目，或選擇一個現有項目進行編輯。")
        st.session_state.editing_item_id = item_list[selected_item_key]

        # 根據選擇顯示對應的表單
        item_data = {}
        if st.session_state.editing_item_id:
            # 編輯模式
            item_data = items_df_raw[items_df_raw['id'] == st.session_state.editing_item_id].iloc[0]
            form_title = "✏️ 編輯薪資項目"
            button_label = "儲存變更"
        else:
            # 新增模式
            form_title = "➕ 新增薪資項目"
            button_label = "確認新增"

        with st.form("salary_item_form", clear_on_submit=False):
            st.markdown(f"**{form_title}**")
            name = st.text_input("項目名稱*", value=item_data.get('name', ''), help="例如：底薪、伙食津貼、勞健保費")
            type_options = {'earning': '給付 (Earning)', 'deduction': '扣除 (Deduction)'}
            # 反向查找當前選項的 key
            current_type_key = item_data.get('type', 'earning')
            type = st.selectbox("項目類型*", options=list(type_options.keys()), format_func=lambda x: type_options[x], index=list(type_options.keys()).index(current_type_key))
            is_active = st.checkbox("啟用此項目", value=item_data.get('is_active', True), help="取消勾選可暫時停用此項目，但不會刪除。")

            submitted = st.form_submit_button(button_label)
            if submitted:
                if not name.strip():
                    st.error("「項目名稱」為必填欄位！")
                else:
                    new_data = {'name': name.strip(), 'type': type, 'is_active': is_active}
                    try:
                        if st.session_state.editing_item_id:
                            # 更新
                            update_salary_item(conn, st.session_state.editing_item_id, new_data)
                            st.success(f"✅ 成功更新項目：{name}")
                        else:
                            # 新增
                            add_salary_item(conn, new_data)
                            st.success(f"✅ 成功新增項目：{name}")

                        # 清除狀態並強制重新整理頁面
                        st.session_state.editing_item_id = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 操作失敗：{e}")

    # --- 3. 刪除項目 (Delete) ---
    st.write("---")
    st.subheader("刪除薪資項目")
    if not items_df_raw.empty:
        # 建立可供刪除的項目列表
        delete_options = {f"{row['name']} (ID: {row['id']})": row['id'] for _, row in items_df_raw.iterrows()}
        item_to_delete_key = st.selectbox("選擇要刪除的項目", options=delete_options.keys(), index=None, placeholder="請選擇...", key="delete_item_select")

        if item_to_delete_key:
            item_to_delete_id = delete_options[item_to_delete_key]
            st.warning(f"⚠️ 您確定要永久刪除「{item_to_delete_key}」嗎？此操作無法復原！")
            st.info("注意：如果某個項目已經在過去的薪資單中使用過，為了保持紀錄完整性，系統將不允許刪除。")

            if st.button("🔴 我確定，請刪除", type="primary"):
                try:
                    delete_salary_item(conn, item_to_delete_id)
                    st.success(f"✅ 已成功刪除項目：{item_to_delete_key}")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("❌ 刪除失敗：此項目已被薪資單引用，無法刪除。您可以將其狀態改為「停用」。")
                except Exception as e:
                    st.error(f"❌ 刪除時發生錯誤：{e}")
    else:
        st.info("目前沒有可刪除的項目。")