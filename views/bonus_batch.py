# pages/bonus_batch.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

# 導入新架構的模組
from services import bonus_scraper as scraper
from services import bonus_logic as logic_bonus
from db import queries_bonus as q_bonus

def show_page(conn):
    st.header("🌀 業務獎金批次匯入")
    st.info("此功能將會登入舊版業績系統，抓取指定月份的收款紀錄，並依規則計算業務獎金後存入資料庫中繼站。")

    st.subheader("步驟 1: 輸入系統資訊與查詢區間")
    with st.form("scrape_form"):
        c1, c2 = st.columns(2)
        username = c1.text_input("業績系統帳號", type="password")
        password = c2.text_input("業績系統密碼", type="password")
        
        c3, c4 = st.columns(2)
        today = datetime.now()
        # 計算上一個月的年份和月份
        last_month = today - relativedelta(months=1)
        year = c3.number_input("選擇獎金歸屬年份", min_value=2020, max_value=today.year + 1, value=last_month.year)
        month = c4.number_input("選擇獎金歸屬月份", min_value=1, max_value=12, value=last_month.month)
        
        submitted = st.form_submit_button("執行資料抓取與計算", type="primary")

    if submitted:
        if not username or not password:
            st.error("請輸入業績系統的帳號與密碼！")
        else:
            progress_bar = st.progress(0, text="準備開始...")
            
            with st.spinner("正在登入並獲取業務員列表..."):
                salespersons = scraper.get_salespersons_list(username, password)
            
            if not salespersons:
                st.error("無法獲取業務員列表，請檢查帳號密碼或系統連線。")
                return

            def progress_callback(message, percent):
                progress_bar.progress(percent, text=message)

            with st.spinner("正在遍歷所有業務員並抓取資料，請耐心等候..."):
                all_details_df = scraper.fetch_all_bonus_data(username, password, year, month, salespersons, progress_callback)
            
            progress_bar.progress(1.0, text="資料抓取完成！正在進行獎金計算...")
            
            with st.spinner("正在處理明細並計算獎金..."):
                summary_df, detailed_view_df = logic_bonus.process_and_calculate_bonuses(conn, all_details_df, year, month)
            
            st.session_state.bonus_summary = summary_df
            st.session_state.bonus_detailed_view = detailed_view_df
            st.success("獎金計算完成！")
            st.rerun()

    if 'bonus_summary' in st.session_state:
        st.write("---")
        st.subheader("步驟 2: 計算結果預覽")
        summary_df = st.session_state.bonus_summary
        
        if summary_df.empty:
            st.warning("當月無任何符合條件的獎金產生。")
        else:
            st.dataframe(summary_df)
            
            st.write("---")
            st.subheader(f"步驟 3: 存入 {year} 年 {month} 月獎金紀錄")
            st.warning("此操作將會覆蓋資料庫中該月份的所有業務獎金紀錄。")
            
            if st.button(f"確認存入 {len(summary_df)} 筆獎金紀錄", type="primary"):
                try:
                    with st.spinner("正在寫入資料庫..."):
                        count = q_bonus.save_bonuses_to_monthly_table(conn, year, month, summary_df)
                    st.success(f"成功將 {count} 筆獎金紀錄存入資料庫！")
                    # 清除 session state 避免重複操作
                    del st.session_state.bonus_summary
                    del st.session_state.bonus_detailed_view
                    st.rerun()
                except Exception as e:
                    st.error(f"存入資料庫時發生錯誤: {e}")

        with st.expander("點此查看完整抓取明細與計算過程"):
            detailed_view_df = st.session_state.get('bonus_detailed_view', pd.DataFrame())
            st.dataframe(detailed_view_df)