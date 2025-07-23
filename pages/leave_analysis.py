import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np
import traceback
from utils import (
    get_all_employees,
    read_leave_file,
    check_leave_hours,
    generate_leave_attendance_comparison,
    get_leave_df_from_db,
    batch_insert_leave_records,
    DEFAULT_GSHEET_URL
)

def show_page(conn):
    """
    顯示請假與異常分析頁面的主函式
    """
    st.header("請假與異常分析")
    
    # **核心修改：將三頁籤改為兩頁籤**
    tab1, tab2 = st.tabs(["請假時數核對與匯入", "請假與出勤重疊分析"])

    # --- 原 Tab 2 的內容，現在是 Tab 1 ---
    with tab1:
        st.subheader("核對請假單時數並匯入資料庫")
        st.info("此功能會讀取請假紀錄並核算時數。您可以在下方的表格中直接編輯，確認無誤後，再點擊「匯入」按鈕。")
        
        source_type = st.radio("選擇資料來源", ("Google Sheet (建議)", "上傳 Excel 檔案"), horizontal=True, key="leave_source")
        if source_type == "Google Sheet (建議)":
            source_input = st.text_input("輸入 Google Sheet 分享連結", value=DEFAULT_GSHEET_URL)
        else:
            source_input = st.file_uploader("上傳請假紀錄 Excel 檔", type=['xlsx'])
        
        if st.button("讀取並核對時數", key="check_hours_button"):
            if not source_input:
                st.warning("請提供資料來源！")
            else:
                try:
                    with st.spinner("正在讀取與核對資料..."):
                        leave_df = read_leave_file(source_input)
                        check_df = check_leave_hours(leave_df)
                        st.session_state['leave_check_results'] = check_df
                except Exception as e:
                    st.error(f"處理時發生錯誤: {e}")
                    st.error(traceback.format_exc())
                    st.session_state['leave_check_results'] = None
        
        if 'leave_check_results' in st.session_state and st.session_state['leave_check_results'] is not None:
            st.write("---")
            st.subheader("步驟 1: 核對與編輯假單")
            st.caption("您可以在下表中直接修改「假別」、「開始/結束時間」、「時數」等欄位。修改會被自動儲存。")
            
            edited_df = st.data_editor(
                st.session_state['leave_check_results'],
                use_container_width=True,
                num_rows="dynamic"
            )
            st.session_state['leave_check_results'] = edited_df

            st.write("---")
            st.subheader("步驟 2: 將上方編輯後的假單匯入資料庫")
            st.warning("匯入操作會以「假單申請ID」為基準，覆蓋資料庫中已有的紀錄。")
            
            if st.button("✅ 確認並將上方表格的內容匯入資料庫", type="primary"):
                try:
                    df_to_import = st.session_state['leave_check_results']
                    with st.spinner("正在寫入資料庫..."):
                        count = batch_insert_leave_records(conn, df_to_import)
                    st.success(f"成功匯入/更新了 {count} 筆請假紀錄！")
                except Exception as e:
                    st.error(f"匯入時發生錯誤: {e}")
                    st.error(traceback.format_exc())

    # --- 原 Tab 3 的內容，現在是 Tab 2 ---
    with tab2:
        st.subheader("比對請假紀錄與實際打卡狀況")
        st.info("此功能會直接讀取**資料庫中已匯入**的假單，與出勤紀錄進行比對。")
        
        st.write("---")
        st.markdown("#### 請選擇比對月份")
        c1, c2 = st.columns(2)
        today = datetime.now()
        year = c1.number_input("年份", min_value=2020, max_value=today.year + 1, value=today.year, key="conflict_year")
        month = c2.number_input("月份", min_value=1, max_value=12, value=today.month, key="conflict_month")
        
        if st.button("開始交叉比對", key="conflict_button"):
            try:
                with st.spinner("正在從資料庫讀取資料並進行比對..."):
                    leave_df = get_leave_df_from_db(conn, year, month)
                    
                    if leave_df.empty:
                        st.warning(f"在 {year} 年 {month} 月的資料庫中，找不到任何已匯入的請假紀錄。")
                        st.session_state['comparison_results'] = pd.DataFrame()
                    else:
                        attendance_df = pd.read_sql_query("SELECT * FROM attendance", conn)
                        emp_df = get_all_employees(conn)
                        
                        comparison_df = generate_leave_attendance_comparison(leave_df, attendance_df, emp_df, year, month)
                        st.session_state['comparison_results'] = comparison_df
            except Exception as e:
                st.error(f"比對過程中發生錯誤: {e}")
                st.error(traceback.format_exc())
                st.session_state['comparison_results'] = None

        if 'comparison_results' in st.session_state and st.session_state['comparison_results'] is not None:
            results_df = st.session_state['comparison_results']
            
            st.write("---")
            st.subheader("交叉比對結果")

            if results_df.empty:
                st.info(f"在 {year} 年 {month} 月中，未發現任何可供比對的紀錄。")
            else:
                show_only_anomalies = st.checkbox("僅顯示異常紀錄", key="conflict_anomalies_check")
                st.caption("異常紀錄包含：「請假期間有打卡」和「無出勤且無請假紀錄」。")
                
                if show_only_anomalies:
                    anomalous_statuses = ['異常：請假期間有打卡', '無出勤且無請假紀錄']
                    display_df = results_df[results_df['狀態註記'].isin(anomalous_statuses)]
                else:
                    display_df = results_df
                
                if display_df.empty:
                    st.info("在當前條件下無符合的紀錄。")
                else:
                    st.dataframe(display_df, use_container_width=True)
                    
                    fname = f"leave_attendance_comparison_{year}-{month:02d}.csv"
                    st.download_button(
                        "下載當前檢視的報告CSV",
                        display_df.to_csv(index=False).encode("utf-8-sig"),
                        file_name=fname
                    )