# db/queries_config.py
import pandas as pd

def get_minimum_wage_for_year(conn, year: int):
    """查詢指定年份的有效基本工資。如果當年沒有，則找最近的一年。"""
    sql = """
    SELECT wage FROM minimum_wage_history 
    WHERE year <= ? 
    ORDER BY year DESC 
    LIMIT 1
    """
    result = conn.execute(sql, (year,)).fetchone()
    return result['wage'] if result else 0

def get_all_minimum_wages(conn):
    """取得所有歷史基本工資紀錄。"""
    return pd.read_sql_query("SELECT * FROM minimum_wage_history ORDER BY year DESC", conn)

def add_or_update_minimum_wage(conn, year: int, wage: int, effective_date, note: str):
    """新增或更新指定年份的基本工資。"""
    sql = """
    INSERT INTO minimum_wage_history (year, wage, effective_date, note)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(year) DO UPDATE SET
        wage = excluded.wage,
        effective_date = excluded.effective_date,
        note = excluded.note;
    """
    cursor = conn.cursor()
    cursor.execute(sql, (year, wage, effective_date, note))
    conn.commit()
    return cursor.rowcount

def get_all_configs(conn):
    """取得所有系統通用參數設定。"""
    df = pd.read_sql_query("SELECT key, value FROM system_config", conn)
    return dict(zip(df['key'], df['value']))

def batch_update_configs(conn, data_tuples: list):
    """批次更新或插入系統通用參數。"""
    sql = """
    INSERT INTO system_config (key, value) VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET
        value = excluded.value,
        updated_at = CURRENT_TIMESTAMP;
    """
    cursor = conn.cursor()
    cursor.executemany(sql, data_tuples)
    conn.commit()