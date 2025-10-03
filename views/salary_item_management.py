# views/salary_item_management.py
import streamlit as st
import pandas as pd
import sqlite3

from db import queries_salary_items as q_items
from utils.ui_components import create_batch_import_section
from services import salary_item_logic as logic_items

def show_page(conn):
    """
    顯示薪資項目管理頁面 (CRUD)，已適配 v1 架構。
    """
    st.header("⚙️ 薪資項目管理")
    st.info("您可以在此頁面統一管理薪資單中的所有「給付 (earning)」或「扣除 (deduction)」項目。")

    items_df_raw = q_items.get_all_salary_items(conn)
    items_df_display = items_df_raw.rename(columns={
        'id': 'ID', 'name': '項目名稱', 'type': '類型', 'is_active': '是否啟用'
    })
    if '是否啟用' in items_df_display.columns:
        items_df_display['是否啟用'] = items_df_display['是否啟用'].apply(lambda x: '是' if x else '否')
    st.dataframe(items_df_display, width='stretch')

    st.write("---")

    tab1, tab2, tab3 = st.tabs([" ✨ 新增項目", "✏️ 修改/刪除項目", "🚀 批次匯入 (Excel)"])

    with tab1:
        with st.form("add_item_form"):
            st.markdown("##### 新增薪資項目")
            name = st.text_input("項目名稱*")
            type_options = {'earning': '給付 (Earning)', 'deduction': '扣除 (Deduction)'}
            type = st.selectbox("項目類型*", options=list(type_options.keys()), format_func=lambda x: type_options[x])
            is_active = st.checkbox("啟用此項目", value=True)

            if st.form_submit_button("確認新增", type="primary"):
                if not name.strip():
                    st.error("「項目名稱」為必填欄位！")
                else:
                    new_data = {'name': name.strip(), 'type': type, 'is_active': is_active}
                    try:
                        q_items.add_salary_item(conn, new_data)
                        st.success(f"✅ 成功新增項目：{name}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"❌ 操作失敗：項目名稱「{name.strip()}」可能已存在。")
                    except Exception as e:
                        st.error(f"❌ 操作失敗：{e}")

    with tab2:
        if not items_df_raw.empty:
            item_list = {f"{row['name']} (ID: {row['id']})": row['id'] for _, row in items_df_raw.iterrows()}
            selected_item_key = st.selectbox("選擇要操作的項目", options=list(item_list.keys()), index=None, placeholder="請選擇一個薪資項目...")

            if selected_item_key:
                item_id = item_list[selected_item_key]
                item_data = items_df_raw[items_df_raw['id'] == item_id].iloc[0].to_dict()

                with st.form(f"edit_item_form_{item_id}"):
                    st.markdown(f"##### 正在編輯: {item_data['name']}")
                    name_edit = st.text_input("項目名稱*", value=item_data.get('name', ''))
                    type_options = {'earning': '給付 (Earning)', 'deduction': '扣除 (Deduction)'}
                    type_index = list(type_options.keys()).index(item_data.get('type', 'earning'))
                    type_edit = st.selectbox("項目類型*", options=list(type_options.keys()), format_func=lambda x: type_options[x], index=type_index)
                    is_active_edit = st.checkbox("啟用此項目", value=bool(item_data.get('is_active', True)))
                    
                    c1, c2 = st.columns(2)
                    
                    if c1.form_submit_button("儲存變更", width='stretch'):
                        if not name_edit.strip():
                            st.error("「項目名稱」為必填欄位！")
                        else:
                            update_data = {
                                'name': name_edit.strip(),
                                'type': type_edit,
                                'is_active': is_active_edit
                            }
                            try:
                                q_items.update_salary_item(conn, item_id, update_data)
                                st.success(f"✅ 成功更新項目：{name_edit}")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error(f"❌ 操作失敗：項目名稱「{name_edit.strip()}」可能已存在。")
                            except Exception as e:
                                st.error(f"❌ 操作失敗：{e}")
                    
                    if c2.form_submit_button("🔴 刪除此項目", type="primary", width='stretch'):
                        try:
                            q_items.delete_salary_item(conn, item_id)
                            st.success(f"✅ 已成功刪除項目：{item_data['name']}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ 刪除失敗：{e}")
        else:
            st.info("目前沒有可操作的項目。")

    with tab3:
        create_batch_import_section(
            info_text="說明：系統會以「項目名稱」為唯一鍵，若紀錄已存在則會更新，否則新增。",
            template_columns={
                'name': '項目名稱*', 'type': '類型*(earning/deduction)', 'is_active': '是否啟用*(1/0)'
            },
            template_file_name="salary_items_template.xlsx",
            import_logic_func=logic_items.batch_import_salary_items,
            conn=conn
        )