# views/nhi_summary.py
import streamlit as st
import pandas as pd
from datetime import datetime
import config
from services import reporting_logic as logic_report

def show_page(conn):
    st.header("健保補充保費試算 (個人高額獎金)")
    st.info("本頁面將依健保署規定，試算每位員工**全年度**因領取高額獎金（如年終、三節獎金等）而需負擔的補充保費。")
    
    with st.expander("點此查看計算規則"):
        st.markdown(f"""
        #### 計算公式
        當員工**單次**領取的獎金，或**當年度累計**的獎金總額，超過其 **當月投保金額4倍** 的門檻時，**就超過的部分**，應按補充保險費率 ({config.NHI_SUPPLEMENT_RATE * 100:.2f}%) 計算補充保費。
        
        - **應繳保費 = 應計費金額 × {config.NHI_SUPPLEMENT_RATE * 100:.2f}%**
        - **應計費金額 = 期間獎金總額 - (期間結束時的月投保薪資 × 4)**
        
        *注意：本系統會加總所有在 `config.py` 中被定義為獎金的薪資項目。*
        """)

    current_year = datetime.now().year
    year = st.number_input("選擇要計算的年份", min_value=2020, max_value=current_year + 1, value=current_year -1)

    if st.button("🚀 開始試算", type="primary"):
        with st.spinner(f"正在分段彙總 {year} 年度的個人獎金資料..."):
            try:
                periods = {
                    "端午 (1-5月)": (1, 5),
                    "中秋 (6-10月)": (6, 10),
                    "年終 (11-12月)": (11, 12),
                    "全年度 (1-12月)": (1, 12)
                }
                results = {}
                for name, (start_month, end_month) in periods.items():
                    df = logic_report.calculate_nhi_personal_bonus_for_period(conn, year, start_month, end_month)
                    results[name] = df
                
                st.session_state.nhi_period_results = results
            except Exception as e:
                st.error(f"計算過程中發生錯誤: {e}")

    if 'nhi_period_results' in st.session_state:
        st.write("---")
        st.subheader(f"{year} 年度個人補充保費分段試算結果")
        
        results = st.session_state.nhi_period_results
        
        tab_names = list(results.keys())
        tabs = st.tabs(tab_names)
        
        for i, tab_name in enumerate(tab_names):
            with tabs[i]:
                display_df = results[tab_name]
                if display_df.empty:
                    st.success(f"在此期間內，沒有任何員工的獎金總額超過需繳納補充保費的門檻。")
                else:
                    formatted_df = display_df.copy()
                    for col in formatted_df.columns:
                        if pd.api.types.is_numeric_dtype(formatted_df[col]):
                            formatted_df[col] = formatted_df[col].map('{:,.0f}'.format)
                    st.dataframe(formatted_df, use_container_width=True, hide_index=True)