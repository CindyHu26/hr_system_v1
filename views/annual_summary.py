# pages/annual_summary.py
import streamlit as st
from datetime import datetime

# 導入新架構的模組
from db import queries_salary_items as q_items
from services import reporting_logic as logic_report

def show_page(conn):
    st.header("📊 年度薪資總表")
    st.info("此頁面用於檢視整年度特定薪資項目的加總。")

    st.subheader("篩選條件")
    c1, c2 = st.columns([1, 3])
    
    with c1:
        current_year = datetime.now().year
        year = st.number_input("選擇年份", min_value=2020, max_value=current_year + 5, value=current_year)

    with c2:
        try:
            all_items_df = q_items.get_all_salary_items(conn, active_only=True)
            item_options = dict(zip(all_items_df['name'], all_items_df['id']))
            default_items = [
                row['name'] for _, row in all_items_df.iterrows()
                if row['type'] == 'earning'
            ]
            selected_item_names = st.multiselect(
                "選擇要加總的薪資項目*",
                options=item_options.keys(),
                default=default_items,
                help="預設選取所有「給付」類型項目。"
            )
            selected_item_ids = [item_options[name] for name in selected_item_names]
        except Exception as e:
            st.error(f"讀取薪資項目時發生錯誤: {e}")
            selected_item_ids = []

    if st.button("產生年度報表", type="primary"):
        if not selected_item_ids:
            st.warning("請至少選擇一個薪資項目！")
        else:
            with st.spinner("正在彙總整年度資料..."):
                summary_df = logic_report.generate_annual_salary_summary(conn, year, selected_item_ids)
                st.session_state.annual_summary_df = summary_df

    if 'annual_summary_df' in st.session_state:
        st.write("---")
        st.subheader("報表預覽")
        display_df = st.session_state.annual_summary_df
        st.dataframe(display_df, width='stretch')

        if not display_df.empty:
            csv = display_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載CSV報表",
                data=csv,
                file_name=f"annual_salary_summary_{year}.csv",
                mime="text/csv",
            )