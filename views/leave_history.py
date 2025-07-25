# views/leave_history.py
import streamlit as st
import pandas as pd
from datetime import datetime

from db import queries_attendance as q_att

def show_page(conn):
    st.header("📖 請假紀錄總覽")
    st.info("您可以在此查詢所有已從 Google Sheet 匯入的請假紀錄。")

    # --- 篩選條件 ---
    st.subheader("篩選條件")
    c1, c2, c3 = st.columns([1, 1, 2])
    today = datetime.now()
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=today.year, key="lh_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=today.month, key="lh_month")
    
    # --- 查詢與顯示 ---
    try:
        leave_df = q_att.get_leave_records_by_month(conn, year, month)
        
        st.markdown(f"#### {year} 年 {month} 月請假紀錄")
        
        # 【修改】調整欄位順序並加入事由、簽核人
        display_cols = [
            '員工姓名', '假別', '開始時間', '結束時間', '時數', 
            '事由', '簽核人', '狀態', '假單ID'
        ]
        existing_cols = [col for col in display_cols if col in leave_df.columns]
        
        st.dataframe(leave_df[existing_cols], use_container_width=True)

        if not leave_df.empty:
            csv = leave_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載查詢結果 (CSV)",
                data=csv,
                file_name=f"leave_history_{year}-{month:02d}.csv",
                mime="text/csv",
            )

    except Exception as e:
        st.error(f"讀取請假紀錄時發生錯誤: {e}")