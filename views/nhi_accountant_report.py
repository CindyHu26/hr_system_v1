# views/nhi_accountant_report.py
import streamlit as st
from datetime import datetime
import pandas as pd

# 導入新架構的模組
from db import queries_salary_items as q_items
from services import reporting_logic as logic_report

def show_page(conn):
    st.header("🧾 會計用二代健保總表")
    st.info("此頁面用於匯出特定年度、特定獎金項目的加總表，以便會計事務所計算二代健保補充保費。")

    st.subheader("篩選條件")
    c1, c2 = st.columns([1, 3])
    
    with c1:
        current_year = datetime.now().year
        # 預設查詢去年
        year = st.number_input("選擇年份", min_value=2020, max_value=current_year + 5, value=current_year - 1)

    with c2:
        try:
            all_items_df = q_items.get_all_salary_items(conn, active_only=True)
            item_options = dict(zip(all_items_df['name'], all_items_df['id']))
            
            # 預設選取所有常見的獎金/加給項目
            default_bonus_items = [
                "津貼加班", "業務獎金", "特休未休", "主管津貼", 
                "仲介師", "加薪", "補助", "績效獎金", "津貼"
            ]
            
            # 過濾出資料庫中實際存在的項目作為預設選項
            existing_default_items = [item for item in default_bonus_items if item in item_options]
            
            selected_item_names = st.multiselect(
                "選擇要加總的薪資項目*",
                options=list(item_options.keys()),
                default=existing_default_items,
                help="預設選取所有可能的獎金類項目，您可以自行增減。"
            )
            selected_item_ids = [item_options[name] for name in selected_item_names]
        except Exception as e:
            st.error(f"讀取薪資項目時發生錯誤: {e}")
            selected_item_ids = []

    if st.button("🚀 產生年度報表", type="primary"):
        if not selected_item_ids:
            st.warning("請至少選擇一個薪資項目！")
        else:
            with st.spinner("正在彙總整年度資料..."):
                # 呼叫新的報表邏輯函式
                summary_df = logic_report.generate_nhi_accountant_summary(conn, year, selected_item_ids)
                st.session_state.nhi_accountant_summary_df = summary_df

    if 'nhi_accountant_summary_df' in st.session_state:
        st.write("---")
        st.subheader(f"{year} 年度報表預覽")
        display_df = st.session_state.nhi_accountant_summary_df
        
        if display_df.empty:
            st.info(f"在 {year} 年度中查無所選薪資項目的紀錄。")
        else:
            st.dataframe(display_df, width='stretch')
            csv = display_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載CSV報表",
                data=csv,
                file_name=f"nhi_accountant_summary_{year}.csv",
                mime="text/csv",
            )