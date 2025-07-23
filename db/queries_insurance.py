# db/queries_insurance.py
"""
資料庫查詢：專門處理「保險(insurance)」相關的資料庫操作。
"""
import pandas as pd

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