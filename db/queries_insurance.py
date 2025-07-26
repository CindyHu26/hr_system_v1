# db/queries_insurance.py
"""
資料庫查詢：專門處理「保險(insurance)」相關的資料庫操作。
包含：員工加退保歷史、勞健保級距表管理。
"""
import pandas as pd
from utils.helpers import get_monthly_dates

# --- Employee Insurance History ---

def get_all_insurance_history(conn):
    """取得所有員工的加退保歷史紀錄。"""
    query = """
    SELECT ech.id, e.name_ch, c.name as company_name,
           ech.start_date, ech.end_date, ech.note
    FROM employee_company_history ech
    JOIN employee e ON ech.employee_id = e.id
    JOIN company c ON ech.company_id = c.id
    ORDER BY e.hr_code, ech.start_date DESC
    """
    return pd.read_sql_query(query, conn)

def get_employee_insurance_fee(conn, insurance_salary):
    """根據投保薪資查詢員工應負擔的勞健保費用。"""
    if not insurance_salary or insurance_salary <= 0:
        return 0, 0
        
    sql_labor = "SELECT employee_fee FROM insurance_grade WHERE type = 'labor' AND ? BETWEEN salary_min AND salary_max ORDER BY start_date DESC LIMIT 1"
    labor_fee_row = conn.execute(sql_labor, (insurance_salary,)).fetchone()
    
    sql_health = "SELECT employee_fee FROM insurance_grade WHERE type = 'health' AND ? BETWEEN salary_min AND salary_max ORDER BY start_date DESC LIMIT 1"
    health_fee_row = conn.execute(sql_health, (insurance_salary,)).fetchone()
    
    labor_fee = labor_fee_row[0] if labor_fee_row else 0
    health_fee = health_fee_row[0] if health_fee_row else 0
    
    return labor_fee, health_fee

def get_insurance_grades(conn):
    """取得所有勞健保級距資料。"""
    return pd.read_sql_query("SELECT * FROM insurance_grade ORDER BY start_date DESC, type, grade", conn)

def batch_insert_or_replace_grades(conn, df: pd.DataFrame, grade_type: str, start_date):
    """批次插入或替換指定適用日期的級距資料。"""
    cursor = conn.cursor()
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    sql = """
    INSERT INTO insurance_grade (
        start_date, type, grade, salary_min, salary_max, 
        employee_fee, employer_fee, gov_fee, note
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(start_date, type, grade) DO UPDATE SET
        salary_min=excluded.salary_min,
        salary_max=excluded.salary_max,
        employee_fee=excluded.employee_fee,
        employer_fee=excluded.employer_fee,
        gov_fee=excluded.gov_fee,
        note=excluded.note;
    """
    
    try:
        data_tuples = []
        for _, row in df.iterrows():
            data_tuples.append((
                start_date_str, grade_type, row['grade'],
                row['salary_min'], row['salary_max'],
                row.get('employee_fee'), row.get('employer_fee'),
                row.get('gov_fee'), row.get('note')
            ))
            
        cursor.executemany(sql, data_tuples)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    
# 批次新增或更新員工加保紀錄
def batch_add_or_update_insurance_history(conn, df: pd.DataFrame):
    cursor = conn.cursor()
    report = {'inserted': 0, 'updated': 0, 'errors': []}
    
    emp_map = pd.read_sql("SELECT name_ch, id FROM employee", conn).set_index('name_ch')['id'].to_dict()
    comp_map = pd.read_sql("SELECT name, id FROM company", conn).set_index('name')['id'].to_dict()

    sql_insert = "INSERT INTO employee_company_history (employee_id, company_id, start_date, end_date, note) VALUES (?, ?, ?, ?, ?)"
    sql_update = "UPDATE employee_company_history SET end_date = ?, note = ? WHERE id = ?"
    sql_check = "SELECT id FROM employee_company_history WHERE employee_id = ? AND company_id = ? AND start_date = ?"

    try:
        cursor.execute("BEGIN TRANSACTION")
        for index, row in df.iterrows():
            emp_id = emp_map.get(row['name_ch'])
            comp_id = comp_map.get(row['company_name'])

            if not emp_id:
                report['errors'].append({'row': index + 2, 'reason': f"找不到員工姓名 '{row['name_ch']}'。"})
                continue
            if not comp_id:
                report['errors'].append({'row': index + 2, 'reason': f"找不到公司名稱 '{row['company_name']}'。"})
                continue

            existing_record = cursor.execute(sql_check, (emp_id, comp_id, row['start_date'])).fetchone()
            
            if existing_record:
                cursor.execute(sql_update, (row.get('end_date'), row.get('note'), existing_record['id']))
                report['updated'] += 1
            else:
                cursor.execute(sql_insert, (emp_id, comp_id, row['start_date'], row.get('end_date'), row.get('note')))
                report['inserted'] += 1
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        report['errors'].append({'row': 'N/A', 'reason': f'資料庫操作失敗: {e}'})
    
    return report

def get_insurance_salary_level(conn, base_salary: float):
    """根據薪資查詢對應的健保投保級距金額(上限)。"""
    if not base_salary or base_salary <= 0:
        return base_salary
        
    # 優先使用健保('health')級距來決定投保薪資
    sql = """
    SELECT salary_max 
    FROM insurance_grade 
    WHERE type = 'health' 
      AND ? BETWEEN salary_min AND salary_max 
    ORDER BY start_date DESC 
    LIMIT 1
    """
    result = conn.execute(sql, (base_salary,)).fetchone()
    
    if result:
        return result[0]
    else:
        # 如果找不到對應級距（可能薪資超過最高級距），則回傳薪資本身或一個預設上限
        # 這裡我們回傳薪資本身，讓薪資計算邏輯去處理
        return base_salary