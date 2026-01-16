# views/insurance_grade_management.py
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date

from db import queries_insurance as q_ins
from db import queries_common as q_common
from db import queries_config as q_config
from services import insurance_logic as logic_ins

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

COLUMN_MAP = {
    'grade': '級', 'salary_min': '薪資下限', 'salary_max': '薪資上限',
    'employee_fee': '員工負擔', 'employer_fee': '雇主負擔', 'gov_fee': '政府補助',
    'note': '備註'
}

def show_page(conn):
    st.header("🏦 勞健保級距管理")
    st.info("您可以在此維護不同版本的勞、健保投保級距與費用。")

    try:
        grades_df = q_ins.get_insurance_grades(conn)
        st.subheader("歷史級距總覽")
        if not grades_df.empty:
            versions = sorted(pd.to_datetime(grades_df['start_date']).unique(), reverse=True)
            selected_version_date = st.selectbox(
                "選擇要檢視的版本 (依起算日)",
                versions,
                format_func=lambda dt: dt.strftime('%Y-%m-%d')
            )
            display_df = grades_df[pd.to_datetime(grades_df['start_date']) == selected_version_date]
            labor_df = display_df[display_df['type'] == 'labor'].drop(columns=['type', 'start_date', 'id']).rename(columns=COLUMN_MAP)
            health_df = display_df[display_df['type'] == 'health'].drop(columns=['type', 'start_date', 'id']).rename(columns=COLUMN_MAP)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 勞工保險級距")
                st.dataframe(labor_df, width='stretch')
            with col2:
                st.markdown("#### 全民健康保險級距")
                st.dataframe(health_df, width='stretch')
        else:
            st.warning("資料庫中尚無任何級距資料，請先從下方進行更新。")
    except Exception as e:
        st.error(f"讀取級距表時發生錯誤: {e}")
        return

    st.write("---")
    st.subheader("資料更新")
    
    start_date = st.date_input("請選擇此份資料的「適用起算日」", value=date(datetime.now().year, 1, 1))
    
    tab1, tab2 = st.tabs(["👷 勞工保險", "🏥 全民健康保險"])

    with tab1:
        st.markdown("##### 更新勞工保險投保薪資分級表")
        uploaded_labor_file = st.file_uploader("上傳勞保級距 Excel 檔", type=['xls', 'xlsx'], key="labor_uploader")
        
        if uploaded_labor_file:
            try:
                with st.spinner("正在智慧解析您上傳的 Excel 檔案..."):
                    parsed_df = logic_ins.parse_labor_insurance_excel(uploaded_labor_file)
                st.success(f"成功解析檔案！此資料將以 **{start_date}** 作為起算日匯入。預覽如下：")
                st.dataframe(parsed_df)
                
                if st.button(f"✅ 確認匯入「勞保」級距表", type="primary"):
                    count = q_ins.batch_insert_or_replace_grades(conn, parsed_df, 'labor', start_date)
                    st.success(f"成功匯入/更新 {count} 筆起算日為 {start_date} 的勞保級距資料！")
                    st.rerun()
            except Exception as e:
                st.error(f"處理勞保檔案時發生錯誤：{e}")

    with tab2:
        st.markdown("##### 更新健保投保金額分級表")
        db_configs = q_config.get_all_configs(conn)
        default_health_url = db_configs.get('HEALTH_INSURANCE_URL', "https://www.nhi.gov.tw/ch/cp-19418-9eefb-2576-1.html")
        health_url = st.text_input("健保署保費負擔金額表網址", value=default_health_url)
        
        if st.button("🔗 從網址解析並預覽"):
            status_text = st.empty()
            try:
                status_text.info("正在啟動瀏覽器模擬器 (Selenium)...")
                
                # --- 使用 Selenium 替代 requests ---
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                html_content = ""
                try:
                    status_text.info(f"正在前往 {health_url} ...")
                    driver.get(health_url)
                    time.sleep(3) # 等待網頁載入
                    html_content = driver.page_source
                finally:
                    driver.quit()

                status_text.info("正在解析表格內容...")
                # 這裡直接傳入 html_content
                st.session_state.parsed_health_df = logic_ins.parse_health_insurance_html(html_content)
                status_text.success("成功解析健保網頁表格！")
            except Exception as e:
                status_text.error(f"處理失敗: {e}")
                st.error("請確認您的電腦已安裝 Google Chrome 瀏覽器。")

        if 'parsed_health_df' in st.session_state and st.session_state.parsed_health_df is not None:
            st.markdown(f"##### 解析結果預覽 (將以 **{start_date}** 作為起算日匯入)")
            st.dataframe(st.session_state.parsed_health_df)
            
            if st.button(f"✅ 確認匯入「健保」級距表", type="primary"):
                try:
                    # 使用原始變數 start_date 和原始函式 q_ins.batch_insert_or_replace_grades
                    count = q_ins.batch_insert_or_replace_grades(conn, st.session_state.parsed_health_df, 'health', start_date)
                    st.success(f"成功匯入/更新 {count} 筆起算日為 {start_date} 的健保級距資料！")
                    del st.session_state.parsed_health_df
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"寫入資料庫時發生錯誤：{e}")