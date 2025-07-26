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
        
        # [核心修改] 將 dataframe 改為 data_editor
        st.info("您可以直接在下表中修改資料，完成後點擊表格下方的「儲存變更」按鈕。")
        
        df_raw.set_index('id', inplace=True)
        
        if 'original_company_df' not in st.session_state:
            st.session_state.original_company_df = df_raw.copy()

        edited_df = st.data_editor(
            df_raw.rename(columns=COLUMN_MAP),
            use_container_width=True,
            disabled=["統一編號"] # 統一編號通常不變，設為不可編輯
        )
        
        if st.button("💾 儲存公司資料變更", type="primary"):
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
        return

    st.subheader("資料操作")
    tab1, tab2 = st.tabs(["新增公司", "🚀 批次匯入 (Excel)"]) # [修改] 簡化頁籤

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
        create_batch_import_section(
            info_text="說明：請下載範本，填寫公司資料後上傳。系統會以「統一編號」為唯一鍵進行新增或更新。",
            template_columns=COMPANY_TEMPLATE_COLUMNS,
            template_file_name="company_template.xlsx",
            import_logic_func=logic_comp.batch_import_companies,
            conn=conn
        )
