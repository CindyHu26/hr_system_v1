# db/queries_employee.py
"""
資料庫查詢：專門處理「員工(employee)」與「公司(company)」相關的資料庫操作。
也包含一些通用的 CRUD (Create, Read, Update, Delete) 函式。
"""
import pandas as pd

# --- 通用 CRUD ---

def get_all(conn, table_name, order_by="id"):
    """通用函式：取得一個資料表中的所有紀錄。"""
    return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY {order_by}", conn)

def get_by_id(conn, table_name, record_id):
    """通用函式：根據 ID 取得單筆紀錄。"""
    df = pd.read_sql_query(f"SELECT * FROM {table_name} WHERE id = ?", conn, params=(record_id,))
    return df.iloc[0] if not df.empty else None

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
    # 啟用外鍵約束，確保刪除時的資料完整性
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute(f'DELETE FROM {table_name} WHERE id = ?', (record_id,))
    conn.commit()
    return cursor.rowcount

# --- 員工(Employee) 相關查詢 ---

def get_all_employees(conn):
    """取得所有員工的資料，並按員工編號排序。"""
    return pd.read_sql_query("SELECT * FROM employee ORDER BY hr_code", conn)

def get_employee_map(conn):
    """獲取員工姓名與ID的對應表，並包含一個用於匹配的「淨化姓名」。"""
    df = pd.read_sql_query("SELECT id as employee_id, name_ch FROM employee", conn)
    # 移除姓名中的所有空格，方便後續進行匹配
    df['clean_name'] = df['name_ch'].str.replace(r'\s+', '', regex=True)
    return df

# --- 公司(Company) 相關查詢 ---

def get_all_companies(conn):
    """取得所有公司的資料，並按公司名稱排序。"""
    return pd.read_sql_query("SELECT * FROM company ORDER BY name", conn)