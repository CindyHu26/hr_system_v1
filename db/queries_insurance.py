# db/queries_insurance.py
"""
資料庫查詢：專門處理「保險(insurance)」相關的資料庫操作。
包含：員工加退保歷史、勞健保級距表管理。
"""
import pandas as pd
from utils.helpers import get_monthly_dates

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

def get_employee_insurance_fee(conn, insurance_salary: int, year: int, month: int):
    """
    根據投保薪資、年份和月份，查詢員工應負擔的勞健保費用。
    """
    if not insurance_salary or insurance_salary <= 0:
        return 0, 0
        
    cursor = conn.cursor()
    month_end_date = get_monthly_dates(year, month)[1]

    def get_fee_by_type(ins_type: str):
        query = """
        SELECT g.employee_fee
        FROM insurance_grade g
        WHERE g.type = ?
          AND g.start_date = (
              SELECT MAX(start_date) 
              FROM insurance_grade 
              WHERE type = ? AND start_date <= ?
          )
          AND (
              ? BETWEEN g.salary_min AND g.salary_max
              OR 
              g.grade = (SELECT MAX(grade) FROM insurance_grade WHERE type = ? AND start_date = g.start_date) AND ? > g.salary_max
          )
        LIMIT 1;
        """
        params = (ins_type, ins_type, month_end_date, insurance_salary, ins_type, insurance_salary)
        fee_row = cursor.execute(query, params).fetchone()
        
        return fee_row[0] if fee_row else 0

    labor_fee = get_fee_by_type('labor')
    health_fee = get_fee_by_type('health')
    
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

def is_employee_insured_in_month(conn, employee_id: int, year: int, month: int):
    """檢查員工在指定月份是否在公司有加保紀錄。"""
    _, month_end = get_monthly_dates(year, month)
    query = """
    SELECT 1 FROM employee_company_history
    WHERE employee_id = ?
      AND start_date <= ?
      AND (end_date IS NULL OR end_date >= ?)
    LIMIT 1;
    """
    cursor = conn.cursor()
    result = cursor.execute(query, (employee_id, month_end, month_end)).fetchone()
    return result is not None

def get_insurance_salary_level(conn, base_salary: float):
    """根據薪資查詢對應的健保投保級距金額(上限)。"""
    if not base_salary or base_salary <= 0:
        return base_salary
        
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
        return base_salary