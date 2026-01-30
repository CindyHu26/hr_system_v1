# pages/annual_leave.py
import streamlit as st
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

from db import queries_employee as q_emp
from db import queries_attendance as q_att
from services import leave_logic

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
    st.title("🏖️ 特休管理與試算")
    leave_logic = leave_logic(conn) # 假設您的初始化方式
    employee_logic = q_emp(conn)
    # 建立分頁
    tab1, tab2 = st.tabs(["📅 當年度特休試算", "📜 歷年特休結算總覽"])
    with tab1:
        st.header("📅 當年度特休試算")
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
    with tab2:
        st.header("📜 歷年特休結算總覽")
        st.info("此功能用於查看員工過去每一年的特休使用狀況，方便計算未休完的代金。")
        
        # 1. 選擇員工
        employees = employee_logic.get_all_employees()
        emp_options = {f"{emp['employee_id']} - {emp['name']}": emp for emp in employees}
        selected_emp_key = st.selectbox("選擇員工", list(emp_options.keys()), key="histemp_select")
        
        if selected_emp_key:
            selected_emp = emp_options[selected_emp_key]
            hire_date = selected_emp.get('hire_date')
            
            if hire_date:
                st.write(f"**到職日**: {hire_date}")
                
                # 2. 呼叫邏輯計算歷史
                history_data = leave_logic.get_employee_annual_leave_history(
                    selected_emp['employee_id'], 
                    hire_date
                )
                
                if history_data:
                    df_history = pd.DataFrame(history_data)
                    
                    # 格式化顯示
                    df_history['週期開始'] = pd.to_datetime(df_history['週期開始']).dt.strftime('%Y-%m-%d')
                    df_history['週期結束'] = pd.to_datetime(df_history['週期結束']).dt.strftime('%Y-%m-%d')
                    
                    # 針對"剩餘天數"欄位做顏色標示 (大於0且已過期的顯示紅色，代表要發錢)
                    def highlight_settlement(row):
                        if row['狀態'] == "過期 (可結算)" and row['剩餘天數'] > 0:
                            return ['background-color: #ffcccc'] * len(row)
                        elif row['狀態'] == "進行中 (目前年度)":
                            return ['background-color: #e6f3ff'] * len(row)
                        return [''] * len(row)

                    st.dataframe(
                        df_history.style.apply(highlight_settlement, axis=1).format({
                            "特休總額": "{:.1f}", 
                            "已休天數": "{:.1f}", 
                            "剩餘天數": "{:.1f}"
                        }),
                        use_container_width=True
                    )
                    
                    st.warning("⚠️ 注意：『過期 (可結算)』且剩餘天數 > 0 的項目，應於年度終結時折發工資。")
                    
                else:
                    st.write("尚無特休歷史資料 (可能年資未滿半年)")
            else:
                st.error("該員工無到職日資料，無法計算。")