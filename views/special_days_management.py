# views/special_days_management.py
import streamlit as st
import pandas as pd
from datetime import datetime
from db import queries_common as q_common

def show_page(conn):
    st.header("🌀 特殊日期管理 (不計薪假)")
    # 更新說明文字，使其符合新的自動化邏輯
    st.info("您可以在此設定全公司通用的不計薪日期（例如颱風假）。系統會自動排除職稱為「舍監」的員工，使其正常支薪。")

    try:
        # 簡化查詢，不再需要 JOIN 例外表
        special_days_df = pd.read_sql_query("SELECT id, date, description FROM special_unpaid_days ORDER BY date DESC", conn)
        
        # 將欄位名稱中文化
        display_df = special_days_df.rename(columns={
            'id': '紀錄ID',
            'date': '日期',
            'description': '事由'
        })
        st.dataframe(display_df, width='stretch')

    except Exception as e:
        st.error(f"讀取特殊日期時發生錯誤: {e}")
        special_days_df = pd.DataFrame()

    st.markdown("---")
    
    # 簡化頁籤，移除管理例外人員的功能
    tab1, tab2 = st.tabs([" ✨ 新增特殊日期", "🗑️ 刪除特殊日期"])

    with tab1:
        st.subheader("新增不計薪日期")
        with st.form("add_special_day", clear_on_submit=True):
            day = st.date_input("選擇日期*", value=None)
            desc = st.text_input("事由*", placeholder="例如：海葵颱風停止上班")

            if st.form_submit_button("確認新增", type="primary"):
                if not all([day, desc]):
                    st.warning("日期和事由為必填欄位。")
                else:
                    try:
                        q_common.add_record(conn, 'special_unpaid_days', {'date': day, 'description': desc})
                        st.success(f"已成功新增特殊日期：{day} {desc}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗，日期可能已存在: {e}")

    with tab2:
        st.subheader("刪除不計薪日期")
        if not special_days_df.empty:
            day_options = {f"{row['date']} {row['description']}": row['id'] for _, row in special_days_df.iterrows()}
            selected_day_key = st.selectbox("選擇要刪除的日期*", options=day_options.keys(), index=None)

            if st.button("確認刪除", type="primary"):
                if not selected_day_key:
                    st.warning("請選擇一個要刪除的日期。")
                else:
                    day_id = day_options[selected_day_key]
                    q_common.delete_record(conn, 'special_unpaid_days', day_id)
                    st.success("已成功刪除！")
                    st.rerun()
        else:
            st.info("目前沒有可供刪除的日期。")