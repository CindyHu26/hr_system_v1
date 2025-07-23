# db/queries_salary.py
"""
資料庫查詢：專門處理所有與「薪資(salary)」、「保險(insurance)」
和「獎金(bonus)」計算相關的資料庫操作。
"""
import pandas as pd
from utils.helpers import get_monthly_dates

# --- 保險(Insurance) 相關 ---

def get_all_insurance_history(conn):
    """取得所有員工的加退保歷史紀錄。"""
    query = """
    SELECT ech.id, e.name_ch, c.name as company_name,
           ech.start_date, ech.end_date, ech.note
    FROM employee_company_history ech
    JOIN employee e ON ech.employee_id = e.id
    JOIN company c ON ech.company_id = c.id
    ORDER BY ech.start_date DESC
    """
    return pd.read_sql_query(query, conn)

def get_employee_insurance_fee(conn, insurance_salary):
    """根據投保薪資查詢員工應負擔的勞健保費用。"""
    sql_labor = "SELECT employee_fee FROM insurance_grade WHERE type = 'labor' AND ? BETWEEN salary_min AND salary_max ORDER BY start_date DESC LIMIT 1"
    labor_fee_row = conn.execute(sql_labor, (insurance_salary,)).fetchone()
    
    sql_health = "SELECT employee_fee FROM insurance_grade WHERE type = 'health' AND ? BETWEEN salary_min AND salary_max ORDER BY start_date DESC LIMIT 1"
    health_fee_row = conn.execute(sql_health, (insurance_salary,)).fetchone()
    
    return (labor_fee_row[0] if labor_fee_row else 0), (health_fee_row[0] if health_fee_row else 0)

# --- 薪資項目(Salary Item) & 薪資基準(Base History) ---

def get_all_salary_items(conn, active_only=False):
    """取得所有薪資項目。"""
    query = "SELECT * FROM salary_item ORDER BY type, id"
    if active_only:
        query = "SELECT * FROM salary_item WHERE is_active = 1"
    return pd.read_sql_query(query, conn)

def get_salary_base_history(conn):
    """取得所有員工的薪資基準(底薪、眷屬數)歷史紀錄。"""
    return pd.read_sql_query("""
        SELECT sh.id, sh.employee_id, e.name_ch, sh.base_salary, sh.insurance_salary,
               sh.dependents, sh.start_date, sh.end_date, sh.note
        FROM salary_base_history sh JOIN employee e ON sh.employee_id = e.id
        ORDER BY e.id, sh.start_date DESC
    """, conn)

def get_employee_base_salary_info(conn, emp_id, year, month):
    """查詢員工在特定時間點的底薪、投保薪資與眷屬數。"""
    _, month_end = get_monthly_dates(year, month)
    sql = "SELECT base_salary, insurance_salary, dependents FROM salary_base_history WHERE employee_id = ? AND start_date <= ? ORDER BY start_date DESC LIMIT 1"
    return conn.execute(sql, (emp_id, month_end)).fetchone()

def get_item_types(conn):
    """獲取薪資項目的名稱與類型對應字典。"""
    return pd.read_sql("SELECT name, type FROM salary_item", conn).set_index('name')['type'].to_dict()

def get_employee_recurring_items(conn, emp_id):
    """查詢員工的常態薪資設定 (如固定的津貼或扣款)。"""
    sql = "SELECT si.name, esi.amount, si.type FROM employee_salary_item esi JOIN salary_item si ON esi.salary_item_id = si.id WHERE esi.employee_id = ?"
    return conn.execute(sql, (emp_id,)).fetchall()

# --- 薪資主流程(Salary) & 獎金(Bonus) ---

def get_active_employees_for_month(conn, year, month):
    """查詢指定月份仍在職的員工。"""
    start_date, end_date = get_monthly_dates(year, month)
    query = """
    SELECT e.id, e.name_ch, e.hr_code FROM employee e
    WHERE (e.entry_date IS NOT NULL AND e.entry_date <= ?) 
      AND (e.resign_date IS NULL OR e.resign_date >= ?)
    ORDER BY e.id ASC
    """
    return conn.execute(query, (end_date, start_date)).fetchall()

def get_monthly_attendance_summary(conn, year, month):
    """獲取指定月份的考勤總結，用於薪資計算。"""
    _, month_end = get_monthly_dates(year, month)
    month_str = month_end[:7] # YYYY-MM
    query = """
    SELECT employee_id, 
           SUM(overtime1_minutes) as overtime1_minutes, 
           SUM(overtime2_minutes) as overtime2_minutes, 
           SUM(late_minutes) as late_minutes, 
           SUM(early_leave_minutes) as early_leave_minutes 
    FROM attendance 
    WHERE STRFTIME('%Y-%m', date) = ?
    GROUP BY employee_id
    """
    return pd.read_sql_query(query, conn, params=(month_str,)).set_index('employee_id')

def get_employee_bonus(conn, emp_id, year, month):
    """從中繼站讀取預先算好的業務獎金。"""
    sql = "SELECT bonus_amount FROM monthly_bonus WHERE employee_id = ? AND year = ? AND month = ?"
    return conn.execute(sql, (emp_id, year, month)).fetchone()

def save_bonuses_to_monthly_table(conn, year, month, summary_df):
    """將計算好的獎金總結存入 monthly_bonus 中繼站。"""
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM monthly_bonus WHERE year = ? AND month = ?", (year, month))
        to_insert = [
            (int(row['employee_id']), year, month, float(row['bonus_amount']), '爬蟲計算')
            for _, row in summary_df.iterrows()
        ]
        sql = "INSERT INTO monthly_bonus (employee_id, year, month, bonus_amount, note) VALUES (?, ?, ?, ?, ?)"
        cursor.executemany(sql, to_insert)
        conn.commit()
        return len(to_insert)
    except Exception as e:
        conn.rollback()
        raise e

def save_salary_draft(conn, year, month, df: pd.DataFrame):
    """儲存薪資草稿。"""
    cursor = conn.cursor()
    emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
    item_map = pd.read_sql("SELECT id, name FROM salary_item", conn).set_index('name')['id'].to_dict()
    for _, row in df.iterrows():
        emp_id = emp_map.get(row['員工姓名'])
        if not emp_id: continue
        cursor.execute("INSERT INTO salary (employee_id, year, month, status) VALUES (?, ?, ?, 'draft') ON CONFLICT(employee_id, year, month) DO UPDATE SET status = 'draft' WHERE status != 'final'", (emp_id, year, month))
        salary_id = cursor.execute("SELECT id FROM salary WHERE employee_id = ? AND year = ? AND month = ?", (emp_id, year, month)).fetchone()[0]
        cursor.execute("DELETE FROM salary_detail WHERE salary_id = ?", (salary_id,))
        details_to_insert = [(salary_id, item_map.get(k), int(v)) for k, v in row.items() if item_map.get(k) and v != 0]
        if details_to_insert:
            cursor.executemany("INSERT INTO salary_detail (salary_id, salary_item_id, amount) VALUES (?, ?, ?)", details_to_insert)
    conn.commit()

def finalize_salary_records(conn, year, month, df: pd.DataFrame):
    """將薪資紀錄定版。"""
    cursor = conn.cursor()
    emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
    for _, row in df.iterrows():
        emp_id = emp_map.get(row['員工姓名'])
        if not emp_id: continue
        params = {
            'total_payable': row.get('應付總額', 0), 'total_deduction': row.get('應扣總額', 0),
            'net_salary': row.get('實發薪資', 0), 'bank_transfer_amount': row.get('匯入銀行', 0),
            'cash_amount': row.get('現金', 0), 'status': 'final',
            'employee_id': emp_id, 'year': year, 'month': month
        }
        cursor.execute("""
            UPDATE salary SET
            total_payable = :total_payable, total_deduction = :total_deduction,
            net_salary = :net_salary, bank_transfer_amount = :bank_transfer_amount,
            cash_amount = :cash_amount, status = :status
            WHERE employee_id = :employee_id AND year = :year AND month = :month
        """, params)
    conn.commit()

def revert_salary_to_draft(conn, year, month, employee_ids: list):
    """將已定版的薪資紀錄恢復為草稿狀態。"""
    if not employee_ids: return 0
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in employee_ids)
    sql = f"UPDATE salary SET status = 'draft' WHERE year = ? AND month = ? AND employee_id IN ({placeholders}) AND status = 'final'"
    params = [year, month] + employee_ids
    cursor.execute(sql, params)
    conn.commit()
    return cursor.rowcount