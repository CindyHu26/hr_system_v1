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

    with tab2:
        st.subheader("交叉比對請假與出勤紀錄")
        st.info("此功能會直接讀取 **資料庫中已匯入** 的假單，與出勤紀錄進行比對，找出異常情況。")
        st.write("---")
        st.markdown("#### 請選擇比對月份")
        c1, c2 = st.columns(2)
        today = datetime.now()
        year_conflict = c1.number_input("年份", min_value=2020, max_value=today.year + 1, value=today.year, key="conflict_year")
        month_conflict = c2.number_input("月份", min_value=1, max_value=12, value=today.month, key="conflict_month")

        if st.button("開始交叉比對", key="conflict_button"):
            st.info("功能開發中... 此處將顯示資料庫中假單與打卡紀錄的重疊分析結果。")