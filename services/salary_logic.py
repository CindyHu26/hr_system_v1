# services/salary_logic.py
import pandas as pd
import config
from db import queries as q
from services import overtime_logic

def calculate_salary_df(conn, year, month):
    """
    薪資試算引擎：根據各項資料計算全新的薪資草稿。
    """
    employees_df = q.get_active_employees_for_month(conn, year, month)
    if employees_df.empty:
        return pd.DataFrame(), {}
    
    monthly_attendance = q.get_monthly_attendance_summary(conn, year, month)
    item_types = q.get_item_types(conn)
    all_salary_data = []

    for emp in employees_df:
        emp_id, emp_name = emp['id'], emp['name_ch']
        details = {'員工姓名': emp_name, '員工編號': emp['hr_code']}
        
        base_info = q.get_employee_base_salary_info(conn, emp_id, year, month)
        base_salary = base_info['base_salary'] if base_info else 0
        insurance_salary = base_info['insurance_salary'] if base_info and base_info['insurance_salary'] else base_salary
        dependents = base_info['dependents'] if base_info else 0.0
        
        hourly_rate = base_salary / config.HOURLY_RATE_DIVISOR if config.HOURLY_RATE_DIVISOR > 0 else 0
        details['底薪'] = base_salary
        
        if emp_id in monthly_attendance.index:
            emp_att = monthly_attendance.loc[emp_id]
            if emp_att.get('late_minutes', 0) > 0:
                details['遲到'] = -int(round((emp_att['late_minutes'] / 60) * hourly_rate))
            if emp_att.get('early_leave_minutes', 0) > 0:
                details['早退'] = -int(round((emp_att['early_leave_minutes'] / 60) * hourly_rate))
            if emp_att.get('overtime1_minutes', 0) > 0:
                details['加班費(平日)'] = int(round((emp_att['overtime1_minutes'] / 60) * hourly_rate * 1.34))
            if emp_att.get('overtime2_minutes', 0) > 0:
                details['加班費(假日)'] = int(round((emp_att['overtime2_minutes'] / 60) * hourly_rate * 1.67))

        for leave_type, hours in q.get_employee_leave_summary(conn, emp_id, year, month):
            if hours > 0:
                if leave_type == '事假': details['事假'] = -int(round(hours * hourly_rate))
                elif leave_type == '病假': details['病假'] = -int(round(hours * hourly_rate * 0.5))

        for item in q.get_employee_recurring_items(conn, emp_id):
            details[item['name']] = details.get(item['name'], 0) + (-abs(item['amount']) if item['type'] == 'deduction' else abs(item['amount']))

        if insurance_salary > 0:
            labor_fee, health_fee = q.get_employee_insurance_fee(conn, insurance_salary)
            total_health_fee = health_fee * (1 + min(dependents, 3))
            details['勞健保'] = -int(labor_fee + total_health_fee)
            
        special_ot_pay = overtime_logic.calculate_special_overtime_pay(conn, emp_id, year, month, hourly_rate)
        if special_ot_pay > 0:
            details['津貼加班'] = special_ot_pay

        bonus_result = q.get_employee_bonus(conn, emp_id, year, month)
        if bonus_result:
            details['業務獎金'] = int(round(bonus_result['bonus_amount']))

        all_salary_data.append(details)

    return pd.DataFrame(all_salary_data).fillna(0), item_types
