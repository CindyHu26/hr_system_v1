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
    st.info("此功能將會登入舊版業績系統，抓取指定月份的收款紀錄，並依規則計算業務獎金後存入資料庫中繼站。")

    # 確保 session_state 中有需要的鍵
    if 'raw_bonus_details' not in st.session_state:
        st.session_state.raw_bonus_details = pd.DataFrame()
    if 'bonus_summary' not in st.session_state:
        st.session_state.bonus_summary = pd.DataFrame()


    st.subheader("步驟 1: 輸入系統資訊與查詢區間")
    with st.form("scrape_form"):
        c1, c2 = st.columns(2)
        username = c1.text_input("業績系統帳號", type="password")
        password = c2.text_input("業績系統密碼", type="password")
        
        c3, c4 = st.columns(2)
        today = datetime.now()
        last_month = today - relativedelta(months=1)
        year = c3.number_input("選擇獎金歸屬年份", min_value=2020, max_value=today.year + 1, value=last_month.year)
        month = c4.number_input("選擇獎金歸屬月份", min_value=1, max_value=12, value=last_month.month)
        
        submitted = st.form_submit_button("執行資料抓取與計算", type="primary")

    if submitted:
        if not username or not password:
            st.error("請輸入業績系統的帳號與密碼！")
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
                # **【核心修改】** 將抓回來的原始資料存到 st.session_state.raw_bonus_details
                raw_details_df, not_found_employees = scraper.fetch_all_bonus_data(username, password, year, month, employee_names, progress_callback)
                st.session_state.raw_bonus_details = raw_details_df
            
            if not_found_employees:
                st.warning(f"注意：在獎金系統的下拉選單中找不到以下員工，已自動跳過： {', '.join(not_found_employees)}")

            progress_bar.progress(1.0, text="資料抓取完成！正在進行獎金計算...")
            
            with st.spinner("正在處理明細並計算獎金..."):
                # **【核心修改】** 第一次計算也是使用完整的原始資料
                summary_df, _ = logic_bonus.process_and_calculate_bonuses(conn, st.session_state.raw_bonus_details, year, month)
                st.session_state.bonus_summary = summary_df
            
            st.success("獎金計算完成！")
            st.rerun()

    if not st.session_state.bonus_summary.empty:
        st.write("---")
        st.subheader("步驟 2: 計算結果預覽")
        st.dataframe(st.session_state.bonus_summary)
        
        st.write("---")
        st.subheader(f"步驟 3: 存入 {year} 年 {month} 月獎金紀錄")
        st.warning("此操作將會覆蓋資料庫中該月份的所有業務獎金紀錄。")
        
        if st.button(f"確認存入 {len(st.session_state.bonus_summary)} 筆獎金紀錄", type="primary"):
            try:
                with st.spinner("正在寫入資料庫..."):
                    count = q_bonus.save_bonuses_to_monthly_table(conn, year, month, st.session_state.bonus_summary)
                st.success(f"成功將 {count} 筆獎金紀錄存入資料庫！")
                # 清除 session state
                st.session_state.raw_bonus_details = pd.DataFrame()
                st.session_state.bonus_summary = pd.DataFrame()
                st.rerun()
            except Exception as e:
                st.error(f"存入資料庫時發生錯誤: {e}")

    # --- 可編輯的明細區塊 ---
    if not st.session_state.raw_bonus_details.empty:
        with st.expander("點此查看、修改或刪除抓取明細", expanded=True):
            # 為了顯示，我們產生一個僅供顯示用的版本
            _, display_df = logic_bonus.process_and_calculate_bonuses(conn, st.session_state.raw_bonus_details, year, month)
            
            if not display_df.empty:
                display_df["刪除"] = False
                # 為了能對應回原始資料，我們將原始索引加入顯示表格
                display_df['original_index'] = display_df.index
                
                cols_to_show = ["刪除"] + [col for col in display_df.columns if col not in ["刪除", "original_index"]]
                
                edited_df = st.data_editor(
                    display_df,
                    column_order=cols_to_show,
                    hide_index=True,
                    key="detail_editor"
                )
                
                c1, c2 = st.columns([1,1])
                
                if c1.button("🗑️ 刪除選中明細", use_container_width=True):
                    rows_to_delete_indices = edited_df[edited_df["刪除"] == True]['original_index']
                    # 從 **原始資料** 中刪除對應的列
                    st.session_state.raw_bonus_details.drop(index=rows_to_delete_indices, inplace=True)
                    st.success(f"已標記刪除 {len(rows_to_delete_indices)} 筆明細，請點擊重算更新總覽。")
                    st.rerun()
                
                if c2.button("🔄 根據上方明細重算總覽", type="primary", use_container_width=True):
                    with st.spinner("正在根據修改後的明細重新計算..."):
                        # **【核心修改】** 直接使用更新後的 st.session_state.raw_bonus_details 進行計算
                        summary_df, _ = logic_bonus.process_and_calculate_bonuses(
                            conn, 
                            st.session_state.raw_bonus_details, 
                            year, 
                            month
                        )
                        st.session_state.bonus_summary = summary_df
                    st.success("總覽已更新！")
                    st.rerun()

            else:
                st.info("目前沒有可供檢視的明細資料。")