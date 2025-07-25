# services/salary_logic.py
import pandas as pd
import config
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from db import queries_employee as q_emp
from db import queries_attendance as q_att

from db import queries_salary_base as q_base
from db import queries_salary_records as q_records
from db import queries_insurance as q_ins
from db import queries_bonus as q_bonus
from db import queries_allowances as q_allow 
from services import overtime_logic
from views.annual_leave import calculate_leave_entitlement 

def calculate_salary_df(conn, year, month):
    """
    薪資試算引擎：根據各項資料計算全新的薪資草稿。
    V7: 導入符合法規的個人二代健保補充保費計算邏輯
    """
    TAX_THRESHOLD = config.MINIMUM_WAGE * config.FOREIGNER_TAX_RATE_THRESHOLD_MULTIPLIER

    employees = q_emp.get_active_employees_for_month(conn, year, month)
    if not employees:
        return pd.DataFrame(), {}
    
    monthly_attendance = q_att.get_monthly_attendance_summary(conn, year, month)
    item_types = pd.read_sql("SELECT name, type FROM salary_item", conn).set_index('name')['type'].to_dict()
    all_salary_data = []

    for emp in employees:
        emp_id, emp_name = emp['id'], emp['name_ch']
        details = {'員工姓名': emp_name, '員工編號': emp['hr_code']}
        
        base_info = q_base.get_employee_base_salary_info(conn, emp_id, year, month)
        base_salary = base_info['base_salary'] if base_info else 0
        insurance_salary = base_info['insurance_salary'] if base_info and base_info['insurance_salary'] else base_salary
        dependents = base_info['dependents'] if base_info else 0
        
        hourly_rate = base_salary / config.HOURLY_RATE_DIVISOR if config.HOURLY_RATE_DIVISOR > 0 else 0
        details['底薪'] = base_salary
        
        entry_date_str = emp['entry_date']
        if pd.notna(entry_date_str):
            entry_date = pd.to_datetime(entry_date_str).date()
            if entry_date.month == month:
                last_anniversary_year_start = date(year - 1, entry_date.month, entry_date.day)
                last_anniversary_year_end = last_anniversary_year_start + relativedelta(years=1) - relativedelta(days=1)
                service_at_start = relativedelta(last_anniversary_year_start, entry_date)
                service_years = service_at_start.years + service_at_start.months / 12 + service_at_start.days / 365.25
                total_entitled_days = calculate_leave_entitlement(service_years)
                used_hours = q_att.get_leave_hours_for_period(conn, emp_id, '特休', last_anniversary_year_start, last_anniversary_year_end)
                used_days = round(used_hours / 8, 2)
                unused_days = total_entitled_days - used_days
                if unused_days > 0:
                    daily_wage = round(base_salary / 30)
                    payout_amount = int(round(unused_days * daily_wage))
                    details['特休未休'] = payout_amount

        if emp_id in monthly_attendance.index:
            emp_att = monthly_attendance.loc[emp_id]
            if emp_att.get('late_minutes', 0) > 0: details['遲到'] = -int(round((emp_att['late_minutes'] / 60) * hourly_rate))
            if emp_att.get('early_leave_minutes', 0) > 0: details['早退'] = -int(round((emp_att['early_leave_minutes'] / 60) * hourly_rate))
            if emp_att.get('overtime1_minutes', 0) > 0: details['加班費(延長工時)'] = int(round((emp_att['overtime1_minutes'] / 60) * hourly_rate * 1.34))
            re_extended_minutes = emp_att.get('overtime2_minutes', 0) + emp_att.get('overtime3_minutes', 0)
            if re_extended_minutes > 0: details['加班費(再延長工時)'] = int(round((re_extended_minutes / 60) * hourly_rate * 1.67))

        for leave_type, hours in q_att.get_employee_leave_summary(conn, emp_id, year, month):
            if hours > 0:
                if leave_type == '事假': details['事假'] = -int(round(hours * hourly_rate))
                elif leave_type == '病假': details['病假'] = -int(round(hours * hourly_rate * 0.5))

        for item in q_allow.get_employee_recurring_items(conn, emp_id):
            details[item['name']] = details.get(item['name'], 0) + (-abs(item['amount']) if item['type'] == 'deduction' else abs(item['amount']))

        if insurance_salary > 0:
            labor_fee, health_fee = q_ins.get_employee_insurance_fee(conn, insurance_salary)
            total_health_fee = health_fee * (1 + min(dependents, 3))
            details['勞健保'] = -int(labor_fee + total_health_fee)
            
        if emp['nationality'] and emp['nationality'] != 'TW':
            entry_date = datetime.strptime(emp['entry_date'], '%Y-%m-%d').date()
            should_withhold = (entry_date.year == year and entry_date.month <= month < entry_date.month + 6) or \
                              (entry_date.year < year and 1 <= month <= 6)
            if should_withhold and insurance_salary > 0:
                tax_rate = config.FOREIGNER_LOW_INCOME_TAX_RATE if insurance_salary <= TAX_THRESHOLD else config.FOREIGNER_HIGH_INCOME_TAX_RATE
                details['稅款'] = -int(round(insurance_salary * tax_rate))

        special_ot_pay = overtime_logic.calculate_special_overtime_pay(conn, emp_id, year, month, hourly_rate)
        if special_ot_pay > 0: details['津貼加班'] = special_ot_pay

        bonus_result = q_bonus.get_employee_bonus(conn, emp_id, year, month)
        if bonus_result: details['業務獎金'] = int(round(bonus_result['bonus_amount']))

        # --- [核心修改] 二代健保補充保費計算 (個人高額獎金) ---
        is_insured = q_ins.is_employee_insured_in_month(conn, emp_id, year, month)
        if is_insured:
            # 1. 計算當月發放的獎金總額
            current_month_bonus = sum(details.get(item, 0) for item in config.NHI_BONUS_ITEMS)
            
            # 2. 只有當月有發放獎金時，才需要重算
            if current_month_bonus > 0:
                # 3. 查詢年度累計獎金 和 已扣補充保費
                cumulative_bonus, already_deducted = q_records.get_cumulative_bonus_for_year(conn, emp_id, year, config.NHI_BONUS_ITEMS)
                total_cumulative_bonus = cumulative_bonus + current_month_bonus

                # 4. 計算免扣額
                deduction_threshold = insurance_salary * config.NHI_BONUS_MULTIPLIER
                
                # 5. 計算應扣總額
                taxable_bonus = total_cumulative_bonus - deduction_threshold
                if taxable_bonus > 0:
                    total_premium_due = round(taxable_bonus * config.NHI_SUPPLEMENT_RATE)
                    # 6. 本月應扣 = 應扣總額 - 已扣總額
                    this_month_premium = total_premium_due - already_deducted
                    if this_month_premium > 0:
                        details['二代健保補充費'] = -int(this_month_premium)
        # --- 計算結束 ---

        all_salary_data.append(details)

    return pd.DataFrame(all_salary_data).fillna(0), item_types

def process_batch_salary_update_excel(conn, year: int, month: int, uploaded_file):
    report = {"success": 0, "skipped_emp": [], "skipped_item": [], "no_salary_record": []}
    
    try:
        df = pd.read_excel(uploaded_file)
        if '員工姓名' not in df.columns:
            raise ValueError("Excel 檔案中缺少 '員工姓名' 欄位。")

        emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
        item_map_df = pd.read_sql("SELECT id, name, type FROM salary_item", conn)
        item_map = {row['name']: {'id': row['id'], 'type': row['type']} for _, row in item_map_df.iterrows()}
        
        salary_main_df = pd.read_sql("SELECT id, employee_id FROM salary WHERE year = ? AND month = ?", conn, params=(year, month))
        salary_id_map = salary_main_df.set_index('employee_id')['id'].to_dict()

        data_to_upsert = []

        for _, row in df.iterrows():
            emp_name = row.get('員工姓名')
            if pd.isna(emp_name): continue

            emp_id = emp_map.get(emp_name)
            if not emp_id:
                report["skipped_emp"].append(emp_name)
                continue

            salary_id = salary_id_map.get(emp_id)
            if not salary_id:
                report["no_salary_record"].append(emp_name)
                continue

            for item_name, amount in row.items():
                if item_name == '員工姓名' or pd.isna(amount): continue
                
                item_info = item_map.get(item_name)
                if not item_info:
                    report["skipped_item"].append(item_name)
                    continue

                final_amount = -abs(float(amount)) if item_info['type'] == 'deduction' else abs(float(amount))
                
                data_to_upsert.append((salary_id, item_info['id'], int(final_amount)))

        if data_to_upsert:
            report["success"] = q_records.batch_upsert_salary_details(conn, data_to_upsert)
            
        report["skipped_emp"] = list(set(report["skipped_emp"]))
        report["skipped_item"] = list(set(report["skipped_item"]))
        return report

    except Exception as e:
        raise e