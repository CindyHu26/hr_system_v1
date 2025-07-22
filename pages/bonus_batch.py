# pages/bonus_batch.py
import streamlit as st
import pandas as pd
from datetime import datetime
from services import bonus_scraper, bonus_logic
from db import queries as q

def show_page(conn):
    st.header("🌀 業務獎金批次處理")
    st.info("此功能將遍歷所有業務員，自動從外部系統抓取業績，計算獎金，並匯入到薪資系統待算區。")

    with st.form("bonus_batch_form"):
        st.subheader("1. 登入與執行")
        
        c1, c2 = st.columns(2)
        username = c1.text_input("外部系統帳號", value="cindyhu")
        password = c2.text_input("外部系統密碼", type="password", value="2322")

        c3, c4 = st.columns(2)
        year = c3.number_input("選擇年份", min_value=2020, max_value=datetime.now().year + 5, value=datetime.now().year)
        month = c4.number_input("選擇月份", min_value=1, max_value=12, value=datetime.now().month)

        submitted = st.form_submit_button("🚀 開始批次擷取與計算", use_container_width=True, type="primary")

    if submitted:
        st.session_state.batch_result = {}
        progress_bar = st.progress(0, text="準備開始...")

        with st.spinner("正在連線並獲取業務員列表..."):
            salespersons = bonus_scraper.get_salespersons_list(username, password)
        
        if not salespersons:
            st.error("登入失敗或無法獲取業務員列表，請檢查帳號密碼。")
        else:
            def progress_callback(message, percent):
                progress_bar.progress(percent, text=message)
            
            all_details_df = bonus_scraper.fetch_all_bonus_data(username, password, year, month, salespersons, progress_callback)
            progress_bar.progress(1.0, text="所有資料已擷取完畢！正在進行最終計算...")

            summary_df, detailed_view_df = bonus_logic.process_and_calculate_bonuses(conn, all_details_df, year, month)
            
            st.session_state.batch_result = {
                "year": year, "month": month,
                "summary": summary_df,
                "details": detailed_view_df
            }
            progress_bar.empty()

    if 'batch_result' in st.session_state and st.session_state.batch_result:
        result = st.session_state.batch_result
        summary = result.get("summary")
        details = result.get("details")

        st.subheader("2. 計算結果總覽")
        if summary is not None and not summary.empty:
            st.dataframe(summary)
            
            st.subheader("3. 獎金明細查詢")
            filter_option = st.radio(
                "選擇檢視模式",
                ["所有明細", "僅顯示異常款項", "僅顯示本月付清款項"],
                horizontal=True
            )
            
            if filter_option == "所有明細":
                display_details = details
            elif filter_option == "僅顯示異常款項":
                display_details = details[details['is_abnormal'] == True]
            else:
                display_details = details[details['is_fully_paid'] == True]

            st.dataframe(display_details)
            
            st.write("---")
            st.subheader("4. 匯入薪資系統")
            st.warning(f"注意：此操作將會**覆蓋** {result['year']} 年 {result['month']} 月的所有現有業務獎金紀錄。")
            if st.button(f"✅ 確認並將上方 {len(summary)} 筆獎金匯入待算區", use_container_width=True):
                with st.spinner("正在寫入資料庫..."):
                    count = q.save_bonuses_to_monthly_table(conn, result['year'], result['month'], summary)
                    st.success(f"成功匯入 {count} 筆獎金紀錄！您現在可以到「薪資單產生與管理」頁面產生新的草稿。")
                    st.session_state.batch_result = {}
        else:
            st.warning("計算完成，但沒有找到任何符合條件且可計算獎金的紀錄。")
