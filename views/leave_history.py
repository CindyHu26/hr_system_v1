# views/leave_history.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from db import queries_attendance as q_att

def show_page(conn):
    st.header("📖 請假紀錄總覽與分析")
    st.info("您可以在此查詢所有已匯入的請假紀錄，並進行數據統計。")

    # --- 篩選條件 ---
    st.subheader("篩選條件")
    c1, c2 = st.columns([1, 1])
    today = datetime.now()
    last_month = today - relativedelta(months=1) # [新增] 計算上一個月

    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year, key="lh_year")
    
    month_options = {f"{i}月": i for i in range(1, 13)}
    month_options["全年"] = 0
    
    # 讓 selectbox 預設選中上一個月
    selected_month_name = c2.selectbox(
        "選擇月份 (可選 '全年' 進行年度統計)", 
        options=list(month_options.keys()), 
        index=last_month.month - 1 # 月份是1-12，索引是0-11
    )
    month = month_options[selected_month_name]

    # --- 查詢與顯示 ---
    try:
        df_for_display = pd.DataFrame() # 初始化一個空的 DF
        
        if month == 0:
            df_for_display = q_att.get_leave_records_by_year(conn, year)
            st.markdown(f"#### {year} 年 全年度請假紀錄")
        else:
            df_for_display = q_att.get_leave_records_by_month(conn, year, month)
            st.markdown(f"#### {year} 年 {month} 月請假紀錄")

        display_cols = ['員工姓名', '假別', '開始時間', '結束時間', '時數', '事由', '簽核人', '狀態', '假單ID']
        existing_cols = [col for col in display_cols if col in df_for_display.columns]
        
        st.session_state.leave_history_df = df_for_display # 將查詢結果存入 session
        
        st.dataframe(df_for_display[existing_cols], width='stretch')

        if not df_for_display.empty:
            csv = df_for_display.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載查詢結果 (CSV)",
                data=csv,
                file_name=f"leave_history_{year}-{selected_month_name}.csv",
                mime="text/csv",
            )
        else:
             st.info("在選定的時間範圍內查無請假紀錄。")

    except Exception as e:
        st.error(f"讀取請假紀錄時發生錯誤: {e}")
        st.session_state.leave_history_df = pd.DataFrame()

    st.write("---")

    # --- 數據分析與統計區塊 ---
    st.subheader("📊 數據分析與統計")
    if 'leave_history_df' in st.session_state and not st.session_state.leave_history_df.empty:
        df_for_stats = st.session_state.leave_history_df
        
        # 【核心修改】無論是月份還是年度，都使用同樣的統計邏輯
        period_str = f"{year}年 {selected_month_name}" if month != 0 else f"{year}年 全年"
        st.markdown(f"##### {period_str} 個人假單統計 (單位：小時)")
        
        summary_df = df_for_stats.groupby(['員工姓名', '假別'])['時數'].sum().unstack(fill_value=0)
        
        if not summary_df.empty:
            summary_df['總計'] = summary_df.sum(axis=1)
            st.dataframe(summary_df.style.format("{:.2f}").background_gradient(cmap='viridis', subset=['總計']), width='stretch')
        else:
            st.info("目前篩選範圍內無資料可供統計。")
            
    else:
        st.info("請先查詢出資料，才能進行統計分析。")