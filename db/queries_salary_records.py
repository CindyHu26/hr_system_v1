# db/queries_salary_records.py
"""
資料庫查詢：專門處理每月的「薪資單紀錄(salary)」與「獎金(bonus)」的儲存與讀取。
"""
import pandas as pd
from utils.helpers import get_monthly_dates

def get_active_employees_for_month(conn, year, month):
    """查詢指定月份仍在職的員工。"""
    start_date, end_date = get_monthly_dates(year, month)
    query = """
    SELECT e.id, e.name_ch, e.hr_code FROM employee e
    WHERE (e.entry_date IS NOT NULL AND e.entry_date <= ?) 
      AND (e.resign_date IS NULL OR e.resign_date >= ?)
    ORDER BY e.hr_code ASC
    """
    return conn.execute(query, (end_date, start_date)).fetchall()

def get_monthly_attendance_summary(conn, year, month):
    """獲取指定月份的考勤總結，用於薪資計算。"""
    _, month_end = get_monthly_dates(year, month)
    month_str = month_end[:7] # YYYY-MM
    query = """
    SELECT employee_id, 
           SUM(overtime1_minutes) as overtime1_minutes, SUM(overtime2_minutes) as overtime2_minutes, 
           SUM(late_minutes) as late_minutes, SUM(early_leave_minutes) as early_leave_minutes 
    FROM attendance WHERE STRFTIME('%Y-%m', date) = ? GROUP BY employee_id
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
        conn.rollback(); raise e

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
    # (此函式內容不變，此處省略以保持簡潔)
    pass 

def revert_salary_to_draft(conn, year, month, employee_ids: list):
    """將已定版的薪資紀錄恢復為草稿狀態。"""
    # (此函式內容不變，此處省略以保持簡潔)
    pass