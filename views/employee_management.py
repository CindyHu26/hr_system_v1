# views/employee_management.py
import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, datetime 
from db import queries_employee as q_emp
from db import queries_common as q_common
from utils.helpers import to_date
from services import employee_logic as logic_emp
from utils.ui_components import create_batch_import_section

NATIONALITY_MAP = {'台灣': 'TW', '泰國': 'TH', '印尼': 'ID', '越南': 'VN', '菲律賓': 'PH'}
NATIONALITY_MAP_REVERSE = {v: k for k, v in NATIONALITY_MAP.items()}
COLUMN_MAP = {
    'id': '系統ID', 'name_ch': '姓名', 'id_no': '身份證號', 'entry_date': '到職日',
    'hr_code': '員工編號', 'gender': '性別', 'birth_date': '生日', 'nationality': '國籍',
    'arrival_date': '首次抵台日', 'phone': '電話', 'address': '地址', 'dept': '部門',
    'title': '職稱', 'resign_date': '離職日', 'bank_account': '銀行帳號', 'note': '備註',
    'nhi_status': '健保狀態', 'nhi_status_expiry': '狀態效期'
}
TEMPLATE_COLUMNS = {
    'name_ch': '姓名*', 'id_no': '身分證號*', 'hr_code': '員工編號*', 'entry_date': '到職日(YYYY-MM-DD)',
    'gender': '性別(男/女)', 'birth_date': '生日(YYYY-MM-DD)', 'nationality': '國籍(台灣/泰國...)',
    'arrival_date': '首次抵台日(YYYY-MM-DD)', 'phone': '電話', 'address': '地址', 'dept': '部門',
    'title': '職稱', 'resign_date': '離職日(YYYY-MM-DD)', 'bank_account': '銀行帳號', 'note': '備註',
    'nhi_status': '健保狀態(一般/低收入戶/自理)', 'nhi_status_expiry': '狀態效期(YYYY-MM-DD)'
}

def show_page(conn):
    st.header("👤 員工管理")
    
    df_raw = q_emp.get_all_employees(conn)

    tab1, tab2, tab3 = st.tabs([" 總覽與編輯", " ✨ 新增員工", "🚀 批次匯入 (Excel)"])

    with tab1:
        st.subheader("員工資料總覽")
        try:
            df_processed = df_raw.copy()
            date_cols = ['entry_date', 'birth_date', 'arrival_date', 'resign_date', 'nhi_status_expiry']
            for col in date_cols:
                df_processed[col] = pd.to_datetime(df_processed[col], errors='coerce').dt.date
            df_processed['nationality'] = df_processed['nationality'].map(NATIONALITY_MAP_REVERSE)
            df_processed.set_index('id', inplace=True)
            
            if 'original_employee_df' not in st.session_state:
                st.session_state.original_employee_df = df_processed.copy()
            
            st.info("您可以直接在下表中修改資料，完成後點擊表格下方的「儲存變更」按鈕。")
            
            edited_df = st.data_editor(
                df_processed.rename(columns=COLUMN_MAP), use_container_width=True,
                column_config={
                    "到職日": st.column_config.DateColumn("到職日", format="YYYY-MM-DD"),
                    "生日": st.column_config.DateColumn("生日", format="YYYY-MM-DD"),
                    "首次抵台日": st.column_config.DateColumn("首次抵台日", format="YYYY-MM-DD"),
                    "離職日": st.column_config.DateColumn("離職日", format="YYYY-MM-DD"),
                    "狀態效期": st.column_config.DateColumn("狀態效期", format="YYYY-MM-DD"),
                    "性別": st.column_config.SelectboxColumn("性別", options=["男", "女"]),
                    "國籍": st.column_config.SelectboxColumn("國籍", options=list(NATIONALITY_MAP.keys())),
                    "健保狀態": st.column_config.SelectboxColumn("健保狀態", options=["一般", "低收入戶", "自理"]),
                },
                disabled=["系統ID", "員工編號", "身份證號"]
            )

            if st.button("💾 儲存員工資料變更", type="primary"):
                original_df_renamed = st.session_state.original_employee_df.rename(columns=COLUMN_MAP)
                changes = edited_df.compare(original_df_renamed)
                if changes.empty:
                    st.info("沒有偵測到任何變更。")
                else:
                    updates_count = 0
                    with st.spinner("正在儲存變更..."):
                        for record_id, changed_row in changes.iterrows():
                            update_data_raw = {}
                            changed_columns = changed_row.dropna().index.get_level_values(0).unique()
                            for col_name in changed_columns:
                                new_value = changed_row.get((col_name, 'self'))
                                update_data_raw[col_name] = new_value
                            update_data_reverted = {(k for k, v in COLUMN_MAP.items() if v == col_name).__next__(): val for col_name, val in update_data_raw.items()}
                            if 'nationality' in update_data_reverted:
                                update_data_reverted['nationality'] = NATIONALITY_MAP.get(update_data_reverted['nationality'], 'TW')
                            cleaned_update_data = {}
                            for key, value in update_data_reverted.items():
                                if pd.isna(value): cleaned_update_data[key] = None
                                elif isinstance(value, (pd.Timestamp, date)): cleaned_update_data[key] = value.strftime('%Y-%m-%d')
                                else: cleaned_update_data[key] = value
                            q_common.update_record(conn, 'employee', record_id, cleaned_update_data)
                            updates_count += 1
                    st.success(f"成功更新了 {updates_count} 位員工的資料！")
                    del st.session_state.original_employee_df
                    st.rerun()
            
            st.markdown("---")
            with st.expander("🗑️ 刪除員工"):
                st.warning("注意：刪除員工將會一併刪除與其相關的所有紀錄（如薪資單、出勤等），此操作無法復原！")
                emp_options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in df_raw.iterrows()}
                selected_emp_to_delete = st.selectbox("選擇要刪除的員工", options=emp_options.keys(), index=None)
                
                if st.button("🔴 確認刪除所選員工", type="primary"):
                    if selected_emp_to_delete:
                        emp_id_to_delete = emp_options[selected_emp_to_delete]
                        try:
                            q_common.delete_record(conn, 'employee', emp_id_to_delete)
                            st.success(f"已成功刪除員工：{selected_emp_to_delete}")
                            if 'original_employee_df' in st.session_state:
                                del st.session_state.original_employee_df
                            st.rerun()
                        except Exception as e:
                            st.error(f"刪除失敗：{e}")
                    else:
                        st.warning("請先選擇一位要刪除的員工。")

        except Exception as e:
            st.error(f"讀取或處理員工資料時發生錯誤: {e}")
            return

    with tab2:
        with st.form("add_employee_form", clear_on_submit=True):
            st.write("請填寫新員工資料 (*為必填)")
            st.markdown("##### 基本資料")
            c1, c2, c3 = st.columns(3)
            name_ch = c1.text_input("姓名*")
            hr_code = c2.text_input("員工編號*")
            id_no = c3.text_input("身分證號*")
            st.markdown("##### 職務資料")
            c4, c5, c6 = st.columns(3)
            dept = c4.text_input("部門")
            title = c5.text_input("職稱")
            gender = c6.selectbox("性別", ["", "男", "女"])
            st.markdown("##### 個人與日期資料")
            c7, c8, c9 = st.columns(3)
            nationality_ch = c7.selectbox("國籍", list(NATIONALITY_MAP.keys()))
            min_date_birth = date(1950, 1, 1)
            min_date_general = date(2000, 1, 1)
            max_date = date.today().replace(year=date.today().year + 10)
            birth_date = c8.date_input("生日", value=None, min_value=min_date_birth, max_value=date.today())
            entry_date = c9.date_input("到職日", value=None, min_value=min_date_general, max_value=max_date)
            st.markdown("---")
            st.markdown("##### 聯絡資訊")
            c10, c11 = st.columns(2)
            phone = c10.text_input("電話")
            bank_account = c11.text_input("銀行帳號")
            address = st.text_input("地址")
            st.markdown("---")
            st.markdown("##### 特殊身份與日期")
            c12, c13 = st.columns(2)
            arrival_date = c12.date_input("首次抵台日期 (外籍適用)", value=None, min_value=min_date_general, max_value=max_date)
            resign_date = c13.date_input("離職日", value=None, min_value=min_date_general, max_value=max_date)
            st.markdown("---")
            st.markdown("##### 健保相關設定")
            c14, c15 = st.columns(2)
            nhi_status = c14.selectbox("健保狀態", ["一般", "低收入戶", "自理"])
            nhi_status_expiry = c15.date_input("狀態效期", value=None, min_value=min_date_general, max_value=max_date)
            note = st.text_area("備註")
            if st.form_submit_button("確認新增"):
                if not all([name_ch, hr_code, id_no]):
                    st.error("姓名、員工編號、身分證號為必填欄位！")
                else:
                    new_data = {'name_ch': name_ch, 'hr_code': hr_code, 'id_no': id_no,'dept': dept, 'title': title, 'gender': gender,'nationality': NATIONALITY_MAP[nationality_ch],'birth_date': birth_date, 'entry_date': entry_date,'phone': phone, 'bank_account': bank_account, 'address': address,'arrival_date': arrival_date, 'resign_date': resign_date,'nhi_status': nhi_status, 'nhi_status_expiry': nhi_status_expiry,'note': note}
                    try:
                        cleaned_data = {k: (v if pd.notna(v) and v != '' else None) for k, v in new_data.items()}
                        q_common.add_record(conn, 'employee', cleaned_data)
                        st.success(f"成功新增員工：{new_data['name_ch']}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("新增失敗：員工編號或身分證號可能已存在。")
                    except Exception as e:
                        st.error(f"發生未知錯誤：{e}")

    with tab3:
        create_batch_import_section(
            info_text="說明：請先下載範本檔案，依照格式填寫員工資料後，再將檔案上傳。系統會以「身分證號」為唯一鍵進行新增或更新。",
            template_columns=TEMPLATE_COLUMNS,
            template_file_name="employee_template.xlsx",
            import_logic_func=logic_emp.batch_import_employees,
            conn=conn
        )