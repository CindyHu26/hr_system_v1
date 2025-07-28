# db/queries_performance_bonus.py
import pandas as pd

def save_performance_bonuses(conn, year: int, month: int, bonus_df: pd.DataFrame):
    """
    將計算好的績效獎金批次存入資料庫。
    此操作會先刪除該月份的舊紀錄，再插入新紀錄。
    """
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. 刪除該月份的舊資料
        cursor.execute("DELETE FROM monthly_performance_bonus WHERE year = ? AND month = ?", (year, month))
        
        # 2. 準備要插入的新資料
        to_insert = [
            (int(row['employee_id']), year, month, float(row['bonus_amount']))
            for _, row in bonus_df.iterrows()
        ]
        
        # 3. 執行批次插入
        sql = "INSERT INTO monthly_performance_bonus (employee_id, year, month, bonus_amount) VALUES (?, ?, ?, ?)"
        cursor.executemany(sql, to_insert)
        
        conn.commit()
        return len(to_insert)
    except Exception as e:
        conn.rollback()
        raise e

def get_performance_bonus(conn, emp_id: int, year: int, month: int):
    """
    從資料庫讀取指定員工在該月份的績效獎金。
    """
    sql = "SELECT bonus_amount FROM monthly_performance_bonus WHERE employee_id = ? AND year = ? AND month = ?"
    result = conn.execute(sql, (emp_id, year, month)).fetchone()
    return result['bonus_amount'] if result else 0