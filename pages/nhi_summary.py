# pages/nhi_summary.py
import streamlit as st
import pandas as pd
from datetime import datetime

# 導入新架構的模組
import config
from services import reporting_logic as logic_report

def show_page(conn):
    st.header("健保補充保費試算")
    st.info("本頁面將依健保署規定，試算投保單位（公司）應負擔的補充保費。")

    with st.expander("點此查看計算規則"):
        st.markdown(f"""
        #### 計算公式
        **應繳保費 = 計費差額 × 補充保險費率 ({config.NHI_SUPPLEMENT_RATE * 100:.2f}%)**
        - **計費差額 = (A) 支付薪資總額 - (B) 健保投保薪資總額**
        - (A) 支付薪資總額: 當月公司支付給所有員工的薪資總和 (所有「給付」項目)。
        - (B) 健保投保薪資總額: 當月公司所有在保員工，其健保投保級距金額的加總。
        *注意：如果計費差額為負數或零，則當月無需繳納補充保費。*
        """)

    current_year = datetime.now().year
    year = st.number_input("選擇要計算的年份", min_value=2020, max_value=current_year + 5, value=current_year)

    if st.button("🚀 開始計算", type="primary"):
        with st.spinner(f"正在彙總 {year} 年度的健保補充保費資料..."):
            try:
                # 由於此功能較複雜且依賴多個查詢，先暫時保留在此頁面
                # 未來可將核心邏輯移至 services/reporting_logic.py
                st.info("此功能正在開發中，將顯示健保補充保費的年度試算結果。")
                # summary_df = logic_report.generate_nhi_employer_summary(conn, year)
                # st.session_state.nhi_summary_df = summary_df
            except Exception as e:
                st.error(f"計算過程中發生錯誤: {e}")

    if 'nhi_summary_df' in st.session_state:
        st.write("---")
        st.subheader(f"{year} 年度計算結果")
        display_df = st.session_state.nhi_summary_df
        formatted_df = display_df.copy()
        for col in formatted_df.columns:
            if pd.api.types.is_numeric_dtype(formatted_df[col]) and col != '月份':
                formatted_df[col] = formatted_df[col].map('{:,.0f}'.format)
        st.dataframe(formatted_df, use_container_width=True, hide_index=True)