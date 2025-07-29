# views/bonus_batch.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from services import bonus_scraper as scraper
from services import bonus_logic as logic_bonus
from db import queries_bonus as q_bonus
from db import queries_employee as q_emp

# --- 常數定義 ---
DEFAULT_COLS = ["序號", "雇主姓名", "入境日", "外勞姓名", "帳款名稱", "帳款日", "應收金額", "收款日", "實收金額", "業務員姓名", "source"]

def show_page(conn):
    st.header("🌀 業務獎金管理")

    # --- Session State 初始化 ---
    if 'bonus_details_df' not in st.session_state:
        st.session_state.bonus_details_df = pd.DataFrame(columns=DEFAULT_COLS)
    if 'bonus_summary_df' not in st.session_state:
        st.session_state.bonus_summary_df = pd.DataFrame()

    # --- 頁面主要篩選器 ---
    st.info("請先選擇要處理的獎金月份。系統會自動載入該月份的草稿。")
    c1, c2, c3 = st.columns([2, 1, 1])
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c2.number_input("選擇年份", min_value=2020, max_value=today.year + 1, value=last_month.year)
    month = c3.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month)

    # --- 頁面初次載入或月份變更時，讀取草稿 ---
    query_key = f"{year}-{month}"
    if 'current_bonus_query' not in st.session_state or st.session_state.current_bonus_query != query_key:
        with st.spinner(f"正在讀取 {year} 年 {month} 月的獎金草稿..."):
            draft_df = q_bonus.get_bonus_details_by_month(conn, year, month, status='draft')
            st.session_state.bonus_details_df = draft_df
            st.session_state.bonus_summary_df = pd.DataFrame() # 清空舊的計算總覽
            st.session_state.current_bonus_query = query_key

    # --- 功能區塊 ---
    tab1, tab2 = st.tabs(["📝 獎金明細維護", "📊 獎金總覽計算"])

    # --- TAB 1: 獎金明細維護 ---
    with tab1:
        st.subheader("步驟 1: 編輯獎金明細 (系統抓取 + 手動新增)")
        st.write("您可以在下表中直接修改、刪除或新增獎金項目。完成所有編輯後，請點擊「💾 儲存草稿」。")

        # 可編輯的資料表格
        edited_df = st.data_editor(
            st.session_state.bonus_details_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={"source": st.column_config.TextColumn("來源", disabled=True)},
            key="bonus_details_editor"
        )
        st.session_state.bonus_details_df = edited_df # 將修改即時存回 session

        # --- 按鈕操作區 ---
        btn_c1, btn_c2 = st.columns(2)

        # 儲存草稿按鈕
        with btn_c1:
            if st.button("💾 儲存草稿", use_container_width=True):
                with st.spinner("正在儲存您的變更..."):
                    # 將 'source' 欄位為空的行（手動新增的）填上 'manual'
                    st.session_state.bonus_details_df['source'].fillna('manual', inplace=True)
                    q_bonus.upsert_bonus_details_draft(conn, year, month, st.session_state.bonus_details_df)
                st.success("草稿已成功儲存！")

        # 從外部系統抓取資料
        with btn_c2, st.expander("從外部系統抓取資料 (會覆蓋現有草稿)"):
            with st.form("scrape_form"):
                username = st.text_input("業績系統帳號", type="password")
                password = st.text_input("業績系統密碼", type="password")
                submitted = st.form_submit_button("執行資料抓取", type="primary")

                if submitted:
                    if not username or not password:
                        st.error("請輸入業績系統的帳號與密碼！")
                    else:
                        progress_bar = st.progress(0, text="準備開始...")
                        with st.spinner("正在獲取員工名單..."):
                            employees_df = q_emp.get_all_employees(conn)
                            employee_names = employees_df['name_ch'].unique().tolist()

                        def progress_callback(message, percent):
                            progress_bar.progress(percent, text=message)

                        with st.spinner("正在遍歷所有業務員並抓取資料..."):
                            raw_details_df, not_found = scraper.fetch_all_bonus_data(username, password, year, month, employee_names, progress_callback)
                            raw_details_df['source'] = 'scraped' # 標記來源
                        
                        # 將新抓取的資料存為草稿，並更新到頁面上
                        q_bonus.upsert_bonus_details_draft(conn, year, month, raw_details_df)
                        st.session_state.bonus_details_df = raw_details_df
                        st.success(f"資料抓取完成！共抓取 {len(raw_details_df)} 筆明細。")
                        if not_found:
                            st.warning(f"在系統中找不到員工: {', '.join(not_found)}")
                        st.rerun()

    # --- TAB 2: 獎金總覽計算 ---
    with tab2:
        st.subheader("步驟 2: 計算獎金總覽")
        st.info("此處會根據您在「明細維護」頁籤儲存的草稿進行計算。")

        # 計算按鈕
        if st.button("🔄 根據最新草稿計算總覽", type="primary"):
            df_to_calc = q_bonus.get_bonus_details_by_month(conn, year, month, status='draft')
            if df_to_calc.empty:
                st.warning("目前沒有草稿資料可供計算。")
                st.session_state.bonus_summary_df = pd.DataFrame()
            else:
                with st.spinner("正在處理明細並計算獎金..."):
                    summary_df, _ = logic_bonus.process_and_calculate_bonuses(conn, df_to_calc, year, month)
                    st.session_state.bonus_summary_df = summary_df
                st.success("獎金總覽計算完成！")

        # 顯示計算結果
        if not st.session_state.bonus_summary_df.empty:
            st.markdown("---")
            st.markdown("#### 計算結果預覽")
            st.dataframe(st.session_state.bonus_summary_df, use_container_width=True)

            st.markdown("---")
            st.subheader("步驟 3: 鎖定最終版本")
            st.warning(f"此操作將會把 {year} 年 {month} 月的獎金總額寫入薪資系統，並將所有相關明細標記為「最終版」，之後將無法再透過此頁面修改。")

            if st.button("🔒 確認計算結果並鎖定", type="primary"):
                summary_df_to_save = st.session_state.bonus_summary_df
                if summary_df_to_save.empty:
                    st.error("沒有可鎖定的計算結果。")
                else:
                    try:
                        with st.spinner("正在寫入獎金總額並鎖定明細..."):
                            # 1. 儲存計算總額到中繼站
                            q_bonus.save_bonuses_to_monthly_table(conn, year, month, summary_df_to_save)
                            # 2. 將草稿狀態更新為 final
                            q_bonus.finalize_bonus_details(conn, year, month)
                        st.success(f"{year} 年 {month} 月的業務獎金已成功鎖定！")
                        # 清空 session state 以便處理下一個月份
                        st.session_state.bonus_details_df = pd.DataFrame(columns=DEFAULT_COLS)
                        st.session_state.bonus_summary_df = pd.DataFrame()
                        st.session_state.current_bonus_query = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"鎖定時發生錯誤: {e}")
        else:
            st.info("點擊上方按鈕以計算獎金總覽。")