# db/queries_insurance.py
"""
資料庫查詢：專門處理「保險(insurance)」相關的資料庫操作。
包含：員工加退保歷史、勞健保級距表管理。
"""
import pandas as pd

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

# --- Insurance Grade Management (新增的函式) ---

def get_insurance_grades(conn):
    """取得所有勞健保級距資料。"""
    return pd.read_sql_query("SELECT * FROM insurance_grade ORDER BY start_date DESC, type, grade", conn)

def batch_insert_or_replace_grades(conn, df: pd.DataFrame, grade_type: str, start_date):
    """批次插入或替換指定適用日期的級距資料。"""
    cursor = conn.cursor()
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    # 使用 ON CONFLICT(start_date, type, grade) DO UPDATE 確保資料的唯一性
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