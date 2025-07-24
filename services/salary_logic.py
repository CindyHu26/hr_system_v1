# services/salary_logic.py
import pandas as pd
import config
from datetime import datetime # 【新增】導入 datetime
# 修正 import 路徑，導入所有需要的模組
from db import queries_employee as q_emp
from db import queries_attendance as q_att
# 【修改】導入 queries_salary_base 以取代舊的 q_items
from db import queries_salary_base as q_base
from db import queries_salary_records as q_records
from db import queries_insurance as q_ins
from db import queries_bonus as q_bonus
from db import queries_allowances as q_allow # 【新增】導入津貼查詢
from services import overtime_logic

def calculate_salary_df(conn, year, month):
    """
    薪資試算引擎：根據各項資料計算全新的薪資草稿。
    """
    # 【新增】定義稅務計算所需的常數
    MINIMUM_WAGE_2025 = 28590
    TAX_THRESHOLD = MINIMUM_WAGE_2025 * 1.5

    employees = q_emp.get_active_employees_for_month(conn, year, month)
    if not employees:
        return pd.DataFrame(), {}
    
    monthly_attendance = q_att.get_monthly_attendance_summary(conn, year, month)
    # 【修改】從正確的模組取得項目類型
    item_types = pd.read_sql("SELECT name, type FROM salary_item", conn).set_index('name')['type'].to_dict()
    all_salary_data = []

    for emp in employees:
        emp_id, emp_name = emp['id'], emp['name_ch']
        details = {'員工姓名': emp_name, '員工編號': emp['hr_code']}
        
        # 【修改】改用 q_base 模組中的函式
        base_info = q_base.get_employee_base_salary_info(conn, emp_id, year, month)
        base_salary = base_info['base_salary'] if base_info else 0
        insurance_salary = base_info['insurance_salary'] if base_info and base_info['insurance_salary'] else base_salary
        dependents = base_info['dependents'] if base_info else 0
        
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

        for leave_type, hours in q_att.get_employee_leave_summary(conn, emp_id, year, month):
            if hours > 0:
                if leave_type == '事假': details['事假'] = -int(round(hours * hourly_rate))
                elif leave_type == '病假': details['病假'] = -int(round(hours * hourly_rate * 0.5))

        # 【修改】改用 q_allow 模組中的函式
        for item in q_allow.get_employee_recurring_items(conn, emp_id):
            details[item['name']] = details.get(item['name'], 0) + (-abs(item['amount']) if item['type'] == 'deduction' else abs(item['amount']))

        if insurance_salary > 0:
            labor_fee, health_fee = q_ins.get_employee_insurance_fee(conn, insurance_salary)
            total_health_fee = health_fee * (1 + min(dependents, 3))
            details['勞健保'] = -int(labor_fee + total_health_fee)
            
        # --- 【全新功能】非居住者預扣稅款計算 ---
        if emp['nationality'] and emp['nationality'] != 'TW':
            entry_date = datetime.strptime(emp['entry_date'], '%Y-%m-%d').date()
            should_withhold = False
            
            # 規則1: 到職當年，從到職月起算6個月
            if entry_date.year == year:
                if month >= entry_date.month and month < entry_date.month + 6:
                    should_withhold = True
            # 規則2: 到職隔年起，每年1-6月預扣
            elif entry_date.year < year:
                if month >= 1 and month <= 6:
                    should_withhold = True
            
            if should_withhold and insurance_salary > 0:
                tax_rate = 0.0
                if insurance_salary <= TAX_THRESHOLD:
                    tax_rate = 0.06
                else:
                    tax_rate = 0.18
                
                tax_amount = insurance_salary * tax_rate
                details['預扣稅款'] = -int(round(tax_amount))
        # --- 預扣稅款計算結束 ---

        special_ot_pay = overtime_logic.calculate_special_overtime_pay(conn, emp_id, year, month, hourly_rate)
        if special_ot_pay > 0:
            details['津貼加班'] = special_ot_pay

        bonus_result = q_bonus.get_employee_bonus(conn, emp_id, year, month)
        if bonus_result:
            details['業務獎金'] = int(round(bonus_result['bonus_amount']))

        all_salary_data.append(details)

    return pd.DataFrame(all_salary_data).fillna(0), item_types

# --- NEW: 薪資單批次修改 ---
def process_batch_salary_update_excel(conn, year: int, month: int, uploaded_file):
    """
    處理從 Excel 上傳的薪資單批次修改。
    """
    report = {"success": 0, "skipped_emp": [], "skipped_item": [], "no_salary_record": []}
    
    try:
        df = pd.read_excel(uploaded_file)
        if '員工姓名' not in df.columns:
            raise ValueError("Excel 檔案中缺少 '員工姓名' 欄位。")

        # 獲取所有必要的映射表
        emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
        item_map_df = pd.read_sql("SELECT id, name, type FROM salary_item", conn)
        item_map = {row['name']: {'id': row['id'], 'type': row['type']} for _, row in item_map_df.iterrows()}
        
        # 獲取當月所有薪資主紀錄的 ID
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

                # 根據項目類型決定金額正負號
                final_amount = -abs(float(amount)) if item_info['type'] == 'deduction' else abs(float(amount))
                
                # 將準備好的資料加入列表
                data_to_upsert.append((salary_id, item_info['id'], int(final_amount)))

        # 批次執行資料庫操作
        if data_to_upsert:
            report["success"] = q_records.batch_upsert_salary_details(conn, data_to_upsert)
            
        # 清理回報訊息
        report["skipped_emp"] = list(set(report["skipped_emp"]))
        report["skipped_item"] = list(set(report["skipped_item"]))
        return report

    except Exception as e:
        raise e