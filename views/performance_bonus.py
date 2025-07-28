# views/performance_bonus.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import traceback

# 導入新架構的模組
from services import performance_bonus_logic as logic_perf
import config

def show_page(conn):
    st.header("🏆 績效獎金計算")
    st.info("此功能將登入外部系統，抓取數據後計算績效獎金，並自動發配給當月有出勤紀錄的員工。")

    if not config.PERFORMANCE_BONUS_URL:
        st.error("錯誤：請先在您的 .env 檔案中設定 PERFORMANCE_BONUS_URL 的值。")
        st.code("PERFORMANCE_BONUS_URL=http://your_system_ip/path/to/page.php")
        return

    st.subheader("步驟 1: 輸入系統資訊與查詢區間")
    with st.form("perf_bonus_form"):
        c1, c2 = st.columns(2)
        username = c1.text_input("外部系統帳號", type="password", help="用於登入並抓取數據的帳號")
        password = c2.text_input("外部系統密碼", type="password", help="對應的密碼")

        c3, c4 = st.columns(2)
        today = datetime.now()
        last_month = today - relativedelta(months=1)
        year = c3.number_input("獎金歸屬年份", min_value=2020, max_value=today.year + 1, value=last_month.year)
        month = c4.number_input("獎金歸屬月份", min_value=1, max_value=12, value=last_month.month)

        submitted = st.form_submit_button("執行計算並儲存獎金", type="primary")

    if submitted:
        if not username or not password:
            st.error("請輸入外部系統的帳號與密碼！")
        else:
            try:
                with st.spinner(f"正在為 {year}-{month} 計算績效獎金，請稍候..."):
                    report = logic_perf.calculate_and_save_performance_bonus(
                        conn=conn,
                        username=username,
                        password=password,
                        year=year,
                        month=month
                    )
                st.session_state['perf_bonus_report'] = report
                st.rerun() # 使用 rerun 來刷新頁面並顯示報告

            except Exception as e:
                st.error(f"執行過程中發生嚴重錯誤：{e}")
                st.code(traceback.format_exc())

    if 'perf_bonus_report' in st.session_state:
        st.write("---")
        st.subheader("計算結果報告")
        report = st.session_state['perf_bonus_report']
        
        st.success(f"操作完成！目標人數為：**{report['target_count']}** 人。")
        st.info(f"每人績效獎金金額為：**{report['target_count']} x 50 = {report['bonus_per_person']} 元**。")

        if report['eligible_employees_df'] is not None and not report['eligible_employees_df'].empty:
            st.markdown(f"#### ✅ 成功發配獎金給以下 **{report['saved_count']}** 位員工：")
            st.dataframe(report['eligible_employees_df'], use_container_width=True)
        else:
            st.warning("該月份在打卡系統中沒有找到任何有出勤紀錄的員工，因此未發配任何獎金。")
        
        if report['errors']:
            st.error("過程中發生以下錯誤：")
            for error in report['errors']:
                st.write(f"- {error}")
        
        if st.button("清除報告"):
            del st.session_state['perf_bonus_report']
            st.rerun()