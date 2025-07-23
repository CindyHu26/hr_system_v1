# page_salary_calculation.py (V7 - 功能完整最終版)
import streamlit as st
import pandas as pd
from datetime import datetime
from utils_salary_calc import (
    calculate_salary_df, 
    get_salary_report_for_editing, 
    save_salary_draft, 
    finalize_salary_records, 
    revert_salary_to_draft,
    batch_update_salary_details_from_excel
)

def show_page(conn):
    st.header("💵 薪資單產生與管理")
    
    c1, c2 = st.columns(2)
    year = c1.number_input("選擇年份", min_value=2020, max_value=datetime.now().year + 1, value=datetime.now().year)
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=datetime.now().month)

    st.write("---")
    
    action_c1, action_c2 = st.columns(2)

    with action_c1:
        if st.button("🚀 產生新的薪資草稿", help="如果本月已有草稿，此操作將會覆蓋舊的草稿。"):
            with st.spinner("正在根據出勤與假單等資料計算全新草稿..."):
                new_draft_df, item_types = calculate_salary_df(conn, year, month)
                if not new_draft_df.empty:
                    st.session_state.salary_report_df = new_draft_df
                    st.session_state.salary_item_types = item_types
                    st.success("新草稿已產生！請在下方表格確認後儲存。")
                else:
                    st.warning("當月沒有在職員工，無法產生草稿。")
                st.rerun()

    with action_c2:
        if st.button("🔄 讀取已儲存的薪資資料", type="primary"):
            with st.spinner("正在讀取薪資資料..."):
                report_df, item_types = get_salary_report_for_editing(conn, year, month)
                st.session_state.salary_report_df = report_df
                st.session_state.salary_item_types = item_types
                if report_df.empty:
                    st.info("資料庫中沒有本月的薪資紀錄，您可以點擊左側按鈕產生新草稿。")
                st.rerun()

    if 'salary_report_df' not in st.session_state:
        st.info("請點擊上方按鈕開始薪資作業。")
        return

    st.write("---")
    
    df_to_edit = st.session_state.salary_report_df
    if 'status' not in df_to_edit.columns: df_to_edit['status'] = 'draft'

    st.markdown("##### 薪資單編輯區")
    st.caption("您可以直接在表格中修改 `draft` 狀態的紀錄。`final` 狀態的紀錄已鎖定。")
    
    edited_df = st.data_editor(
        df_to_edit.style.apply(lambda row: ['background-color: #f0f2f6'] * len(row) if row.status == 'final' else [''] * len(row), axis=1),
        use_container_width=True, key="salary_editor"
    )
    
    with st.expander("🚀 批次上傳津貼/費用 (Excel)"):
        uploaded_file = st.file_uploader("上傳 Excel 檔更新薪資", type="xlsx", key=f"salary_excel_uploader_{year}_{month}")
        if uploaded_file:
            with st.spinner("正在處理上傳的 Excel 檔案..."):
                report = batch_update_salary_details_from_excel(conn, year, month, uploaded_file)
                st.success("批次更新完成！")
                if report["success"]: st.write(f"成功更新 {len(report['success'])} 筆資料。")
                if report["skipped_emp"]: st.warning(f"找不到對應員工，已跳過：{', '.join(report['skipped_emp'])}")
                if report["skipped_item"]: st.warning(f"找不到對應薪資項目，已跳過：{', '.join(report['skipped_item'])}")
                st.rerun()

    st.write("---")
    btn_c1, btn_c2 = st.columns(2)

    with btn_c1:
        draft_rows_to_save = edited_df[edited_df['status'] == 'draft']
        if st.button("💾 儲存草稿變更", disabled=draft_rows_to_save.empty):
            with st.spinner("正在儲存草稿..."):
                save_salary_draft(conn, year, month, draft_rows_to_save)
                st.success("草稿已成功儲存至資料庫！")
                st.rerun()

    with btn_c2:
        draft_rows_to_finalize = edited_df[edited_df['status'] == 'draft']
        if st.button("🔒 儲存並鎖定最終版本", type="primary", disabled=draft_rows_to_finalize.empty):
            with st.spinner("正在寫入並鎖定最終薪資單..."):
                item_types = st.session_state.salary_item_types
                earning_cols = [c for c, t in item_types.items() if t == 'earning' and c in draft_rows_to_finalize.columns]
                deduction_cols = [c for c, t in item_types.items() if t == 'deduction' and c in draft_rows_to_finalize.columns]
                
                draft_rows_to_finalize.loc[:, '應付總額'] = draft_rows_to_finalize.loc[:, earning_cols].sum(axis=1, numeric_only=True)
                draft_rows_to_finalize.loc[:, '應扣總額'] = draft_rows_to_finalize.loc[:, deduction_cols].sum(axis=1, numeric_only=True)
                draft_rows_to_finalize.loc[:, '實發薪資'] = draft_rows_to_finalize['應付總額'] + draft_rows_to_finalize['應扣總額']
                draft_rows_to_finalize.loc[:, '現金'] = draft_rows_to_finalize['實發薪資'] - draft_rows_to_finalize['匯入銀行']
                
                finalize_salary_records(conn, year, month, draft_rows_to_finalize)
                st.success(f"{year}年{month}月的薪資單已成功定版！")
                st.rerun()

    with st.expander("⚠️ 進階操作"):
        finalized_records = df_to_edit[df_to_edit['status'] == 'final']
        if not finalized_records.empty:
            emp_map_df = pd.read_sql("SELECT id, name_ch FROM employee", conn)
            finalized_records_with_id = pd.merge(finalized_records, emp_map_df, left_on='員工姓名', right_on='name_ch')
            finalized_options = finalized_records_with_id['員工姓名'].tolist()
            employees_to_unlock = st.multiselect("選擇要解鎖的員工紀錄", options=finalized_options)
            
            if st.button("解鎖選定員工紀錄"):
                if not employees_to_unlock: st.error("請至少選擇一位要解鎖的員工。")
                else:
                    emp_ids_to_unlock = finalized_records_with_id[finalized_records_with_id['員工姓名'].isin(employees_to_unlock)]['id'].tolist()
                    with st.spinner("正在解鎖紀錄..."):
                        count = revert_salary_to_draft(conn, year, month, emp_ids_to_unlock)
                        st.success(f"成功解鎖 {count} 筆紀錄！")
                        st.rerun()
        else:
            st.info("目前沒有已定版的紀錄可供解鎖。")