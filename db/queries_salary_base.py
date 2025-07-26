# db/queries_salary_base.py
"""
資料庫查詢：專門處理員工的「薪資基準(salary_base_history)」，如底薪、眷屬數的歷史紀錄。
"""
import pandas as pd
import re
from utils.helpers import get_monthly_dates

def get_salary_base_history(conn):
    """取得所有員工的薪資基準歷史紀錄，並包含健保狀態與手動調整欄位。"""
    return pd.read_sql_query("""
        SELECT sh.id, sh.employee_id, e.name_ch, sh.base_salary, sh.insurance_salary,
               sh.dependents_under_18, sh.dependents_over_18, 
               sh.labor_insurance_override, sh.health_insurance_override, sh.pension_override,
               sh.start_date, sh.end_date, sh.note,
               e.nhi_status, e.nhi_status_expiry
        FROM salary_base_history sh JOIN employee e ON sh.employee_id = e.id
        ORDER BY e.hr_code, sh.start_date DESC
    """, conn)

def get_employee_base_salary_info(conn, emp_id, year, month):
    """查詢員工在特定時間點的底薪、投保薪資、眷屬數及手動調整值。"""
    _, month_end = get_monthly_dates(year, month)
    sql = """
    SELECT base_salary, insurance_salary, dependents_under_18, dependents_over_18,
           labor_insurance_override, health_insurance_override, pension_override
    FROM salary_base_history 
    WHERE employee_id = ? AND start_date <= ? 
    ORDER BY start_date DESC 
    LIMIT 1
    """
    return conn.execute(sql, (emp_id, month_end)).fetchone()

def get_employees_below_minimum_wage(conn, new_minimum_wage: int):
    """找出所有在職且當前底薪低於指定薪資的員工，並包含計算保費所需的所有資訊。"""
    query = """
    WITH latest_salary AS (
        SELECT
            employee_id, base_salary, insurance_salary, 
            dependents_under_18, dependents_over_18,
            ROW_NUMBER() OVER(PARTITION BY employee_id ORDER BY start_date DESC) as rn
        FROM salary_base_history
    )
    SELECT
        e.id as employee_id, e.name_ch as "員工姓名",
        ls.base_salary as "目前底薪", ls.insurance_salary as "目前投保薪資",
        ls.dependents_under_18, ls.dependents_over_18,
        e.nhi_status, e.nhi_status_expiry
    FROM employee e
    JOIN latest_salary ls ON e.id = ls.employee_id
    WHERE (e.resign_date IS NULL OR e.resign_date = '') AND ls.rn = 1 AND ls.base_salary < ?
    ORDER BY e.hr_code;
    """
    return pd.read_sql_query(query, conn, params=(new_minimum_wage,))

def batch_update_base_salary(conn, preview_df: pd.DataFrame, new_wage: int, effective_date):
    """根據預覽 DataFrame，為指定員工批次新增一筆調薪紀錄。"""
    cursor = conn.cursor()
    try:
        # [核心修改] 更新資料元組，使其對應新的眷屬欄位
        data_to_insert = [
            (
                row['employee_id'], new_wage, new_wage, 
                row['dependents_under_18'], row['dependents_over_18'],
                effective_date.strftime('%Y-%m-%d'), None,
                f"配合 {effective_date.year} 年基本工資調整"
            )
            for _, row in preview_df.iterrows()
        ]
        # [核心修改] 更新 INSERT 語句中的欄位列表
        sql = """
        INSERT INTO salary_base_history 
            (employee_id, base_salary, insurance_salary, dependents_under_18, dependents_over_18, start_date, end_date, note) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.executemany(sql, data_to_insert)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e

def get_batch_employee_insurance_salary(conn, emp_ids: list, year: int, month: int):
    """批次獲取多名員工在特定時間點的投保薪資。"""
    if not emp_ids:
        return {}
    
    salaries = {}
    for emp_id in emp_ids:
        base_info = get_employee_base_salary_info(conn, emp_id, year, month)
        salaries[emp_id] = base_info['insurance_salary'] if base_info and base_info['insurance_salary'] else (base_info['base_salary'] if base_info else 0)
    return salaries

def batch_add_or_update_salary_base_history(conn, df: pd.DataFrame):
    cursor = conn.cursor()
    report = {'inserted': 0, 'updated': 0, 'failed': 0, 'errors': []}
    
    emp_df_db = pd.read_sql("SELECT name_ch, id FROM employee", conn)
    emp_df_db['clean_name'] = emp_df_db['name_ch'].astype(str).str.replace(r'\s+', '', regex=True)
    emp_map = emp_df_db.set_index('clean_name')['id'].to_dict()

    sql = """
    INSERT INTO salary_base_history 
        (employee_id, base_salary, insurance_salary, dependents_under_18, dependents_over_18, 
         labor_insurance_override, health_insurance_override, pension_override,
         start_date, end_date, note)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(employee_id, start_date) DO UPDATE SET
        base_salary = excluded.base_salary,
        insurance_salary = excluded.insurance_salary,
        dependents_under_18 = excluded.dependents_under_18,
        dependents_over_18 = excluded.dependents_over_18,
        labor_insurance_override = excluded.labor_insurance_override,
        health_insurance_override = excluded.health_insurance_override,
        pension_override = excluded.pension_override,
        end_date = excluded.end_date,
        note = excluded.note;
    """

    try:
        data_to_upsert = []
        for index, row in df.iterrows():
            clean_name_excel = re.sub(r'\s+', '', str(row['name_ch']))
            emp_id = emp_map.get(clean_name_excel)
            
            if not emp_id:
                report['errors'].append({'row': row.get('original_index', index + 2), 'reason': f"找不到員工姓名 '{row['name_ch']}'。"})
                continue
            
            data_to_upsert.append((
                emp_id, row['base_salary'], row['insurance_salary'], 
                row['dependents_under_18'], row['dependents_over_18'],
                row.get('labor_insurance_override'), row.get('health_insurance_override'), row.get('pension_override'),
                row['start_date'], row.get('end_date'), row.get('note')
            ))
        
        if data_to_upsert:
            cursor.executemany(sql, data_to_upsert)
            conn.commit()
            report['updated'] = cursor.rowcount
            
    except Exception as e:
        conn.rollback()
        report['errors'].append({'row': 'N/A', 'reason': f'資料庫操作失敗: {e}'})
        
    return report