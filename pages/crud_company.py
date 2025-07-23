import streamlit as st
import pandas as pd
import sqlite3
from utils import (
    get_all_companies,
    add_company,
    update_company,
    delete_company,
    COMPANY_COLUMNS_MAP
)

def show_page(conn):
    """
    顯示公司資料管理頁面 (CRUD) 的主函式
    """
    st.header("公司資料庫管理")

    # --- 顯示與篩選公司 ---
    st.subheader("公司列表")
    try:
        # 從 utils 取得所有公司資料，並將欄位重命名為中文
        all_comp_df_raw = get_all_companies(conn)
        all_comp_df_display = all_comp_df_raw.rename(columns=COMPANY_COLUMNS_MAP)
        st.dataframe(all_comp_df_display)
    except Exception as e:
        st.error(f"無法讀取公司資料: {e}")
        # 如果無法讀取公司資料，後續操作無意義，直接返回
        return

    st.subheader("資料操作")
    crud_option = st.selectbox("選擇操作", ["新增 (Create)", "修改 (Update) / 刪除 (Delete)"], key="company_crud_option")

    # --- 新增公司 ---
    if crud_option == "新增 (Create)":
        with st.form("add_company_form", clear_on_submit=True):
            st.write("請填寫新公司資料：")
            c1, c2 = st.columns(2)
            
            name_add = c1.text_input(COMPANY_COLUMNS_MAP['name'], key="add_comp_name")
            uniform_no_add = c2.text_input(COMPANY_COLUMNS_MAP['uniform_no'], key="add_comp_uno")
            owner_add = c1.text_input(COMPANY_COLUMNS_MAP['owner'], key="add_comp_owner")
            ins_code_add = c2.text_input(COMPANY_COLUMNS_MAP['ins_code'], key="add_comp_ins_code")
            address_add = st.text_input(COMPANY_COLUMNS_MAP['address'], key="add_comp_address")
            note_add = st.text_area(COMPANY_COLUMNS_MAP['note'], key="add_comp_note")

            submitted = st.form_submit_button("新增公司")
            if submitted:
                # 收集表單資料並淨化
                new_data = {
                    'name': name_add or None,
                    'uniform_no': uniform_no_add or None,
                    'owner': owner_add or None,
                    'ins_code': ins_code_add or None,
                    'address': address_add or None,
                    'note': note_add or None
                }
                
                if not new_data['name']:
                    st.error("公司名稱為必填欄位！")
                else:
                    try:
                        add_company(conn, new_data)
                        st.success(f"成功新增公司：{new_data['name']}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增公司時發生錯誤：{e}")

    # --- 修改/刪除公司 ---
    elif crud_option == "修改 (Update) / 刪除 (Delete)":
        st.write("請先從下方選擇一間公司進行操作：")
        if not all_comp_df_raw.empty:
            # 建立選擇列表
            options_df = all_comp_df_raw[['id', 'name', 'uniform_no']].copy()
            options_df['display'] = options_df['name'] + " (" + options_df['uniform_no'].astype(str) + ")"
            selected_display = st.selectbox("選擇公司", options=options_df['display'], key="company_select")
            
            if selected_display:
                selected_id = int(options_df[options_df['display'] == selected_display]['id'].iloc[0])
                
                # 為了獲取最新資料，這裡不從快取的 all_comp_df_raw 拿，而是重新查詢
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM company WHERE id = ?", (selected_id,))
                selected_company_tuple = cursor.fetchone()
                if selected_company_tuple:
                    # 將 tuple 轉換為 dict
                    selected_company = dict(zip([d[0] for d in cursor.description], selected_company_tuple))
                
                    st.write(f"### 正在編輯: {selected_company['name']}")
                    
                    with st.form("update_company_form"):
                        c1, c2 = st.columns(2)
                        
                        name_input = c1.text_input(COMPANY_COLUMNS_MAP['name'], value=selected_company.get('name', ''))
                        uniform_no_input = c2.text_input(COMPANY_COLUMNS_MAP['uniform_no'], value=selected_company.get('uniform_no', '') or '')
                        owner_input = c1.text_input(COMPANY_COLUMNS_MAP['owner'], value=selected_company.get('owner', '') or '')
                        ins_code_input = c2.text_input(COMPANY_COLUMNS_MAP['ins_code'], value=selected_company.get('ins_code', '') or '')
                        address_input = st.text_input(COMPANY_COLUMNS_MAP['address'], value=selected_company.get('address', '') or '')
                        note_input = st.text_area(COMPANY_COLUMNS_MAP['note'], value=selected_company.get('note', '') or '')
                        
                        update_button = st.form_submit_button("儲存變更")
                        
                        if update_button:
                            # 淨化並收集表單資料
                            updated_data = {
                                'name': name_input or None,
                                'uniform_no': uniform_no_input or None,
                                'owner': owner_input or None,
                                'ins_code': ins_code_input or None,
                                'address': address_input or None,
                                'note': note_input or None
                            }
                            
                            try:
                                update_company(conn, selected_id, updated_data)
                                st.success(f"成功更新公司 {updated_data['name']} 的資料！")
                                st.rerun()
                            except Exception as e:
                                st.error(f"更新公司時發生錯誤：{e}")

                    if st.button("🔴 刪除這間公司", key=f"delete_comp_{selected_id}"):
                        st.warning(f"您確定要永久刪除 **{selected_company['name']}** 嗎？此操作無法復原！")
                        if st.button("我確定，請刪除", key=f"confirm_delete_comp_{selected_id}"):
                            try:
                                delete_company(conn, selected_id)
                                st.success(f"已成功刪除公司 {selected_company['name']}。")
                                st.rerun()
                            except Exception as e:
                                st.error(f"刪除失敗：{e} (該公司可能仍有關聯的員工加保紀錄)")