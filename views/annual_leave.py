# pages/annual_leave.py
import streamlit as st
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

from db import queries_employee as q_emp
from db import queries_attendance as q_att

def calculate_leave_entitlement(years_of_service):
    if years_of_service < 0.5: return 0
    if years_of_service < 1: return 3
    if years_of_service < 2: return 7
    if years_of_service < 3: return 10
    if years_of_service < 5: return 14
    if years_of_service < 10: return 15
    return min(15 + (int(years_of_service) - 9), 30)

def get_annual_leave_summary(conn):
    """
    V4: 新增部門篩選邏輯，只計算 "服務" 或 "行政" 部門的員工。
    """
    employees = q_emp.get_all_employees(conn)
    on_duty_employees = employees[(pd.isnull(employees['resign_date'])) | (employees['resign_date'] == '')].copy()

    if on_duty_employees.empty:
        return pd.DataFrame(), [], []

    today = date.today()
    summaries = []
    skipped_employees = []
    
    # 只篩選出 "服務" 或 "行政" 部門的員工
    eligible_employees = on_duty_employees[on_duty_employees['dept'].isin(['服務', '行政'])]
    # 記錄下所有不符合資格的員工
    ineligible_employees = on_duty_employees[~on_duty_employees['dept'].isin(['服務', '行政'])]['name_ch'].tolist()

    for _, emp in eligible_employees.iterrows():
        if pd.isna(emp['entry_date']) or emp['entry_date'] == '':
            skipped_employees.append(emp['name_ch'])
            continue
            
        entry_date = pd.to_datetime(emp['entry_date']).date()
        total_service = relativedelta(today, entry_date)
        
        if today.month < entry_date.month or (today.month == entry_date.month and today.day < entry_date.day):
            anniversary_year_start = date(today.year - 1, entry_date.month, entry_date.day)
        else:
            anniversary_year_start = date(today.year, entry_date.month, entry_date.day)
        
        anniversary_year_end = anniversary_year_start + relativedelta(years=1) - relativedelta(days=1)
        service_at_anniversary_start = relativedelta(anniversary_year_start, entry_date)
        service_years_at_start = service_at_anniversary_start.years + service_at_anniversary_start.months / 12 + service_at_anniversary_start.days / 365.25
        total_days = calculate_leave_entitlement(service_years_at_start)
        used_hours = q_att.get_leave_hours_for_period(conn, emp['id'], '特休', anniversary_year_start, anniversary_year_end)
        used_days = round(used_hours / 8, 2)
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
    return pd.DataFrame(summaries), skipped_employees, ineligible_employees


def show_page(conn):
    st.header("🏖️ 年度特休計算")
    st.info("系統會根據每位員工的到職日，計算其在當前『週年制』年度的特休天數、已使用天數與剩餘天數。注意：目前只會計算「服務」與「行政」部門的員工。")

    if st.button("重新計算所有員工特休", type="primary"):
        with st.spinner("正在計算中..."):
            summary_df, skipped, ineligible = get_annual_leave_summary(conn)
            st.session_state['annual_leave_summary'] = summary_df
            st.session_state['skipped_employees_annual_leave'] = skipped
            st.session_state['ineligible_employees_annual_leave'] = ineligible
    
    if 'annual_leave_summary' in st.session_state:
        summary_df = st.session_state['annual_leave_summary']
        skipped = st.session_state['skipped_employees_annual_leave']
        ineligible = st.session_state['ineligible_employees_annual_leave']
        
        if skipped:
            st.warning(f"以下 {len(skipped)} 位員工因缺少「到職日」資料而未被計算：{', '.join(skipped)}")
        if ineligible:
            st.info(f"以下 {len(ineligible)} 位非服務/行政部門的員工已被自動排除：{', '.join(ineligible)}")
        
        if not summary_df.empty:
            st.dataframe(summary_df, width='stretch')
            fname = f"annual_leave_summary_{pd.Timestamp.now().strftime('%Y%m%d')}.csv"
            st.download_button(
                "下載總結報告",
                summary_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=fname
            )
        elif not skipped and not ineligible:
            st.info("資料庫中目前沒有符合資格的在職員工可供計算。")