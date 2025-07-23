# db/queries_attendance.py
"""
資料庫查詢：專門處理「出勤(attendance)」、「特別出勤(special_attendance)」
與「請假(leave_record)」相關的資料庫操作。
"""
import pandas as pd
from utils.helpers import get_monthly_dates

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

def batch_insert_or_update_leave_records(conn, df: pd.DataFrame):
    """
    批次插入或更新請假紀錄。
    以「假單申請ID (request_id)」為唯一鍵，如果已存在則更新，否則新增。
    """
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        df_to_import = df.copy()
        
        # 建立 employee_id
        emp_map = pd.read_sql_query("SELECT name_ch, id FROM employee", conn)
        emp_dict = dict(zip(emp_map['name_ch'], emp_map['id']))
        df_to_import['employee_id'] = df_to_import['Employee Name'].map(emp_dict)

        # 篩選掉沒有成功匹配到員工ID的紀錄
        df_to_import.dropna(subset=['employee_id'], inplace=True)
        df_to_import['employee_id'] = df_to_import['employee_id'].astype(int)

        sql = """
        INSERT INTO leave_record (
            employee_id, request_id, leave_type, start_date, end_date,
            duration, reason, status, approver, submit_date, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(request_id) DO UPDATE SET
            employee_id=excluded.employee_id,
            leave_type=excluded.leave_type,
            start_date=excluded.start_date,
            end_date=excluded.end_date,
            duration=excluded.duration,
            status=excluded.status,
            note='UPDATED_FROM_UI'
        """
        
        data_tuples = []
        for _, row in df_to_import.iterrows():
            data_tuples.append((
                row['employee_id'],
                row['Request ID'],
                row['Type of Leave'],
                # 確保日期時間格式正確寫入資料庫
                pd.to_datetime(row['Start Date']).strftime('%Y-%m-%d %H:%M:%S'),
                pd.to_datetime(row['End Date']).strftime('%Y-%m-%d %H:%M:%S'),
                row['核算時數'], # 使用我們核算過後的時數
                row.get('Details'),
                row.get('Status'),
                row.get('Approver Name'),
                pd.to_datetime(row.get('Date Submitted')).strftime('%Y-%m-%d') if pd.notna(row.get('Date Submitted')) else None,
                row.get('備註')
            ))

        cursor.executemany(sql, data_tuples)
        conn.commit()
        return len(data_tuples)
        
    except Exception as e:
        conn.rollback()
        raise e