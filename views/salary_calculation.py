# pages/salary_calculation.py
import streamlit as st
import pandas as pd
from datetime import datetime
import traceback

# 導入所有需要的、已拆分的模組
from services import salary_logic as logic_salary
from db import queries_salary_records as q_records
from db import queries_employee as q_emp

def show_page(conn):
    st.header("💵 薪資單產生與管理")
    
    c1, c2 = st.columns(2)
    today = datetime.now()
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 1, value=today.year)
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=today.month)

    st.write("---")
    
    action_c1, action_c2 = st.columns(2)

    with action_c1:
        if st.button("🚀 產生/覆蓋薪資草稿", help="此操作會根據最新的出勤、假單等資料重新計算，並覆蓋現有草稿。"):
            with st.spinner("正在根據最新資料計算全新草稿..."):
                try:
                    # 呼叫 services 層的函式進行計算
                    new_draft_df, _ = logic_salary.calculate_salary_df(conn, year, month)
                    if not new_draft_df.empty:
                        # 將計算結果存入資料庫
                        q_records.save_salary_draft(conn, year, month, new_draft_df)
                        st.success("新草稿已計算並儲存！請點擊右側按鈕讀取以查看。")
                        # 清除 session state 中的舊資料，以便下次能正確讀取
                        if 'salary_report_df' in st.session_state:
                             del st.session_state['salary_report_df']
                        st.rerun()
                    else:
                        st.warning("當月沒有在職員工，無法產生草稿。")
                except Exception as e:
                    st.error("產生草稿時發生錯誤！")
                    st.code(traceback.format_exc())


    with action_c2:
        if st.button("🔄 讀取已儲存的薪資資料", type="primary"):
            with st.spinner("正在從資料庫讀取薪資報表..."):
                report_df, item_types = q_records.get_salary_report_for_editing(conn, year, month)
                st.session_state.salary_report_df = report_df
                st.session_state.salary_item_types = item_types
                if report_df.empty:
                    st.info("資料庫中沒有本月的薪資紀錄，您可以點擊左側按鈕產生新草稿。")
                st.rerun()

    # 檢查 session state 中是否有報表資料，若無則提示使用者操作
    if 'salary_report_df' not in st.session_state or st.session_state.salary_report_df.empty:
        st.info("請點擊「產生/覆蓋薪資草稿」來開始，或點擊「讀取已儲存的薪資資料」。")
        return

    st.write("---")
    
    df_to_edit = st.session_state.salary_report_df
    
    st.markdown("##### 薪資單編輯區")
    st.caption("您可以直接在表格中修改 `draft` 狀態的紀錄。`final` 狀態的紀錄已鎖定。")
    
    # 使用 data_editor 讓使用者可以直接在網頁上編輯表格
    edited_df = st.data_editor(
        df_to_edit.style.apply(lambda row: ['background-color: #f0f2f6'] * len(row) if row.status == 'final' else [''] * len(row), axis=1),
        use_container_width=True,
        key="salary_editor"
    )
    
    # --- 批次上傳功能 ---
    with st.expander("🚀 批次上傳津貼/費用 (Excel)"):
        st.info("上傳的 Excel 中，第一欄必須是 '員工姓名'，其餘欄位的名稱必須與「薪資項目管理」中的項目名稱完全一致。")
        uploaded_file = st.file_uploader(
            "選擇 Excel 檔", 
            type="xlsx", 
            key=f"uploader_{year}_{month}"
        )
        if uploaded_file:
            with st.spinner("正在處理 Excel 檔案..."):
                try:
                    report = logic_salary.process_batch_salary_update_excel(conn, year, month, uploaded_file)
                    st.success(f"批次更新完成！成功更新/新增了 {report['success']} 筆薪資明細。")
                    if report["skipped_emp"]: st.warning(f"找不到對應員工，已跳過：{', '.join(report['skipped_emp'])}")
                    if report["skipped_item"]: st.warning(f"找不到對應薪資項目，已跳過：{', '.join(report['skipped_item'])}")
                    if report["no_salary_record"]: st.error(f"下列員工在本月尚無薪資主紀錄，請先為他們產生草稿：{', '.join(report['no_salary_record'])}")
                    # 清除 session state 並重新整理頁面以顯示最新資料
                    if 'salary_report_df' in st.session_state:
                         del st.session_state['salary_report_df']
                    st.rerun()
                except Exception as e:
                    st.error(f"處理 Excel 時發生錯誤: {e}")

    st.write("---")
    
    btn_c1, btn_c2 = st.columns(2)

    with btn_c1:
        draft_to_save = edited_df[edited_df['status'] == 'draft']
        if st.button("💾 儲存草稿變更", disabled=draft_to_save.empty):
            with st.spinner("正在儲存草稿..."):
                q_records.save_salary_draft(conn, year, month, draft_to_save)
                st.success("草稿已成功儲存！")
                st.rerun()

    with btn_c2:
        draft_to_finalize = edited_df[edited_df['status'] == 'draft']
        if st.button("🔒 儲存並鎖定最終版本", type="primary", disabled=draft_to_finalize.empty):
            with st.spinner("正在寫入並鎖定最終薪資單..."):
                q_records.finalize_salary_records(conn, year, month, draft_to_finalize)
                st.success(f"{year}年{month}月的薪資單已成功定版！")
                st.rerun()

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
                    count = q_records.revert_salary_to_draft(conn, year, month, ids_to_unlock)
                    st.success(f"成功解鎖 {count} 筆紀錄！請重新讀取資料。")
                    if 'salary_report_df' in st.session_state:
                         del st.session_state['salary_report_df']
                    st.rerun()
        else:
            st.info("目前沒有已定版的紀錄可供解鎖。")