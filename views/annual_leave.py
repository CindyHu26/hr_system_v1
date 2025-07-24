# pages/annual_leave.py
import streamlit as st
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

# 導入新架構的模組
from db import queries_employee as q_emp
from db import queries_attendance as q_att

def calculate_leave_entitlement(years_of_service):
    """根據年資計算特休天數"""
    if years_of_service < 0.5: return 0
    if years_of_service < 1: return 3
    if years_of_service < 2: return 7
    if years_of_service < 3: return 10
    if years_of_service < 5: return 14
    if years_of_service < 10: return 15
    return min(15 + int(years_of_service) - 9, 30)

def get_annual_leave_summary(conn):
    """計算所有在職員工的年度特休天數、已休與剩餘天數"""
    employees = q_emp.get_all_employees(conn)
    on_duty_employees = employees[pd.isnull(employees['resign_date'])].copy()

    if on_duty_employees.empty:
        return pd.DataFrame()

    today = date.today()
    summaries = []

    for _, emp in on_duty_employees.iterrows():
        entry_date = pd.to_datetime(emp['entry_date']).date()
        if pd.isna(entry_date): continue

        # 計算完整年資
        total_service = relativedelta(today, entry_date)
        years_of_service = total_service.years + total_service.months / 12 + total_service.days / 365.25

        # 計算週年制年度區間
        anniversary_year_start = date(today.year, entry_date.month, entry_date.day)
        if anniversary_year_start > today:
            anniversary_year_start = date(today.year - 1, entry_date.month, entry_date.day)
        anniversary_year_end = date(anniversary_year_start.year + 1, anniversary_year_start.month, anniversary_year_start.day) - relativedelta(days=1)

        # 查詢此週年區間內的特休時數
        sql = "SELECT SUM(duration) FROM leave_record WHERE employee_id = ? AND leave_type = '特休' AND status = '已通過' AND start_date BETWEEN ? AND ?"
        used_hours_tuple = conn.execute(sql, (emp['id'], anniversary_year_start, anniversary_year_end)).fetchone()
        used_hours = used_hours_tuple[0] if used_hours_tuple and used_hours_tuple[0] else 0
        used_days = round(used_hours / 8, 2)

        # 計算應有特休
        service_at_anniversary_start = relativedelta(anniversary_year_start, entry_date)
        service_years_at_start = service_at_anniversary_start.years + service_at_anniversary_start.months / 12
        total_days = calculate_leave_entitlement(service_years_at_start)
        
        remaining_days = total_days - used_days

        summaries.append({
            '員工編號': emp['hr_code'],
            '員工姓名': emp['name_ch'],
            '到職日': entry_date.strftime('%Y-%m-%d'),
            '年資': f"{total_service.years}年 {total_service.months}月",
            '本期特休年度': f"{anniversary_year_start} ~ {anniversary_year_end}",
            '本期應有特休天數': total_days,
            '本期已休特休天數': used_days,
            '本期剩餘特休天數': remaining_days
        })
    return pd.DataFrame(summaries)


def show_page(conn):
    st.header("🏖️ 年度特休計算")
    st.info("系統會根據每位員工的到職日，計算其在當前『週年制』年度的特休天數、已使用天數與剩餘天數。")

    if st.button("重新計算所有員工特休", type="primary"):
        with st.spinner("正在計算中..."):
            summary_df = get_annual_leave_summary(conn)
            st.session_state['annual_leave_summary'] = summary_df
    
    if 'annual_leave_summary' in st.session_state:
        st.dataframe(st.session_state['annual_leave_summary'], use_container_width=True)
        
        fname = f"annual_leave_summary_{pd.Timestamp.now().strftime('%Y%m%d')}.csv"
        st.download_button(
            "下載總結報告",
            st.session_state['annual_leave_summary'].to_csv(index=False).encode("utf-8-sig"),
            file_name=fname
        )