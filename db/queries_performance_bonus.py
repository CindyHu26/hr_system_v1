# db/queries_performance_bonus.py
import pandas as pd

def save_performance_bonuses(conn, year: int, month: int, bonus_df: pd.DataFrame):
    """
    將計算好的績效獎金批次存入資料庫。
    【核心修改】此操作會先刪除該月份的所有舊紀錄，再插入新紀錄，確保資料永遠是最新版。
    """
    cursor = conn.cursor()
    try:
        # 使用交易確保操作的原子性 (全部成功或全部失敗)
        cursor.execute("BEGIN TRANSACTION")
        
        # 1. 【關鍵新增】在插入新資料前，先刪除該月份的所有舊紀錄
        cursor.execute("DELETE FROM monthly_performance_bonus WHERE year = ? AND month = ?", (year, month))
        
        # 如果獎金 DataFrame 為空，就直接提交並結束
        if bonus_df.empty:
            conn.commit()
            return 0

        # 2. 準備要插入的新資料
        to_insert = [
            (int(row['employee_id']), year, month, float(row['bonus_amount']))
            for _, row in bonus_df.iterrows()
        ]
        
        # 3. 執行批次插入
        sql = "INSERT INTO monthly_performance_bonus (employee_id, year, month, bonus_amount) VALUES (?, ?, ?, ?)"
        cursor.executemany(sql, to_insert)
        
        # 提交交易，讓變更生效
        conn.commit()
        return len(to_insert)
        
    except Exception as e:
        # 如果過程中發生任何錯誤，就還原所有操作
        conn.rollback()
        raise e

def get_performance_bonus(conn, emp_id: int, year: int, month: int):
    """
    從資料庫讀取指定員工在該月份的績效獎金。
    """
    sql = "SELECT bonus_amount FROM monthly_performance_bonus WHERE employee_id = ? AND year = ? AND month = ?"
    result = conn.execute(sql, (emp_id, year, month)).fetchone()
    return result['bonus_amount'] if result else 0