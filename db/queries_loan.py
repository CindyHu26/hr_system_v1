# db/queries_loan.py
import pandas as pd

def get_loans_by_month(conn, year: int, month: int):
    """查詢指定月份的所有借支紀錄。"""
    query = """
    SELECT 
        l.id,
        e.id as employee_id,
        e.hr_code as '員工編號',
        e.name_ch as '員工姓名',
        l.amount as '借支金額',
        l.note as '備註'
    FROM monthly_loan l
    JOIN employee e ON l.employee_id = e.id
    WHERE l.year = ? AND l.month = ?
    ORDER BY e.hr_code
    """
    return pd.read_sql_query(query, conn, params=(year, month))

def get_employee_loan(conn, emp_id: int, year: int, month: int):
    """查詢單一員工在指定月份的借支金額。"""
    sql = "SELECT amount FROM monthly_loan WHERE employee_id = ? AND year = ? AND month = ?"
    result = conn.execute(sql, (emp_id, year, month)).fetchone()
    return result['amount'] if result else 0

def upsert_loan_record(conn, data: dict):
    """新增或更新一筆借支紀錄。"""
    sql = """
    INSERT INTO monthly_loan (employee_id, year, month, amount, note)
    VALUES (:employee_id, :year, :month, :amount, :note)
    ON CONFLICT(employee_id, year, month) DO UPDATE SET
        amount = excluded.amount,
        note = excluded.note;
    """
    cursor = conn.cursor()
    cursor.execute(sql, data)
    conn.commit()
    return cursor.rowcount