# pages/employee_management.py
import streamlit as st
import pandas as pd
import sqlite3
# 修正 import
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
    'nhi_status': '健保狀態', 'nhi_status_expiry': '狀態效期' # 新增
}

TEMPLATE_COLUMNS = {
    'name_ch': '姓名*', 'id_no': '身分證號*', 'hr_code': '員工編號*', 'entry_date': '到職日(YYYY-MM-DD)',
    'gender': '性別(男/女)', 'birth_date': '生日(YYYY-MM-DD)', 'nationality': '國籍(台灣/泰國...)',
    'arrival_date': '首次抵台日(YYYY-MM-DD)', 'phone': '電話', 'address': '地址', 'dept': '部門',
    'title': '職稱', 'resign_date': '離職日(YYYY-MM-DD)', 'bank_account': '銀行帳號', 'note': '備註'
}

def show_page(conn):
    st.header("👤 員工管理")

    try:
        df_raw = q_emp.get_all_employees(conn)
        df_display = df_raw.copy()
        if 'nationality' in df_display.columns:
            df_display['nationality'] = df_display['nationality'].map(NATIONALITY_MAP_REVERSE).fillna(df_display['nationality'])
        
        st.dataframe(df_display.rename(columns=COLUMN_MAP), use_container_width=True)
    except Exception as e:
        st.error(f"讀取員工資料時發生錯誤: {e}")
        return

    st.subheader("資料操作")
    tab1, tab2, tab3 = st.tabs(["新增員工", "修改或刪除員工", "🚀 批次匯入 (Excel)"])

    with tab1:
        with st.form("add_employee_form", clear_on_submit=True):
            st.write("請填寫新員工資料 (*為必填)")
            
            # --- 基本資料 ---
            c1, c2, c3 = st.columns(3)
            name_ch = c1.text_input("姓名*")
            hr_code = c2.text_input("員工編號*")
            id_no = c3.text_input("身分證號*")
            
            # --- 職務資料 ---
            c4, c5, c6 = st.columns(3)
            dept = c4.text_input("部門")
            title = c5.text_input("職稱")
            gender = c6.selectbox("性別", ["", "男", "女"])
            
            # --- 個人與日期資料 ---
            c7, c8, c9 = st.columns(3)
            nationality_ch = c7.selectbox("國籍", list(NATIONALITY_MAP.keys()))
            birth_date = c8.date_input("生日", value=None)
            entry_date = c9.date_input("到職日", value=None)
            
            # --- 聯絡資訊 ---
            c10, c11 = st.columns(2)
            phone = c10.text_input("電話")
            bank_account = c11.text_input("銀行帳號")
            address = st.text_input("地址")
            
            # --- 特殊身份與日期 ---
            st.markdown("---")
            st.markdown("##### 特殊身份與日期")
            c12, c13, c14 = st.columns(3)
            arrival_date = c12.date_input("首次抵台日期 (外籍適用)", value=None)
            resign_date = c13.date_input("離職日", value=None)
            
            # --- 健保相關 ---
            st.markdown("---")
            st.markdown("##### 健保相關設定")
            c15, c16 = st.columns(2)
            nhi_status = c15.selectbox("健保狀態", ["一般", "低收入戶", "自理"])
            nhi_status_expiry = c16.date_input("狀態效期", value=None)

            note = st.text_area("備註")

            # --- 表單提交按鈕 ---
            if st.form_submit_button("確認新增"):
                if not all([name_ch, hr_code, id_no]):
                    st.error("姓名、員工編號、身分證號為必填欄位！")
                else:
                    new_data = {
                        'name_ch': name_ch, 'hr_code': hr_code, 'id_no': id_no,
                        'dept': dept, 'title': title, 'gender': gender,
                        'nationality': NATIONALITY_MAP[nationality_ch],
                        'birth_date': birth_date, 'entry_date': entry_date,
                        'phone': phone, 'bank_account': bank_account, 'address': address,
                        'arrival_date': arrival_date, 'resign_date': resign_date,
                        'nhi_status': nhi_status, 'nhi_status_expiry': nhi_status_expiry,
                        'note': note
                    }
                    try:
                        # 清理空值，確保資料庫儲存的是 NULL 而不是空字串
                        cleaned_data = {k: (v if v else None) for k, v in new_data.items()}
                        q_common.add_record(conn, 'employee', cleaned_data)
                        st.success(f"成功新增員工：{new_data['name_ch']}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("新增失敗：員工編號或身分證號可能已存在。")
                    except Exception as e:
                        st.error(f"發生未知錯誤：{e}")

    with tab2:
        if not df_raw.empty:
            options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in df_raw.iterrows()}
            selected_key = st.selectbox("選擇要操作的員工", options.keys(), index=None, placeholder="請選擇一位員工...")

            if selected_key:
                selected_id = options[selected_key]
                emp_data = df_raw[df_raw['id'] == selected_id].iloc[0].to_dict()

                with st.form(f"update_employee_{selected_id}"):
                    st.write(f"### 正在編輯: {emp_data['name_ch']}")
                    c1, c2, c3 = st.columns(3)

                    # [核心修改] 使用 'or' 語句來處理空字串的情況
                    current_nationality_code = emp_data.get('nationality') or 'TW'
                    
                    updated_data = {
                        'name_ch': c1.text_input("姓名*", value=emp_data.get('name_ch', '')),
                        'hr_code': c2.text_input("員工編號*", value=emp_data.get('hr_code', '')),
                        'id_no': c3.text_input("身分證號*", value=emp_data.get('id_no', '')),
                        'dept': c1.text_input("部門", value=emp_data.get('dept', '') or ''),
                        'title': c2.text_input("職稱", value=emp_data.get('title', '') or ''),
                        'gender': c3.selectbox("性別", ["男", "女"], index=["男", "女"].index(emp_data['gender']) if emp_data.get('gender') in ["男", "女"] else 0),
                        'nationality': NATIONALITY_MAP[c1.selectbox("國籍", list(NATIONALITY_MAP.keys()), index=list(NATIONALITY_MAP_REVERSE.keys()).index(current_nationality_code))],
                        'arrival_date': c2.date_input("首次抵台日期", value=to_date(emp_data.get('arrival_date'))),
                        'entry_date': c3.date_input("到職日", value=to_date(emp_data.get('entry_date'))),
                        'birth_date': c1.date_input("生日", value=to_date(emp_data.get('birth_date'))),
                        'resign_date': c2.date_input("離職日", value=to_date(emp_data.get('resign_date'))),
                        'phone': c3.text_input("電話", value=emp_data.get('phone', '') or ''),
                        'address': st.text_input("地址", value=emp_data.get('address', '') or ''),
                        'bank_account': st.text_input("銀行帳號", value=emp_data.get('bank_account', '') or ''),
                        'note': st.text_area("備註", value=emp_data.get('note', '') or ''),
                        'nhi_status': c1.selectbox("健保狀態", ["一般", "低收入戶", "自理"], index=["一般", "低收入戶", "自理"].index(emp_data.get('nhi_status', '一般'))),
                        'nhi_status_expiry': c2.date_input("狀態效期", value=to_date(emp_data.get('nhi_status_expiry')))
                    }

                    c_update, c_delete = st.columns(2)
                    if c_update.form_submit_button("儲存變更", use_container_width=True):
                        if not all([updated_data['name_ch'], updated_data['hr_code'], updated_data['id_no']]):
                            st.error("姓名、員工編號、身分證號為必填欄位！")
                        else:
                            try:
                                cleaned_data = {k: (v if v else None) for k, v in updated_data.items()}
                                q_common.update_record(conn, 'employee', selected_id, cleaned_data)
                                st.success(f"成功更新員工 {updated_data['name_ch']} 的資料！")
                                st.rerun()
                            except Exception as e:
                                st.error(f"更新時發生錯誤：{e}")

                    if c_delete.form_submit_button("🔴 刪除此員工", use_container_width=True, type="primary"):
                        try:
                            q_common.delete_record(conn, 'employee', selected_id)
                            st.success(f"已成功刪除員工 {emp_data['name_ch']}。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"刪除失敗：{e} (該員工可能仍有關聯的出勤或薪資紀錄)")

    with tab3:
        create_batch_import_section(
            info_text="說明：請先下載範本檔案，依照格式填寫員工資料後，再將檔案上傳。系統會以「身分證號」為唯一鍵進行新增或更新。",
            template_columns=TEMPLATE_COLUMNS,
            template_file_name="employee_template.xlsx",
            import_logic_func=logic_emp.batch_import_employees,
            conn=conn
        )