# pages/company_management.py
import streamlit as st
import pandas as pd
from db import queries_common as q_common
from utils.ui_components import create_batch_import_section
from services import company_logic as logic_comp

COLUMN_MAP = {
    'name': '公司名稱', 'uniform_no': '統一編號', 'address': '地址',
    'owner': '負責人', 'ins_code': '投保代號', 'note': '備註'
}
COMPANY_TEMPLATE_COLUMNS = {
    'name': '公司名稱*', 'uniform_no': '統一編號*', 'address': '地址',
    'owner': '負責人', 'ins_code': '投保代號', 'note': '備註'
}

def show_page(conn):
    st.header("🏢 公司管理")
    st.info("管理系統中所有作為加保單位的公司資料。")

    try:
        df_raw = q_common.get_all(conn, 'company', order_by='name')
        st.dataframe(df_raw.rename(columns=COLUMN_MAP))
    except Exception as e:
        st.error(f"讀取公司資料時發生錯誤: {e}")
        return

    st.subheader("資料操作")
    tab1, tab2, tab3 = st.tabs(["新增公司", "修改/刪除公司", "🚀 批次匯入 (Excel)"])

    with tab1:
        with st.form("add_company_form", clear_on_submit=True):
            st.write("請填寫新公司資料 (*為必填)")
            c1, c2 = st.columns(2)
            new_data = {
                'name': c1.text_input("公司名稱*"), 'uniform_no': c2.text_input("統一編號"),
                'owner': c1.text_input("負責人"), 'ins_code': c2.text_input("投保代號"),
                'address': st.text_input("地址"), 'note': st.text_area("備註")
            }
            if st.form_submit_button("確認新增"):
                if not new_data['name']:
                    st.error("公司名稱為必填欄位！")
                else:
                    try:
                        cleaned_data = {k: (v if v else None) for k, v in new_data.items()}
                        q_common.add_record(conn, 'company', cleaned_data)
                        st.success(f"成功新增公司：{new_data['name']}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增公司時發生錯誤：{e}")
    
    with tab2:
        if not df_raw.empty:
            options = {f"{row['name']} ({row['uniform_no']})": row['id'] for _, row in df_raw.iterrows()}
            selected_key = st.selectbox("選擇要操作的公司", options.keys(), index=None, placeholder="請選擇一間公司...")
            
            if selected_key:
                selected_id = options[selected_key]
                comp_data = q_common.get_by_id(conn, 'company', selected_id)

                with st.form(f"update_company_{selected_id}"):
                    st.write(f"### 正在編輯: {comp_data['name']}")
                    c1, c2 = st.columns(2)
                    updated_data = {
                        'name': c1.text_input("公司名稱*", value=comp_data.get('name', '')),
                        'uniform_no': c2.text_input("統一編號", value=comp_data.get('uniform_no', '') or ''),
                        'owner': c1.text_input("負責人", value=comp_data.get('owner', '') or ''),
                        'ins_code': c2.text_input("投保代號", value=comp_data.get('ins_code', '') or ''),
                        'address': st.text_input("地址", value=comp_data.get('address', '') or ''),
                        'note': st.text_area("備註", value=comp_data.get('note', '') or '')
                    }
                    
                    c_update, c_delete = st.columns(2)
                    if c_update.form_submit_button("儲存變更", use_container_width=True):
                        if not updated_data['name']:
                            st.error("公司名稱為必填欄位！")
                        else:
                            try:
                                cleaned_data = {k: (v if v else None) for k, v in updated_data.items()}
                                q_common.update_record(conn, 'company', selected_id, cleaned_data)
                                st.success(f"成功更新公司 {updated_data['name']} 的資料！")
                                st.rerun()
                            except Exception as e:
                                st.error(f"更新時發生錯誤：{e}")

                    if c_delete.form_submit_button("🔴 刪除此公司", use_container_width=True, type="primary"):
                        try:
                            q_common.delete_record(conn, 'company', selected_id)
                            st.success(f"已成功刪除公司 {comp_data['name']}。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"刪除失敗：{e} (該公司可能仍有關聯的員工加保紀錄)")
    with tab3:
        # 【新增】直接呼叫通用元件
        create_batch_import_section(
            info_text="說明：請下載範本，填寫公司資料後上傳。系統會以「統一編號」為唯一鍵進行新增或更新。",
            template_columns=COMPANY_TEMPLATE_COLUMNS,
            template_file_name="company_template.xlsx",
            import_logic_func=logic_comp.batch_import_companies,
            conn=conn
        )
