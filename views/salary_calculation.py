# views/salary_calculation.py
import streamlit as st
import pandas as pd
from datetime import datetime
import traceback
from dateutil.relativedelta import relativedelta
import time

from services import salary_logic as logic_salary
from db import queries_salary_read as q_read
from db import queries_salary_write as q_write
from db import queries_employee as q_emp
from db import queries_salary_items as q_items

def show_page(conn):
    st.header("💵 薪資單產生與管理")

    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 1, value=last_month.year)
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month)

    st.write("---")

    # 在 session_state 中初始化，避免每次都重新讀取
    session_key = f"salary_report_{year}_{month}"
    if session_key not in st.session_state:
        st.session_state[session_key] = {'df': pd.DataFrame(), 'types': {}}

    final_records_exist = q_read.check_if_final_records_exist(conn, year, month)

    action_c1, action_c2 = st.columns(2)

    with action_c1:
        if st.button("🚀 產生/覆蓋薪資草稿", help="此操作會根據最新的出勤、假單等資料重新計算，並覆蓋現有草稿。", disabled=final_records_exist):
            with st.spinner("正在根據最新資料計算全新草稿..."):
                try:
                    new_draft_df, item_types = logic_salary.calculate_salary_df(conn, year, month)
                    if not new_draft_df.empty:
                        q_write.save_salary_draft(conn, year, month, new_draft_df)
                        # 直接將新產生的資料存入 session state
                        st.session_state[session_key] = {'df': new_draft_df, 'types': item_types}
                        st.success("新草稿已計算並儲存！表格已更新。")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.warning("當月沒有在職員工，無法產生草稿。")
                except Exception as e:
                    st.error("產生草稿時發生錯誤！")
                    st.code(traceback.format_exc())

    if final_records_exist:
        st.warning(f"🔒 {year}年{month}月的薪資單已定版。如需重新計算，請先至下方的「進階操作」區塊解鎖相關人員。")

    with action_c2:
        if st.button("🔄 讀取已儲存的薪資資料", type="primary"):
            with st.spinner("正在從資料庫讀取薪資報表..."):
                report_df, item_types = q_read.get_salary_report_for_editing(conn, year, month)
                st.session_state[session_key] = {'df': report_df, 'types': item_types}
                if report_df.empty:
                    st.info("資料庫中沒有本月的薪資紀錄，您可以點擊左側按鈕產生新草稿。")
                st.rerun()

    # 從 session state 讀取資料
    df_to_edit = st.session_state[session_key]['df']

    if df_to_edit.empty:
        st.info("請點擊「產生/覆蓋薪資草稿」來開始，或點擊「讀取已儲存的薪資資料」。")
        return

    st.write("---")

    st.markdown("##### 薪資單編輯區")
    st.caption("您可以直接在表格中修改 `draft` 狀態的紀錄。`final` 狀態的紀錄已鎖定。")

    edited_df = st.data_editor(
        df_to_edit.style.apply(lambda row: ['background-color: #f0f2f6'] * len(row) if row.status == 'final' else [''] * len(row), axis=1),
        use_container_width=True,
        key=f"salary_editor_{year}_{month}" # 使用年月作為 key，確保切換月份時編輯器會刷新
    )

    # --- 主要按鈕區 ---
    btn_c1, btn_c2 = st.columns(2)

    with btn_c1:
        # 【核心修改】重新加回 data_editor 的儲存按鈕
        if st.button("💾 儲存表格中的變更", help="儲存您在上方表格中對『草稿』狀態紀錄的所有修改。"):
            draft_to_save = edited_df[edited_df['status'] == 'draft']
            if not draft_to_save.empty:
                with st.spinner("正在儲存草稿..."):
                    q_write.save_salary_draft(conn, year, month, draft_to_save)
                    # 重新讀取以確保資料同步
                    report_df, item_types = q_read.get_salary_report_for_editing(conn, year, month)
                    st.session_state[session_key] = {'df': report_df, 'types': item_types}
                    st.success("草稿已成功儲存！")
                    time.sleep(0.5)
                    st.rerun()
            else:
                st.info("沒有狀態為『草稿』的紀錄可供儲存。")


    with btn_c2:
        draft_to_finalize = edited_df[edited_df['status'] == 'draft']
        if st.button("🔒 儲存並鎖定最終版本", type="primary", disabled=draft_to_finalize.empty):
            with st.spinner("正在寫入並鎖定最終薪資單..."):
                q_write.finalize_salary_records(conn, year, month, draft_to_finalize)
                # 清除舊的 session state
                if session_key in st.session_state:
                    del st.session_state[session_key]
                st.success(f"{year}年{month}月的薪資單已成功定版！")
                st.rerun()

    # --- 單筆調整區塊 ---
    with st.expander("✏️ 單筆手動調整 (會直接影響草稿)"):
        # 邏輯與之前相同，但確保最後會刷新 session state
        all_employees = q_emp.get_all_employees(conn)
        all_items_df = q_items.get_all_salary_items(conn, active_only=True)
        draft_emp_names = edited_df[edited_df['status'] == 'draft']['員工姓名'].unique()
        employees_in_draft = all_employees[all_employees['name_ch'].isin(draft_emp_names)]

        if not employees_in_draft.empty:
            emp_options = dict(zip(employees_in_draft['name_ch'], employees_in_draft['id']))
            item_options = dict(zip(all_items_df['name'], all_items_df['id']))
            item_types_map = dict(zip(all_items_df['name'], all_items_df['type']))

            with st.form("single_item_adjustment_form"):
                c1, c2, c3 = st.columns(3)
                selected_emp_name = c1.selectbox("選擇員工*", options=list(emp_options.keys()), index=None)
                selected_item_name = c2.selectbox("選擇薪資項目*", options=list(item_options.keys()), index=None)
                amount = c3.number_input("輸入金額*", step=1.0, value=0.0)

                if st.form_submit_button("確認調整"):
                    if not (selected_emp_name and selected_item_name):
                        st.warning("請務必選擇員工和薪資項目。")
                    else:
                        with st.spinner("正在儲存調整並刷新資料..."):
                            try:
                                emp_id = emp_options[selected_emp_name]
                                item_id = item_options[selected_item_name]
                                salary_id_result = conn.execute("SELECT id FROM salary WHERE employee_id = ? AND year = ? AND month = ? AND status = 'draft'", (emp_id, year, month)).fetchone()

                                if not salary_id_result:
                                    st.error(f"錯誤：找不到 {selected_emp_name} 的薪資草稿紀錄。")
                                else:
                                    salary_id = salary_id_result[0]
                                    q_write.batch_upsert_salary_details(conn, [(salary_id, item_id, int(amount))])
                                    
                                    # 重新讀取並覆蓋 session state
                                    report_df, item_types = q_read.get_salary_report_for_editing(conn, year, month)
                                    st.session_state[session_key] = {'df': report_df, 'types': item_types}
                                    
                                    st.success(f"成功調整！總覽表格已刷新。")
                                    time.sleep(0.5)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"調整時發生錯誤: {e}")
                                st.code(traceback.format_exc())
        else:
            st.info("目前沒有狀態為「草稿」的紀錄可供單筆調整。")


    # --- 解鎖區塊 ---
    with st.expander("⚠️ 進階操作 (解鎖)"):
        final_records = edited_df[edited_df['status'] == 'final']
        if not final_records.empty:
            emp_map_df = q_emp.get_all_employees(conn)
            emp_map = emp_map_df.set_index('name_ch')['id'].to_dict()
            final_records['id'] = final_records['員工姓名'].map(emp_map)
            
            options = final_records['員工姓名'].tolist()
            to_unlock = st.multiselect("選擇要解鎖的員工紀錄", options=options)
            
            if st.button("解鎖選定員工紀錄"):
                if not to_unlock:
                    st.warning("請至少選擇一位要解鎖的員工。")
                else:
                    ids_to_unlock = final_records[final_records['員工姓名'].isin(to_unlock)]['id'].tolist()
                    count = q_write.revert_salary_to_draft(conn, year, month, ids_to_unlock)
                    if session_key in st.session_state:
                         del st.session_state[session_key]
                    st.success(f"成功解鎖 {count} 筆紀錄！請重新讀取資料。")
                    st.rerun()
        else:
            st.info("目前沒有已定版的紀錄可供解鎖。")