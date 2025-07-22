# app.py
import streamlit as st
from db.db_manager import init_connection
from pages import (
    employee_management, 
    salary_calculation, 
    salary_base_history,
    bonus_batch
)

# --- 頁面設定 ---
st.set_page_config(layout="wide", page_title="輕量人資系統")

# --- 資料庫連線 ---
conn = init_connection()

# --- 頁面路由 ---
PAGES = {
    "👤 員工管理": employee_management,
    "📈 薪資基準管理": salary_base_history,
    "🌀 業務獎金批次匯入": bonus_batch,
    "💵 薪資單產生與管理": salary_calculation,
    # --- 未來可以繼續加入其他頁面 ---
    # "🏢 公司管理": company_management,
    # "📅 出勤紀錄管理": attendance_management,
}

st.sidebar.title("HRIS 導覽")
selection = st.sidebar.radio("前往：", list(PAGES.keys()))

page = PAGES[selection]
page.show_page(conn)
