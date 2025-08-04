# services/salary_logic.py
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import os
import math

from db import queries_employee as q_emp
from db import queries_attendance as q_att
from db import queries_salary_base as q_base
from db import queries_salary_read as q_read
from db import queries_salary_write as q_write
from db import queries_insurance as q_ins
from db import queries_bonus as q_bonus
from db import queries_performance_bonus as q_perf
from db import queries_loan as q_loan
from db import queries_allowances as q_allow
from db import queries_config as q_config
from services import overtime_logic
from views.annual_leave import calculate_leave_entitlement

def calculate_single_employee_insurance(conn, insurance_salary, dependents_under_18, dependents_over_18, nhi_status, nhi_status_expiry, year, month):
    # 此函式維持不變
    if not insurance_salary or insurance_salary <= 0: return 0, 0
    labor_fee, health_fee_base = q_ins.get_employee_insurance_fee(conn, insurance_salary, year, month)
    total_health_fee = 0
    d_under_18 = float(dependents_under_18 or 0)
    d_over_18 = float(dependents_over_18 or 0)
    expiry_date = pd.to_datetime(nhi_status_expiry, errors='coerce').date() if pd.notna(nhi_status_expiry) else None
    is_expired = expiry_date < date(year, month, 1) if expiry_date else False

    if nhi_status == '自理':
        total_health_fee = 0
    elif nhi_status == '低收入戶' and not is_expired:
        total_health_fee = health_fee_base * (0.5 + (d_over_18 * 0.5))
    else:
        total_dependents_count = d_under_18 + d_over_18
        health_ins_count = min(3, total_dependents_count)
        total_health_fee = health_fee_base * (1 + health_ins_count)
    return int(round(labor_fee)), int(round(total_health_fee))

def calculate_salary_df(conn, year, month):
    """
    薪資試算引擎 V35:
    - 呼叫 V2 版本的 get_employee_recurring_items
    - 整合協理計算邏輯
    - 修正單次津貼的累加邏輯
    """
    db_configs = q_config.get_all_configs(conn)
    MINIMUM_WAGE_OF_YEAR = q_config.get_minimum_wage_for_year(conn, year)
    if MINIMUM_WAGE_OF_YEAR == 0:
        raise ValueError(f"錯誤：找不到 {year} 年的基本工資設定，請至「系統參數設定」頁面新增。")
    
    HOURLY_RATE_DIVISOR = float(db_configs.get('HOURLY_RATE_DIVISOR', '240.0'))
    NHI_SUPPLEMENT_RATE = float(db_configs.get('NHI_SUPPLEMENT_RATE', '0.0211'))
    NHI_BONUS_MULTIPLIER = int(float(db_configs.get('NHI_BONUS_MULTIPLIER', '4')))
    NHI_BONUS_ITEMS = [item.strip() for item in db_configs.get('NHI_BONUS_ITEMS', '').split(',')]
    FOREIGNER_MULTIPLIER = float(db_configs.get('FOREIGNER_TAX_RATE_THRESHOLD_MULTIPLIER', '1.5'))
    FOREIGNER_LOW_RATE = float(db_configs.get('FOREIGNER_LOW_INCOME_TAX_RATE', '0.06'))
    FOREIGNER_HIGH_RATE = float(db_configs.get('FOREIGNER_HIGH_INCOME_TAX_RATE', '0.18'))
    TAX_THRESHOLD = MINIMUM_WAGE_OF_YEAR * FOREIGNER_MULTIPLIER
    
    employees = q_emp.get_active_employees_for_month(conn, year, month)
    if not employees: return pd.DataFrame(), {}
    
    monthly_attendance = q_att.get_monthly_attendance_summary(conn, year, month)
    item_types = pd.read_sql("SELECT name, type FROM salary_item", conn).set_index('name')['type'].to_dict()
    
    all_salary_data = []

    for emp in employees:
        emp_id, emp_name = emp['id'], emp['name_ch']
        details = {'employee_id': emp_id, '員工姓名': emp_name, '員工編號': emp['hr_code']}
        base_info = q_base.get_employee_base_salary_info(conn, emp_id, year, month)
        if not base_info: continue

        base_salary = base_info['base_salary']
        details['底薪'] = int(round(base_salary))
        
        if emp['title'] != '協理':
            insurance_salary = base_info['insurance_salary'] or base_salary
            hourly_rate = base_salary / HOURLY_RATE_DIVISOR if HOURLY_RATE_DIVISOR > 0 else 0

            # --- 計算邏輯 ---
            # 1. 常態薪資項目
            # 【核心修正】呼叫更新後的函式
            for item in q_allow.get_employee_recurring_items(conn, emp_id, year, month):
                details[item['name']] = -abs(item['amount']) if item['type'] == 'deduction' else abs(item['amount'])

            # 2. 其他計算項目
            if emp['dept'] in ['服務', '行政']:
                entry_date_str = emp['entry_date']
                if pd.notna(entry_date_str):
                    entry_date = pd.to_datetime(entry_date_str).date()
                    if entry_date.month == month:
                        last_anniversary_year_start = date(year - 1, entry_date.month, entry_date.day)
                        last_anniversary_year_end = last_anniversary_year_start + relativedelta(years=1) - relativedelta(days=1)
                        service_years = (last_anniversary_year_start - entry_date).days / 365.25
                        total_entitled_days = calculate_leave_entitlement(service_years)
                        used_hours = q_att.get_leave_hours_for_period(conn, emp_id, '特休', last_anniversary_year_start, last_anniversary_year_end)
                        unused_days = total_entitled_days - (used_hours / 8)
                        if unused_days > 0:
                            details['特休未休'] = int(round(unused_days * (base_salary / 30)))

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

            is_insured_in_company = q_ins.is_employee_insured_in_month(conn, emp_id, year, month)

            if is_insured_in_company:
                auto_labor_fee, auto_health_fee = calculate_single_employee_insurance(conn, insurance_salary, base_info['dependents_under_18'], base_info['dependents_over_18'], emp['nhi_status'], emp['nhi_status_expiry'], year, month)
                details['勞保費'] = -int(base_info['labor_insurance_override'] if pd.notna(base_info['labor_insurance_override']) else auto_labor_fee)
                health_override = base_info['health_insurance_override']
                if pd.notna(health_override):
                    manual_health_base = int(health_override)
                    d_under_18 = float(base_info['dependents_under_18'] or 0)
                    d_over_18 = float(base_info['dependents_over_18'] or 0)
                    health_ins_count = min(3, d_under_18 + d_over_18)
                    final_health_fee = int(round(manual_health_base * (1 + health_ins_count)))
                    if emp['nhi_status'] == '自理': final_health_fee = 0
                    details['健保費'] = -final_health_fee
                else:
                    details['健保費'] = -auto_health_fee
                details['勞退提撥'] = int(base_info['pension_override'] if pd.notna(base_info['pension_override']) else round(insurance_salary * 0.06))
            
            if emp['nationality'] and emp['nationality'] != 'TW' and pd.notna(emp['entry_date']):
                entry_date = pd.to_datetime(emp['entry_date']).date()
                should_withhold = (year == entry_date.year and (entry_date.month >= 7 or month < entry_date.month + 6)) or \
                                  (year == entry_date.year + 1 and month <= 6)
                if should_withhold and insurance_salary > 0:
                    tax_rate = FOREIGNER_LOW_RATE if base_salary <= TAX_THRESHOLD else FOREIGNER_HIGH_RATE
                    details['稅款'] = -int(round(insurance_salary * tax_rate))
            
            special_ot_pay = overtime_logic.calculate_special_overtime_pay(conn, emp_id, year, month, hourly_rate)
            if special_ot_pay > 0: details['津貼加班'] = details.get('津貼加班', 0) + special_ot_pay
            
            loan_amount = q_loan.get_employee_loan(conn, emp_id, year, month)
            if loan_amount > 0: details['借支'] = -int(loan_amount)
            
            bonus_result = q_bonus.get_employee_bonus(conn, emp_id, year, month)
            if bonus_result: details['業務獎金'] = int(round(bonus_result['bonus_amount']))
            
            perf_bonus_result = q_perf.get_performance_bonus(conn, emp_id, year, month)
            if perf_bonus_result: details['績效獎金'] = int(round(perf_bonus_result))
            
            if is_insured_in_company:
                period_to_check = None
                if month == 6: period_to_check = {"start": 1, "end": 5, "year": year}
                elif month == 11: period_to_check = {"start": 6, "end": 10, "year": year}
                elif month == 1: period_to_check = {"start": 11, "end": 12, "year": year - 1}

                if period_to_check:
                    p_year, p_start, p_end = period_to_check["year"], period_to_check["start"], period_to_check["end"]
                    period_bonus, already_deducted = q_read.get_cumulative_bonus_for_period(conn, emp_id, p_year, p_start, p_end, NHI_BONUS_ITEMS)
                    if period_bonus > 0:
                        deduction_threshold = insurance_salary * NHI_BONUS_MULTIPLIER
                        if period_bonus > deduction_threshold:
                            taxable_bonus = period_bonus - deduction_threshold
                            total_premium_due = round(taxable_bonus * NHI_SUPPLEMENT_RATE)
                            this_month_premium = total_premium_due - already_deducted
                            if this_month_premium > 0:
                                details['二代健保(高額獎金)'] = -int(this_month_premium)
            else:
                earning_cols_for_calc = [k for k, t in item_types.items() if t == 'earning']
                total_earnings_for_part_time = sum(details.get(item, 0) for item in earning_cols_for_calc)
                if total_earnings_for_part_time > MINIMUM_WAGE_OF_YEAR:
                    part_time_premium = math.ceil(total_earnings_for_part_time * NHI_SUPPLEMENT_RATE)
                    if part_time_premium > 0: details['二代健保(兼職)'] = -int(part_time_premium)
            
            unpaid_days_df = pd.read_sql_query(f"SELECT date FROM special_unpaid_days WHERE strftime('%Y-%m', date) = '{year}-{month:02d}'", conn)
            unpaid_dates = set(pd.to_datetime(unpaid_days_df['date']).dt.date)

            if emp['title'] != '舍監' and len(unpaid_dates) > 0:
                unpaid_deduction = round(base_salary / 30) * len(unpaid_dates)
                if (base_salary - unpaid_deduction) < MINIMUM_WAGE_OF_YEAR:
                    details['底薪'] = int(round(MINIMUM_WAGE_OF_YEAR))
                else:
                    details['底薪'] -= int(round(unpaid_deduction))
        
        temp_df = pd.DataFrame([details])
        current_item_types = {**item_types, '勞保費': 'deduction', '健保費': 'deduction'}
        
        earning_cols = [c for c, t in current_item_types.items() if t == 'earning' and c in temp_df.columns]
        deduction_cols = [c for c, t in current_item_types.items() if t == 'deduction' and c in temp_df.columns]
        
        total_payable = temp_df[earning_cols].sum(axis=1, numeric_only=True).iloc[0]
        total_deduction = temp_df[deduction_cols].sum(axis=1, numeric_only=True).iloc[0]
        net_salary = total_payable + total_deduction
        
        bank_transfer_items = ['底薪', '加班費(延長工時)', '加班費(再延長工時)', '勞保費', '健保費', '事假', '病假', '遲到', '早退']
        existing_bank_items = [item for item in bank_transfer_items if item in temp_df.columns]
        
        bank_transfer_amount = 0
        if existing_bank_items:
            bank_transfer_amount = temp_df[existing_bank_items].sum(axis=1).iloc[0]
        cash_amount = net_salary - bank_transfer_amount

        details['應付總額'] = int(round(total_payable))
        details['應扣總額'] = int(round(total_deduction))
        details['實支金額'] = int(round(net_salary))
        details['匯入銀行'] = int(round(bank_transfer_amount))
        details['現金'] = int(round(cash_amount))
        
        all_salary_data.append(details)

    final_df = pd.DataFrame(all_salary_data).fillna(0)
    if not final_df.empty:
        final_df['status'] = 'draft'
        final_df['勞健保'] = pd.to_numeric(final_df.get('勞保費', 0), errors='coerce').fillna(0) + pd.to_numeric(final_df.get('健保費', 0), errors='coerce').fillna(0)
        
        report_template, _ = q_read.get_salary_report_for_editing(conn, 2000, 1)
        final_cols = report_template.columns.tolist()

        for col in final_cols:
            if col not in final_df.columns:
                final_df[col] = 0 if col not in ['status', '備註', '員工姓名', '員工編號'] else ''
        
        for col in final_df.columns:
            if col in report_template.columns and report_template[col].dtype != final_df[col].dtype:
                if pd.api.types.is_numeric_dtype(report_template[col]):
                    final_df[col] = pd.to_numeric(final_df[col], errors='coerce').fillna(0)
        
        return final_df[final_cols], item_types

    return pd.DataFrame(), item_types

def process_batch_salary_update_excel(conn, year: int, month: int, uploaded_file):
    report = {"success": 0, "skipped_emp": [], "skipped_item": [], "no_salary_record": []}
    try:
        df = pd.read_excel(uploaded_file)
        if '員工姓名' not in df.columns: raise ValueError("Excel 檔案中缺少 '員工姓名' 欄位。")
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
        if data_to_upsert: report["success"] = q_write.batch_upsert_salary_details(conn, data_to_upsert)
        report["skipped_emp"] = list(set(report["skipped_emp"]))
        report["skipped_item"] = list(set(report["skipped_item"]))
        return report
    except Exception as e:
        raise e