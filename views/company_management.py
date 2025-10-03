# views/company_management.py
import streamlit as st
import pandas as pd
from db import queries_common as q_common
from utils.ui_components import create_batch_import_section
from services import company_logic as logic_comp

COLUMN_MAP = {
    'name': '公司名稱', 'uniform_no': '統一編號',
    'debit_account': '薪轉帳號',
    'enterprise_id': '企業編號(4碼)',
    'address': '地址',
    'owner': '負責人', 'ins_code': '投保代號', 'note': '備註'
}
COMPANY_TEMPLATE_COLUMNS = {
    'name': '公司名稱*', 'uniform_no': '統一編號*',
    'debit_account': '薪轉帳號',
    'enterprise_id': '企業編號(4碼)',
    'address': '地址',
    'owner': '負責人', 'ins_code': '投保代號', 'note': '備註'
}

def show_page(conn):
    st.header("🏢 公司管理")
    st.info("管理系統中所有作為加保單位的公司資料。")

    try:
        df_raw = q_common.get_all(conn, 'company', order_by='name')
        df_display = df_raw.copy()
        df_display.set_index('id', inplace=True)
        
        st.subheader("公司資料總覽")
        st.caption("您可以直接在下表中快速修改資料，完成後點擊表格下方的「儲存變更」按鈕。")

        if 'original_company_df' not in st.session_state:
            st.session_state.original_company_df = df_display.copy()

        edited_df = st.data_editor(
            df_display.rename(columns=COLUMN_MAP),
            width='stretch',
            disabled=["統一編號"]
        )
        
        if st.button("💾 儲存表格變更", type="primary"):
            original_df_renamed = st.session_state.original_company_df.rename(columns=COLUMN_MAP)
            changes = edited_df.compare(original_df_renamed)
            
            if changes.empty:
                st.info("沒有偵測到任何變更。")
            else:
                updates_count = 0
                with st.spinner("正在儲存變更..."):
                    edited_df_reverted = edited_df.rename(columns={v: k for k, v in COLUMN_MAP.items()})
                    for record_id, row in edited_df_reverted.iterrows():
                        original_row = st.session_state.original_company_df.loc[record_id]
                        if not row.equals(original_row):
                            q_common.update_record(conn, 'company', record_id, row.to_dict())
                            updates_count += 1
                st.success(f"成功更新了 {updates_count} 筆公司資料！")
                del st.session_state.original_company_df
                st.rerun()

    except Exception as e:
        st.error(f"讀取公司資料時發生錯誤: {e}")
        df_raw = pd.DataFrame() # 確保發生錯誤時 df_raw 存在

    st.subheader("資料操作")
    tab1, tab2, tab3 = st.tabs([" ✨ 新增公司", "✏️ 修改/刪除公司", "🚀 批次匯入 (Excel)"])

    with tab1:
        with st.form("add_company_form", clear_on_submit=True):
            st.markdown("##### 請填寫新公司資料 (*為必填)")
            c1, c2 = st.columns(2)
            new_data = {
                'name': c1.text_input("公司名稱*"),
                'uniform_no': c2.text_input("統一編號"),
                'debit_account': c1.text_input("薪轉帳號 (12碼，不含'-')"),
                'enterprise_id': c2.text_input("企業編號 (銀行用，4碼)", max_chars=4),
                'owner': c1.text_input("負責人"),
                'ins_code': c2.text_input("投保代號"),
                'address': st.text_input("地址"),
                'note': st.text_area("備註")
            }
            if st.form_submit_button("確認新增"):
                if not new_data['name']:
                    st.error("公司名稱為必填欄位！")
                else:
                    try:
                        cleaned_data = {k: (v if v else None) for k, v in new_data.items()}
                        q_common.add_record(conn, 'company', cleaned_data)
                        st.success(f"成功新增公司：{new_data['name']}")
                        if 'original_company_df' in st.session_state:
                            del st.session_state.original_company_df
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增公司時發生錯誤：{e}")

    with tab2:
        st.markdown("##### 單筆修改或刪除")
        if not df_raw.empty:
            company_options = {f"{row['name']} ({row['uniform_no'] or 'N/A'})": row['id'] for _, row in df_raw.iterrows()}
            selected_key = st.selectbox(
                "從總覽列表選擇要操作的公司", 
                options=company_options.keys(),
                index=None,
                placeholder="請選擇..."
            )
            if selected_key:
                company_id = company_options[selected_key]
                record_data = q_common.get_by_id(conn, 'company', company_id)

                with st.form(f"edit_company_form_{company_id}"):
                    st.write(f"**正在編輯**: {record_data['name']}")
                    c1, c2 = st.columns(2)
                    updated_data = {
                        'name': c1.text_input("公司名稱*", value=record_data.get('name', '')),
                        'uniform_no': c2.text_input("統一編號", value=record_data.get('uniform_no', ''), disabled=True),
                        'debit_account': c1.text_input("薪轉帳號", value=record_data.get('debit_account', '') or ''),
                        'enterprise_id': c2.text_input("企業編號 (4碼)", value=record_data.get('enterprise_id', '') or '', max_chars=4),
                        'owner': c1.text_input("負責人", value=record_data.get('owner', '') or ''),
                        'ins_code': c2.text_input("投保代號", value=record_data.get('ins_code', '') or ''),
                        'address': st.text_input("地址", value=record_data.get('address', '') or ''),
                        'note': st.text_area("備註", value=record_data.get('note', '') or '')
                    }
                    
                    col_update, col_delete = st.columns(2)
                    if col_update.form_submit_button("儲存變更", width='stretch'):
                        q_common.update_record(conn, 'company', company_id, updated_data)
                        st.success("公司資料已更新！")
                        if 'original_company_df' in st.session_state:
                            del st.session_state.original_company_df
                        st.rerun()
                    
                    if col_delete.form_submit_button("🔴 刪除此公司", type="primary", width='stretch'):
                        try:
                            q_common.delete_record(conn, 'company', company_id)
                            st.warning(f"公司 '{record_data['name']}' 已被刪除！")
                            if 'original_company_df' in st.session_state:
                                del st.session_state.original_company_df
                            st.rerun()
                        except Exception as e:
                            st.error(f"刪除失敗：該公司可能已被員工加保紀錄引用。")

        else:
            st.info("目前沒有可供修改或刪除的紀錄。")


    with tab3:
        create_batch_import_section(
            info_text="說明：請下載範本，填寫公司資料後上傳。系統會以「統一編號」為唯一鍵進行新增或更新。",
            template_columns=COMPANY_TEMPLATE_COLUMNS,
            template_file_name="company_template.xlsx",
            import_logic_func=logic_comp.batch_import_companies,
            conn=conn
        )