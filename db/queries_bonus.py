# db/queries_bonus.py
"""
資料庫查詢：專門處理「業務獎金(monthly_bonus)」相關的資料庫操作。
"""
import pandas as pd

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