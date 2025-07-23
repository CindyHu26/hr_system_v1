# page_annual_leave.py
import streamlit as st
import pandas as pd
from utils import get_annual_leave_summary

def show_page(conn):
    st.header("年度特休天數計算")
    st.info("系統會根據每位員工的到職日，計算其在當前『週年制』年度的特休天數、已使用天數與剩餘天數。")

    if st.button("重新計算所有員工特休"):
        with st.spinner("正在計算中..."):
            summary_df = get_annual_leave_summary(conn)
            st.session_state['annual_leave_summary'] = summary_df
    
    if 'annual_leave_summary' in st.session_state:
        st.dataframe(st.session_state['annual_leave_summary'])
        
        fname = f"annual_leave_summary_{pd.Timestamp.now().strftime('%Y%m%d')}.csv"
        st.download_button(
            "下載總結報告",
            st.session_state['annual_leave_summary'].to_csv(index=False).encode("utf-8-sig"),
            file_name=fname
        )

    with st.expander("勞基法特休天數規則"):
        st.markdown("""
        - **滿 6 個月 ~ 未滿 1 年**: 3 天
        - **滿 1 年 ~ 未滿 2 年**: 7 天
        - **滿 2 年 ~ 未滿 3 年**: 10 天
        - **滿 3 年 ~ 未滿 5 年**: 14 天
        - **滿 5 年 ~ 未滿 10 年**: 15 天
        - **滿 10 年以上**: 每多 1 年加 1 天，最高至 30 天
        """)