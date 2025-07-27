# views/bonus_batch.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from services import bonus_scraper as scraper
from services import bonus_logic as logic_bonus
from db import queries_bonus as q_bonus
from db import queries_employee as q_emp

def show_page(conn):
    st.header("🌀 業務獎金批次匯入")
    st.info("此功能將登入公司系統，抓取指定月份的收款紀錄，並依規則計算業務獎金後存入資料庫中繼站。")

    # 確保 session_state 中有 'bonus_detailed_view'
    if 'bonus_detailed_view' not in st.session_state:
        st.session_state.bonus_detailed_view = pd.DataFrame()

    st.subheader("步驟 1: 輸入系統資訊與查詢區間")
    with st.form("scrape_form"):
        c1, c2 = st.columns(2)
        username = c1.text_input("公司系統帳號", type="password")
        password = c2.text_input("公司系統密碼", type="password")
        
        c3, c4 = st.columns(2)
        today = datetime.now()
        last_month = today - relativedelta(months=1)
        year = c3.number_input("選擇獎金歸屬年份", min_value=2020, max_value=today.year + 1, value=last_month.year)
        month = c4.number_input("選擇獎金歸屬月份", min_value=1, max_value=12, value=last_month.month)
        
        submitted = st.form_submit_button("執行資料抓取與計算", type="primary")

    if submitted:
        if not username or not password:
            st.error("請輸入公司系統的帳號與密碼！")
        else:
            progress_bar = st.progress(0, text="準備開始...")
            
            with st.spinner("正在從人資系統資料庫獲取員工名單..."):
                employees_df = q_emp.get_all_employees(conn)
                employee_names = employees_df['name_ch'].unique().tolist()

            if not employee_names:
                st.error("人資系統中沒有找到任何員工，無法進行查詢。")
                return

            def progress_callback(message, percent):
                progress_bar.progress(percent, text=message)
            
            with st.spinner("正在遍歷所有業務員並抓取資料，請耐心等候..."):
                all_details_df, not_found_employees = scraper.fetch_all_bonus_data(username, password, year, month, employee_names, progress_callback)
            
            if not_found_employees:
                st.warning(f"注意：在獎金系統的下拉選單中找不到以下員工，已自動跳過： {', '.join(not_found_employees)}")

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
                    del st.session_state.bonus_summary
                    del st.session_state.bonus_detailed_view
                    st.rerun()
                except Exception as e:
                    st.error(f"存入資料庫時發生錯誤: {e}")

        # **【核心修改】** 將明細顯示區塊改為可編輯、可刪除的互動介面
        with st.expander("點此查看、修改或刪除抓取明細", expanded=True):
            detailed_view_df = st.session_state.get('bonus_detailed_view', pd.DataFrame())
            
            if not detailed_view_df.empty:
                # 增加一個用於刪除的勾選框欄位
                detailed_view_df["刪除"] = False
                cols_to_show = ["刪除"] + [col for col in detailed_view_df.columns if col != "刪除"]
                
                # 使用 data_editor 讓表格可被編輯
                edited_df = st.data_editor(
                    detailed_view_df[cols_to_show], 
                    key="detail_editor"
                )
                
                c1, c2 = st.columns([1,1])
                
                if c1.button("🗑️ 刪除選中明細", use_container_width=True):
                    # 找出被勾選為 '刪除' 的列
                    rows_to_delete = edited_df[edited_df["刪除"] == True].index
                    # 從 session state 中移除這些列
                    st.session_state.bonus_detailed_view.drop(index=rows_to_delete, inplace=True)
                    st.success(f"已標記刪除 {len(rows_to_delete)} 筆明細，請點擊重算更新總覽。")
                    st.rerun()
                
                if c2.button("🔄 根據下方明細重算總覽", type="primary", use_container_width=True):
                    with st.spinner("正在根據修改後的明細重新計算..."):
                        # 將編輯器中當前的資料存回 session state
                        st.session_state.bonus_detailed_view = edited_df.drop(columns=["刪除"])
                        # 用更新後的明細資料，重新呼叫計算函式
                        summary_df, _ = logic_bonus.process_and_calculate_bonuses(
                            conn, 
                            st.session_state.bonus_detailed_view.rename(columns={v: k for k, v in logic_bonus.COLUMN_MAP.items()}, errors='ignore'), # 將中文欄位轉回英文給函式
                            year, 
                            month
                        )
                        st.session_state.bonus_summary = summary_df
                    st.success("總覽已更新！")
                    st.rerun()

            else:
                st.info("目前沒有可供檢視的明細資料。")