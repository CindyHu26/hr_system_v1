# app.py
import streamlit as st
from db.db_manager import init_connection
from views import (
    employee_management,
    company_management,
    insurance_history,
    attendance_management,
    special_attendance,
    leave_analysis,
    salary_item_management,
    insurance_grade_management, 
    salary_base_history,
    allowance_setting,          
    bonus_batch,                
    salary_calculation,
    annual_summary,             
    nhi_summary,                
    annual_leave                
)

# --- 頁面設定 ---
st.set_page_config(layout="wide", page_title="輕量人資系統 v1.0")

# --- 資料庫連線 ---
conn = init_connection()
if not conn:
    st.error("資料庫連線失敗，請檢查設定。")
    st.stop()

# --- 頁面路由 ---
PAGES_ADMIN = {
    "👤 員工管理": employee_management,
    "🏢 公司管理": company_management,
    "📄 員工加保管理": insurance_history,
}
PAGES_ATTENDANCE = {
    "📅 出勤紀錄管理": attendance_management,
    "📝 特別出勤管理": special_attendance,
    "🌴 請假與異常分析": leave_analysis,
    "🏖️ 年度特休計算": annual_leave,
}
PAGES_SALARY = {
    "⚙️ 薪資項目管理": salary_item_management,
    "🏦 勞健保級距管理": insurance_grade_management,
    "📈 薪資基準管理": salary_base_history,
    "➕ 員工常態薪資項設定": allowance_setting,
    "🌀 業務獎金批次匯入": bonus_batch,
    "💵 薪資單產生與管理": salary_calculation,
}
PAGES_REPORTING = {
    "📊 年度薪資總表": annual_summary,
    "健保補充保費試算": nhi_summary,
}

ALL_PAGES = {**PAGES_ADMIN, **PAGES_ATTENDANCE, **PAGES_SALARY, **PAGES_REPORTING}

# --- Streamlit 側邊欄 UI ---
st.sidebar.title("HRIS 人資系統 v1.0")

page_groups = {
    "基礎資料管理": list(PAGES_ADMIN.keys()),
    "出勤與假務": list(PAGES_ATTENDANCE.keys()),
    "薪資核心功能": list(PAGES_SALARY.keys()),
    "報表與分析": list(PAGES_REPORTING.keys())
}

selected_group = st.sidebar.selectbox("選擇功能區塊", list(page_groups.keys()))

selected_page_name = st.sidebar.radio(
    f"--- {selected_group} ---",
    page_groups[selected_group],
    label_visibility="collapsed"
)

# 執行選定的頁面
page_to_show = ALL_PAGES.get(selected_page_name)
if page_to_show:
    page_to_show.show_page(conn)
else:
    st.warning(f"頁面「{selected_page_name}」功能似乎未正確對應，請檢查 app.py。")