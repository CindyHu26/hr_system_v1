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
        a.late_minutes, a.early_leave_minutes, a.absent_minutes, a.leave_minutes, 
        a.overtime1_minutes, a.overtime2_minutes, a.overtime3_minutes, a.note
    FROM attendance a
    JOIN employee e ON a.employee_id = e.id
    WHERE STRFTIME('%Y-%m', a.date) = ?
    ORDER BY a.date DESC, e.hr_code
    """
    return pd.read_sql_query(query, conn, params=(month_str,))

def batch_insert_or_update_attendance(conn, df: pd.DataFrame):
    """
    批次插入或更新出勤紀錄。
    """
    df_to_insert = df[pd.notna(df['employee_id'])].copy()
    if df_to_insert.empty:
        return 0

    df_to_insert['employee_id'] = pd.to_numeric(df_to_insert['employee_id'], errors='coerce').fillna(0).astype(int)

    sql = """
        INSERT INTO attendance (
            employee_id, date, checkin_time, checkout_time, late_minutes, early_leave_minutes,
            absent_minutes, leave_minutes, overtime1_minutes, overtime2_minutes, overtime3_minutes, source_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(employee_id, date) DO UPDATE SET
            checkin_time=excluded.checkin_time,
            checkout_time=excluded.checkout_time,
            late_minutes=excluded.late_minutes,
            early_leave_minutes=excluded.early_leave_minutes,
            absent_minutes=excluded.absent_minutes,
            leave_minutes=excluded.leave_minutes,
            overtime1_minutes=excluded.overtime1_minutes,
            overtime2_minutes=excluded.overtime2_minutes,
            overtime3_minutes=excluded.overtime3_minutes,
            source_file=excluded.source_file;
    """

    # 【修改】資料元組中加入 leave_minutes
    data_tuples = [
        (
            row['employee_id'], row['date'], row.get('checkin_time'), row.get('checkout_time'),
            row.get('late_minutes', 0), row.get('early_leave_minutes', 0), row.get('absent_minutes', 0),
            row.get('leave_minutes', 0), # 新增欄位
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

def get_special_attendance_by_month(conn, year, month):
    """查詢指定月份的特別出勤紀錄。"""
    month_str = f"{year}-{month:02d}"
    query = """
    SELECT sa.id, e.name_ch as '員工姓名', sa.date as '日期', 
           sa.checkin_time as '上班時間', sa.checkout_time as '下班時間', sa.note as '備註'
    FROM special_attendance sa
    JOIN employee e ON sa.employee_id = e.id
    WHERE STRFTIME('%Y-%m', sa.date) = ?
    ORDER BY sa.date, e.name_ch
    """
    return pd.read_sql_query(query, conn, params=(month_str,))

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
    # 查詢中加入 SUM(leave_minutes)
    query = """
    SELECT employee_id, 
           SUM(overtime1_minutes) as overtime1_minutes, SUM(overtime2_minutes) as overtime2_minutes, 
           SUM(late_minutes) as late_minutes, SUM(early_leave_minutes) as early_leave_minutes,
           SUM(leave_minutes) as leave_minutes
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
        
        emp_map = pd.read_sql_query("SELECT name_ch, id FROM employee", conn)
        emp_dict = dict(zip(emp_map['name_ch'], emp_map['id']))
        df_to_import['employee_id'] = df_to_import['Employee Name'].map(emp_dict)

        df_to_import.dropna(subset=['employee_id'], inplace=True)
        df_to_import['employee_id'] = df_to_import['employee_id'].astype(int)

        # 【修改】將 reason 和 approver 欄位加回到 INSERT 和 UPDATE 語句中
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
            reason=excluded.reason,
            approver=excluded.approver,
            note='UPDATED_FROM_UI'
        """
        
        data_tuples = []
        for _, row in df_to_import.iterrows():
            submit_date_val = row.get('Submission Date')
            parsed_submit_date = pd.to_datetime(submit_date_val, errors='coerce')
            submit_date_str = parsed_submit_date.strftime('%Y-%m-%d') if pd.notna(parsed_submit_date) else None
            
            # 【修改】將 Details (事由) 和 Approver Name (簽核人) 加回到資料元組中
            data_tuples.append((
                row['employee_id'],
                row['Request ID'],
                row['Type of Leave'],
                pd.to_datetime(row['Start Date']).strftime('%Y-%m-%d %H:%M:%S'),
                pd.to_datetime(row['End Date']).strftime('%Y-%m-%d %H:%M:%S'),
                row['核算時數'],
                row.get('Details'),  # 事由
                row.get('Status'),
                row.get('Approver Name'),  # 簽核人
                submit_date_str,
                row.get('備註')
            ))

        cursor.executemany(sql, data_tuples)
        conn.commit()
        return len(data_tuples)
        
    except Exception as e:
        conn.rollback()
        raise e
    
# 用於交叉分析的查詢函式
def get_monthly_attendance_and_leave_data(conn, year: int, month: int):
    """
    獲取指定月份所有員工的出勤紀錄（包含簽到/退）和請假紀錄。
    """
    month_str = f"{year}-{month:02d}"
    
    # 查詢所有出勤紀錄，而不僅僅是缺席
    attendance_query = """
    SELECT 
        e.id as employee_id,
        e.name_ch,
        a.date,
        a.checkin_time,
        a.checkout_time,
        a.absent_minutes
    FROM attendance a
    JOIN employee e ON a.employee_id = e.id
    WHERE STRFTIME('%Y-%m', a.date) = ?
    """
    attendance_df = pd.read_sql_query(attendance_query, conn, params=(month_str,))
    
    # 查詢所有「已通過」的假單紀錄
    leave_query = """
    SELECT
        e.id as employee_id,
        lr.leave_type,
        lr.start_date,
        lr.end_date,
        lr.duration
    FROM leave_record lr
    JOIN employee e ON lr.employee_id = e.id
    WHERE 
        (STRFTIME('%Y-%m', lr.start_date) = ? OR STRFTIME('%Y-%m', lr.end_date) = ?)
        AND lr.status = '已通過'
    """
    leave_df = pd.read_sql_query(leave_query, conn, params=(month_str, month_str))

    return attendance_df, leave_df


def get_leave_records_by_month(conn, year: int, month: int):
    """
    根據年月查詢所有已匯入的請假紀錄。
    """
    month_str = f"{year}-{month:02d}"
    query = """
    SELECT
        e.name_ch as '員工姓名',
        lr.leave_type as '假別',
        lr.start_date as '開始時間',
        lr.end_date as '結束時間',
        lr.duration as '時數',
        lr.reason as '事由',
        lr.status as '狀態',
        lr.approver as '簽核人',
        lr.request_id as '假單ID'
    FROM leave_record lr
    JOIN employee e ON lr.employee_id = e.id
    WHERE STRFTIME('%Y-%m', lr.start_date) = ?
    ORDER BY e.name_ch, lr.start_date
    """
    return pd.read_sql_query(query, conn, params=(month_str,))