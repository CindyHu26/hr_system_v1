# db/queries_attendance.py
"""
資料庫查詢：專門處理「出勤(attendance)」、「特別出勤(special_attendance)」
與「請假(leave_record)」相關的資料庫操作。
"""
import pandas as pd

def get_attendance_by_month(conn, year, month):
    """根據年月查詢出勤紀錄，並一併顯示員工姓名與編號。"""
    month_str = f"{year}-{month:02d}"
    query = """
    SELECT
        a.id, e.hr_code, e.name_ch, a.date, a.checkin_time, a.checkout_time,
        a.late_minutes, a.early_leave_minutes, a.absent_minutes, a.overtime1_minutes,
        a.overtime2_minutes, a.overtime3_minutes, a.note
    FROM attendance a
    JOIN employee e ON a.employee_id = e.id
    WHERE STRFTIME('%Y-%m', a.date) = ?
    ORDER BY a.date DESC, e.hr_code
    """
    return pd.read_sql_query(query, conn, params=(month_str,))

def batch_insert_or_update_attendance(conn, df: pd.DataFrame):
    """
    批次插入或更新出勤紀錄。
    如果員工在同一天的紀錄已存在，則會更新，否則新增。
    """
    df_to_insert = df[pd.notna(df['employee_id'])].copy()
    if df_to_insert.empty:
        return 0

    df_to_insert['employee_id'] = pd.to_numeric(df_to_insert['employee_id'], errors='coerce').fillna(0).astype(int)

    sql = """
        INSERT INTO attendance (
            employee_id, date, checkin_time, checkout_time, late_minutes, early_leave_minutes,
            absent_minutes, overtime1_minutes, overtime2_minutes, overtime3_minutes, source_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(employee_id, date) DO UPDATE SET
            checkin_time=excluded.checkin_time,
            checkout_time=excluded.checkout_time,
            late_minutes=excluded.late_minutes,
            early_leave_minutes=excluded.early_leave_minutes,
            absent_minutes=excluded.absent_minutes,
            overtime1_minutes=excluded.overtime1_minutes,
            overtime2_minutes=excluded.overtime2_minutes,
            overtime3_minutes=excluded.overtime3_minutes,
            source_file=excluded.source_file;
    """

    data_tuples = [
        (
            row['employee_id'], row['date'], row.get('checkin_time'), row.get('checkout_time'),
            row.get('late_minutes', 0), row.get('early_leave_minutes', 0), row.get('absent_minutes', 0),
            row.get('overtime1_minutes', 0), row.get('overtime2_minutes', 0), row.get('overtime3_minutes', 0),
            'excel_import'
        ) for _, row in df_to_insert.iterrows()
    ]

    cursor = conn.cursor()
    try:
        cursor.executemany(sql, data_tuples)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e

def get_special_attendance_for_month(conn, employee_id, year, month):
    """查詢員工指定月份的特別出勤紀錄。"""
    month_str = f"{year}-{month:02d}"
    query = "SELECT checkin_time, checkout_time FROM special_attendance WHERE employee_id = ? AND STRFTIME('%Y-%m', date) = ?"
    return conn.execute(query, (employee_id, month_str)).fetchall()

def get_employee_leave_summary(conn, emp_id, year, month):
    """查詢員工當月的請假總結。"""
    month_str = f"{year}-{month:02d}"
    sql = "SELECT leave_type, SUM(duration) FROM leave_record WHERE employee_id = ? AND strftime('%Y-%m', start_date) = ? AND status = '已通過' GROUP BY leave_type"
    return conn.execute(sql, (emp_id, month_str)).fetchall()