import streamlit as st
import pandas as pd
from datetime import datetime
from utils_bonus_scraper import get_salespersons_list, fetch_bonus_data, save_bonus_data

def show_page(conn):
    st.header("💰 業務獎金計算")
    st.info("此功能將自動從外部系統爬取業績資料，計算獎金，並可將結果儲存至資料庫。")

    # --- 1. 使用者輸入介面 ---
    with st.form("bonus_calc_form"):
        st.subheader("請輸入登入與計算條件")
        
        # --- [KEY CHANGE] 新增帳號密碼輸入 ---
        cred_col1, cred_col2 = st.columns(2)
        with cred_col1:
            username = st.text_input("外部系統帳號", value="cindyhu")
        with cred_col2:
            password = st.text_input("外部系統密碼", type="password", value="2322")

        st.write("---")
        
        # --- [KEY CHANGE] 傳遞帳密來獲取業務員列表 ---
        with st.spinner("正在嘗試連線並獲取業務員列表..."):
            salespersons = get_salespersons_list(username, password)
        
        if not salespersons:
            st.error("登入失敗或無法從外部系統獲取業務員列表，請檢查帳號密碼或系統狀態。")
            st.form_submit_button("擷取與計算", disabled=True)
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                year = st.number_input("選擇年份", min_value=2020, max_value=datetime.now().year + 5, value=datetime.now().year)
            with col2:
                month = st.number_input("選擇月份", min_value=1, max_value=12, value=datetime.now().month)
            with col3:
                salesperson = st.selectbox("選擇業務人員*", options=salespersons)
            
            submitted = st.form_submit_button("🚀 開始擷取與計算", use_container_width=True)

    # --- 2. 執行與顯示結果 ---
    if submitted:
        with st.spinner(f"正在為 {salesperson} 擷取 {year}-{month} 的業績資料...請稍候..."):
            try:
                # --- [KEY CHANGE] 傳遞帳密給爬蟲 ---
                details_df, total, bonus = fetch_bonus_data(username, password, year, month, salesperson)
                
                st.session_state.bonus_result = {
                    "salesperson": salesperson, "year": year, "month": month,
                    "details_df": details_df, "total": total, "bonus": bonus
                }
            except Exception as e:
                st.error(f"擷取過程中發生錯誤: {e}")
                st.session_state.bonus_result = None
    
    # 如果 session_state 中有結果，則顯示
    if 'bonus_result' in st.session_state and st.session_state.bonus_result:
        result = st.session_state.bonus_result
        
        if result["details_df"] is not None:
            st.success(f"資料擷取成功！")
            
            st.metric(label=f"{result['salesperson']} {result['year']}-{result['month']} 業務獎金 (已排除異常)", value=f"{result['bonus']:,.0f}")
            st.metric(label="總收款金額 (已排除異常)", value=f"{result['total']:,.0f}", delta_color="off")
            
            with st.expander("顯示詳細資料 (包含異常)"):
                st.dataframe(result["details_df"])
                
            if st.button("💾 確認無誤，儲存至資料庫", type="primary"):
                with st.spinner("正在儲存結果..."):
                    try:
                        log_id = save_bonus_data(conn, result['salesperson'], result['year'], result['month'], result['total'], result['bonus'], result['details_df'])
                        st.success(f"已成功將紀錄儲存至資料庫！紀錄 ID: {log_id}")
                        del st.session_state.bonus_result
                    except Exception as e:
                        st.error(f"儲存失敗: {e}")
        else:
            st.error("找不到符合條件的資料。")

    # --- 3. 顯示歷史紀錄 ---
    st.write("---")
    st.subheader("📜 歷史計算紀錄")
    try:
        history_df = pd.read_sql("SELECT salesperson_name as '業務員', year as '年', month as '月', total_received as '總收款', calculated_bonus as '計算獎金', scraped_at as '計算時間' FROM sales_bonus_log ORDER BY scraped_at DESC", conn)
        st.dataframe(history_df, use_container_width=True)
    except Exception as e:
        st.warning(f"讀取歷史紀錄失敗: {e}")