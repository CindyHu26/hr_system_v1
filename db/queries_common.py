# db/queries_common.py
"""
資料庫查詢：包含通用的、可重複使用的 CRUD (Create, Read, Update, Delete) 函式。
"""
import pandas as pd

def get_all(conn, table_name, order_by="id"):
    """通用函式：取得一個資料表中的所有紀錄。"""
    return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY {order_by}", conn)

def get_by_id(conn, table_name, record_id):
    """通用函式：根據 ID 取得單筆紀錄。"""
    df = pd.read_sql_query(f"SELECT * FROM {table_name} WHERE id = ?", conn, params=(record_id,))
    # 使用 .to_dict('records')[0] 確保回傳的是字典，而不是 DataFrame 的 Series
    return df.to_dict('records')[0] if not df.empty else None

def add_record(conn, table_name, data: dict):
    """通用函式：在指定的資料表中新增一筆紀錄。"""
    cursor = conn.cursor()
    cols = ', '.join(data.keys())
    placeholders = ', '.join('?' for _ in data)
    sql = f'INSERT INTO {table_name} ({cols}) VALUES ({placeholders})'
    cursor.execute(sql, list(data.values()))
    conn.commit()
    return cursor.lastrowid

def update_record(conn, table_name, record_id, data: dict):
    """通用函式：根據 ID 更新一筆紀錄。"""
    cursor = conn.cursor()
    updates = ', '.join([f"{key} = ?" for key in data.keys()])
    sql = f'UPDATE {table_name} SET {updates} WHERE id = ?'
    cursor.execute(sql, list(data.values()) + [record_id])
    conn.commit()
    return cursor.rowcount

def delete_record(conn, table_name, record_id):
    """通用函式：根據 ID 刪除一筆紀錄。"""
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute(f'DELETE FROM {table_name} WHERE id = ?', (record_id,))
    conn.commit()
    return cursor.rowcount