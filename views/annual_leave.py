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
    # 滿10年後，每多一年加一天，上限30天
    return min(15 + (int(years_of_service) - 9), 30)

def get_annual_leave_summary(conn):
    """
    計算所有在職員工的年度特休天數、已休與剩餘天數。
    V3: 修正對「在職」的判斷邏輯，使其能處理空字串。
    """
    employees = q_emp.get_all_employees(conn)
    
    # [核心修改] 判斷 resign_date 為空值(NULL)或空字串('') 的都算是在職員工
    on_duty_employees = employees[(pd.isnull(employees['resign_date'])) | (employees['resign_date'] == '')].copy()

    if on_duty_employees.empty:
        return pd.DataFrame(), [] # 返回空的 DataFrame 和空的跳過列表

    today = date.today()
    summaries = []
    skipped_employees = [] # 用於記錄被跳過的員工

    for _, emp in on_duty_employees.iterrows():
        if pd.isna(emp['entry_date']) or emp['entry_date'] == '':
            skipped_employees.append(emp['name_ch'])
            continue
            
        entry_date = pd.to_datetime(emp['entry_date']).date()

        # --- 週年計算邏輯 ---
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
    return pd.DataFrame(summaries), skipped_employees


def show_page(conn):
    st.header("🏖️ 年度特休計算")
    st.info("系統會根據每位員工的到職日，計算其在當前『週年制』年度的特休天數、已使用天數與剩餘天數。")

    if st.button("重新計算所有員工特休", type="primary"):
        with st.spinner("正在計算中..."):
            summary_df, skipped_employees = get_annual_leave_summary(conn)
            st.session_state['annual_leave_summary'] = summary_df
            st.session_state['skipped_employees_annual_leave'] = skipped_employees
    
    if 'annual_leave_summary' in st.session_state:
        summary_df = st.session_state['annual_leave_summary']
        skipped_employees = st.session_state['skipped_employees_annual_leave']
        
        if skipped_employees:
            st.warning(f"""
            **注意：** 以下 {len(skipped_employees)} 位在職員工因缺少「到職日」資料而未被計算，請至「員工管理」頁面補全：
            - {', '.join(skipped_employees)}
            """)
        
        if not summary_df.empty:
            st.dataframe(summary_df, use_container_width=True)
            
            fname = f"annual_leave_summary_{pd.Timestamp.now().strftime('%Y%m%d')}.csv"
            st.download_button(
                "下載總結報告",
                summary_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=fname
            )
        elif not skipped_employees:
            st.info("資料庫中目前沒有在職員工可供計算。")