# pages/leave_analysis.py
import streamlit as st
import pandas as pd
from datetime import datetime
import traceback
from dateutil.relativedelta import relativedelta

import config
from services import leave_logic as logic_leave
from db import queries_attendance as q_att

def show_page(conn):
    st.header("🌴 請假紀錄匯入與分析")
    tab1, tab2 = st.tabs(["請假單匯入與時數核對", "請假與出勤重疊分析"])

    with tab1:
        st.subheader("從外部來源匯入假單")
        st.info("此功能將讀取 Google Sheet 或 Excel 檔案中的請假紀錄，自動核算時數，並提供介面供您確認後匯入資料庫。")

        source_type = st.radio(
            "選擇資料來源",
            ("Google Sheet (建議)", "上傳 Excel 檔案"),
            horizontal=True,
            key="leave_source"
        )
        
        year, month = None, None
        
        if source_type == "Google Sheet (建議)":
            source_input = st.text_input("輸入 Google Sheet 分享連結", value=config.DEFAULT_GSHEET_URL)
            st.markdown("##### 篩選匯入月份 (僅針對 Google Sheet)")
            
            today = datetime.now()
            last_month_date = today - relativedelta(months=1)
            default_year, default_month = last_month_date.year, last_month_date.month
            
            c1, c2 = st.columns(2)
            year = c1.number_input("年份", min_value=2020, max_value=today.year + 1, value=default_year)
            month = c2.number_input("月份", min_value=1, max_value=12, value=default_month)
        else:
            source_input = st.file_uploader("上傳請假紀錄 Excel/CSV 檔", type=['xlsx', 'csv'])

        if st.button("讀取並核對時數", key="check_hours_button"):
            if not source_input:
                st.warning("請提供資料來源！")
            else:
                try:
                    # 【修改點】簡化呼叫，所有邏輯都封裝在 process_leave_file 中
                    with st.spinner("正在讀取、篩選並核算所有假單..."):
                        checked_df = logic_leave.process_leave_file(source_input, year=year, month=month)
                    
                    st.session_state['leave_check_results'] = checked_df
                    st.success(f"成功讀取並核算了 {len(checked_df)} 筆假單！")
                    
                except Exception as e:
                    st.error(f"處理時發生錯誤: {e}")
                    st.code(traceback.format_exc())
                    if 'leave_check_results' in st.session_state:
                        del st.session_state['leave_check_results']
        
        if 'leave_check_results' in st.session_state and not st.session_state['leave_check_results'].empty:
            st.markdown("---")
            st.subheader("步驟 1: 核對與編輯假單")
            st.caption("您可以在下表中直接修改「假別」、「開始/結束時間」、「核算時數」等欄位。修改會被自動儲存。")

            edited_df = st.data_editor(
                st.session_state['leave_check_results'],
                use_container_width=True,
                num_rows="dynamic",
                key="leave_editor"
            )
            st.session_state['leave_check_results'] = edited_df

            st.markdown("---")
            st.subheader("步驟 2: 匯入資料庫")
            st.warning("匯入操作會以「假單申請ID (Request ID)」為基準，若資料庫中已有該ID，紀錄將會被覆蓋。")

            if st.button("✅ 確認並將上方表格的內容匯入資料庫", type="primary"):
                try:
                    df_to_import = st.session_state['leave_check_results']
                    with st.spinner("正在寫入資料庫..."):
                        count = q_att.batch_insert_or_update_leave_records(conn, df_to_import)
                    st.success(f"成功匯入/更新了 {count} 筆請假紀錄！")
                except Exception as e:
                    st.error(f"匯入時發生錯誤: {e}")
                    st.code(traceback.format_exc())
    # 【重要改進】在 Tab 之外，顯示上一次的匯入結果
    if 'last_import_success' in st.session_state:
        if st.session_state['last_import_success']:
            st.success(f"成功匯入/更新了 {st.session_state['last_import_count']} 筆請假紀錄！")
            st.markdown("#### 本次匯入紀錄預覽：")
            st.dataframe(st.session_state['last_imported_df'], use_container_width=True)
        # 顯示完畢後，可以選擇清除狀態，避免一直顯示
        if st.button("清除匯入結果訊息"):
            del st.session_state['last_import_success']
            del st.session_state['last_import_count']
            del st.session_state['last_imported_df']
            st.rerun()

    with tab2:
        st.subheader("交叉比對缺勤紀錄與假單")
        st.info("此功能會掃描指定月份中，所有員工在打卡機上的「缺席」紀錄，並與資料庫中「已通過」的假單進行比對，幫助您找出『有缺席但沒請假』的異常情況。")
        st.write("---")
        st.markdown("#### 請選擇比對月份")
        
        c1, c2 = st.columns(2)
        today = datetime.now()
        last_month = today - relativedelta(months=1)
        year_conflict = c1.number_input("年份", min_value=2020, max_value=today.year + 1, value=last_month.year, key="conflict_year")
        month_conflict = c2.number_input("月份", min_value=1, max_value=12, value=last_month.month, key="conflict_month")

        if st.button("開始交叉比對", key="conflict_button", type="primary"):
            with st.spinner(f"正在分析 {year_conflict} 年 {month_conflict} 月的資料..."):
                try:
                    conflict_df = logic_leave.analyze_attendance_leave_conflicts(conn, year_conflict, month_conflict)
                    st.session_state['conflict_analysis_result'] = conflict_df
                except Exception as e:
                    st.error(f"分析時發生錯誤: {e}")
                    st.code(traceback.format_exc())

        if 'conflict_analysis_result' in st.session_state:
            st.markdown("---")
            st.markdown("#### 分析報告")
            result_df = st.session_state['conflict_analysis_result']
            st.dataframe(result_df, use_container_width=True)
