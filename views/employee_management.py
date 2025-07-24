# pages/employee_management.py
import streamlit as st
import pandas as pd
import sqlite3
# 修正 import
from db import queries_employee as q_emp
from db import queries_common as q_common
from utils.helpers import to_date

NATIONALITY_MAP = {'台灣': 'TW', '泰國': 'TH', '印尼': 'ID', '越南': 'VN', '菲律賓': 'PH'}
NATIONALITY_MAP_REVERSE = {v: k for k, v in NATIONALITY_MAP.items()}

COLUMN_MAP = {
    'id': '系統ID', 'name_ch': '姓名', 'id_no': '身份證號', 'entry_date': '到職日',
    'hr_code': '員工編號', 'gender': '性別', 'birth_date': '生日', 'nationality': '國籍',
    'arrival_date': '首次抵台日', 'phone': '電話', 'address': '地址', 'dept': '部門',
    'title': '職稱', 'resign_date': '離職日', 'bank_account': '銀行帳號', 'note': '備註'
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
    mode = st.selectbox("選擇操作", ["新增員工", "修改或刪除員工"], key="emp_crud_mode")

    if mode == "新增員工":
        with st.form("add_employee_form", clear_on_submit=True):
            st.write("請填寫新員工資料 (*為必填)")
            c1, c2, c3 = st.columns(3)
            new_data = {
                'name_ch': c1.text_input("姓名*"), 'hr_code': c2.text_input("員工編號*"),
                'id_no': c3.text_input("身份證號*"), 'dept': c1.text_input("部門"),
                'title': c2.text_input("職稱"), 'gender': c3.selectbox("性別", ["", "男", "女"]),
                'nationality': NATIONALITY_MAP[c1.selectbox("國籍", list(NATIONALITY_MAP.keys()))],
                'arrival_date': c2.date_input("首次抵台日期", value=None), 'entry_date': c3.date_input("到職日", value=None),
                'birth_date': c1.date_input("生日", value=None), 'resign_date': c2.date_input("離職日", value=None),
                'phone': c3.text_input("電話"), 'address': st.text_input("地址"),
                'bank_account': st.text_input("銀行帳號"), 'note': st.text_area("備註")
            }
            
            if st.form_submit_button("確認新增"):
                if not all([new_data['name_ch'], new_data['hr_code'], new_data['id_no']]):
                    st.error("姓名、員工編號、身份證號為必填欄位！")
                else:
                    try:
                        cleaned_data = {k: (v if v else None) for k, v in new_data.items()}
                        q_common.add_record(conn, 'employee', cleaned_data)
                        st.success(f"成功新增員工：{new_data['name_ch']}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("新增失敗：員工編號或身份證號可能已存在。")
                    except Exception as e:
                        st.error(f"發生未知錯誤：{e}")

    elif mode == "修改或刪除員工":
        if not df_raw.empty:
            options = {f"{row['name_ch']} ({row['hr_code']})": row['id'] for _, row in df_raw.iterrows()}
            selected_key = st.selectbox("選擇要操作的員工", options.keys(), index=None, placeholder="請選擇一位員工...")
            
            if selected_key:
                selected_id = options[selected_key]
                emp_data = df_raw[df_raw['id'] == selected_id].iloc[0].to_dict()

                with st.form(f"update_employee_{selected_id}"):
                    st.write(f"### 正在編輯: {emp_data['name_ch']}")
                    c1, c2, c3 = st.columns(3)
                    
                    updated_data = {
                        'name_ch': c1.text_input("姓名*", value=emp_data.get('name_ch', '')),
                        'hr_code': c2.text_input("員工編號*", value=emp_data.get('hr_code', '')),
                        'id_no': c3.text_input("身份證號*", value=emp_data.get('id_no', '')),
                        'dept': c1.text_input("部門", value=emp_data.get('dept', '') or ''),
                        'title': c2.text_input("職稱", value=emp_data.get('title', '') or ''),
                        'gender': c3.selectbox("性別", ["男", "女"], index=["男", "女"].index(emp_data['gender']) if emp_data.get('gender') in ["男", "女"] else 0),
                        'nationality': NATIONALITY_MAP[c1.selectbox("國籍", list(NATIONALITY_MAP.keys()), index=list(NATIONALITY_MAP_REVERSE.keys()).index(emp_data.get('nationality', 'TW')))],
                        'arrival_date': c2.date_input("首次抵台日期", value=to_date(emp_data.get('arrival_date'))),
                        'entry_date': c3.date_input("到職日", value=to_date(emp_data.get('entry_date'))),
                        'birth_date': c1.date_input("生日", value=to_date(emp_data.get('birth_date'))),
                        'resign_date': c2.date_input("離職日", value=to_date(emp_data.get('resign_date'))),
                        'phone': c3.text_input("電話", value=emp_data.get('phone', '') or ''),
                        'address': st.text_input("地址", value=emp_data.get('address', '') or ''),
                        'bank_account': st.text_input("銀行帳號", value=emp_data.get('bank_account', '') or ''),
                        'note': st.text_area("備註", value=emp_data.get('note', '') or '')
                    }

                    c_update, c_delete = st.columns(2)
                    if c_update.form_submit_button("儲存變更", use_container_width=True):
                        if not all([updated_data['name_ch'], updated_data['hr_code'], updated_data['id_no']]):
                            st.error("姓名、員工編號、身份證號為必填欄位！")
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
