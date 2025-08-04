# app.py
import os
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from db.db_manager import init_connection
from views import (
    config_management,
    employee_management,
    company_management,
    insurance_history,
    attendance_management,
    special_attendance,
    leave_analysis,
    leave_history,
    special_days_management,
    salary_item_management,
    insurance_grade_management,
    salary_base_history,
    loan_management,
    allowance_setting,
    bonus_batch,
    performance_bonus,
    salary_calculation,
    annual_summary,
    nhi_summary,
    annual_leave,
    attendance_report,
    bank_transfer_report,
    salary_report
)

# --- 頁面設定 ---
st.set_page_config(layout="wide", page_title="人資系統 v1.0")

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
    "🌀 特殊日期管理": special_days_management,
    "🌴 請假與異常分析": leave_analysis,
    "📖 請假紀錄總覽": leave_history,
    "🏖️ 年度特休計算": annual_leave,
}
PAGES_SALARY = {
    "1️⃣ 薪資基準與保費管理": salary_base_history,
    "2️⃣ 績效獎金計算": performance_bonus,
    "3️⃣ 業務獎金批次匯入": bonus_batch,
    "4️⃣ 借支管理": loan_management,
    "5️⃣ 薪資單產生與鎖定": salary_calculation, 
    "➕ 員工常態薪資項設定": allowance_setting,
    "🏦 勞健保級距管理": insurance_grade_management,
    "🔧 系統參數設定": config_management,
    "⚙️ 薪資項目管理": salary_item_management,
}

PAGES_REPORTING = {
    "📅 出勤日報表匯出": attendance_report,
    "💵 薪資月報與薪資單": salary_report,
    "🏦 銀行薪轉檔產製": bank_transfer_report,
    "📊 年度薪資總表": annual_summary,
    "📈 健保補充保費試算": nhi_summary
}

ALL_PAGES = {**PAGES_ADMIN, **PAGES_ATTENDANCE, **PAGES_SALARY, **PAGES_REPORTING}

# --- Streamlit 側邊欄 UI ---
st.sidebar.title("HRIS 人資系統 v1.0")

page_groups = {
    "基本資料管理": list(PAGES_ADMIN.keys()),
    "出勤與假務": list(PAGES_ATTENDANCE.keys()),
    "薪資核心功能": list(PAGES_SALARY.keys()),
    "報表與分析": list(PAGES_REPORTING.keys())
}

selected_group = st.sidebar.selectbox("選擇功能區塊", list(page_groups.keys()))

page_list = page_groups[selected_group]

selected_page_name = st.sidebar.radio(
    f"--- {selected_group} ---",
    page_list,
    label_visibility="collapsed"
)

# 執行選定的頁面
page_to_show = ALL_PAGES.get(selected_page_name)
if page_to_show:
    page_to_show.show_page(conn)
else:
    st.warning(f"頁面「{selected_page_name}」功能似乎未正確對應，請檢查 app.py。")