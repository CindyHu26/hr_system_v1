# db/queries_salary_items.py
"""
資料庫查詢：專門處理「薪資項目(salary_item)」的定義。
"""
import pandas as pd
import sqlite3

def get_all_salary_items(conn, active_only=False):
    """取得所有薪資項目。"""
    query = "SELECT * FROM salary_item ORDER BY type, id"
    if active_only:
        query = "SELECT * FROM salary_item WHERE is_active = 1"
    return pd.read_sql_query(query, conn)

def add_salary_item(conn, data: dict):
    """新增一個薪資項目。"""
    cursor = conn.cursor()
    sql = "INSERT INTO salary_item (name, type, is_active) VALUES (?, ?, ?)"
    cursor.execute(sql, (data['name'], data['type'], data['is_active']))
    conn.commit()

def update_salary_item(conn, item_id: int, data: dict):
    """更新一個現有的薪資項目。"""
    cursor = conn.cursor()
    sql = "UPDATE salary_item SET name = ?, type = ?, is_active = ? WHERE id = ?"
    cursor.execute(sql, (data['name'], data['type'], data['is_active'], item_id))
    conn.commit()

def delete_salary_item(conn, item_id: int):
    """刪除一個薪資項目。"""
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    try:
        sql = "DELETE FROM salary_item WHERE id = ?"
        cursor.execute(sql, (item_id,))
        conn.commit()
        return cursor.rowcount
    except sqlite3.IntegrityError:
        conn.rollback()
        raise Exception("此項目已被薪資單引用，無法刪除。您可以將其狀態改為「停用」。")

def get_item_types(conn):
    """獲取薪資項目的名稱與類型對應字典。"""
    return pd.read_sql("SELECT name, type FROM salary_item", conn).set_index('name')['type'].to_dict()

# --- [新增函式] ---
def batch_add_or_update_salary_items(conn, df: pd.DataFrame):
    """批次新增或更新薪資項目。"""
    cursor = conn.cursor()
    sql = """
    INSERT INTO salary_item (name, type, is_active) VALUES (?, ?, ?)
    ON CONFLICT(name) DO UPDATE SET
        type = excluded.type,
        is_active = excluded.is_active;
    """
    try:
        data_tuples = [
            (row['name'], row['type'], row['is_active'])
            for _, row in df.iterrows()
        ]
        cursor.executemany(sql, data_tuples)
        conn.commit()
        # 在SQLite中，executemany後的rowcount不準確，但此處回報受影響行數
        return {'inserted': cursor.rowcount, 'updated': 0} 
    except Exception as e:
        conn.rollback()
        raise e