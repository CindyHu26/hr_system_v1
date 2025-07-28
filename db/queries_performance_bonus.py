# db/queries_performance_bonus.py
import pandas as pd

def save_performance_bonuses(conn, year: int, month: int, bonus_df: pd.DataFrame):
    """
    將計算好的績效獎金批次存入資料庫。
    此操作會先刪除該月份的所有舊紀錄，再插入新紀錄，確保資料永遠是最新版。
    """
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM monthly_performance_bonus WHERE year = ? AND month = ?", (year, month))
        
        if bonus_df.empty:
            conn.commit()
            return 0

        to_insert = [
            (int(row['employee_id']), year, month, float(row['bonus_amount']))
            for _, row in bonus_df.iterrows()
        ]
        
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
    【核心修改】確保函式只回傳一個數字或 0。
    """
    sql = "SELECT bonus_amount FROM monthly_performance_bonus WHERE employee_id = ? AND year = ? AND month = ?"
    result = conn.execute(sql, (emp_id, year, month)).fetchone()
    # 如果有找到紀錄，就回傳 bonus_amount 欄位的值，否則回傳 0
    return result['bonus_amount'] if result else 0