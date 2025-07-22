# db/db_manager.py
import sqlite3
import streamlit as st
from pathlib import Path

# --- 資料庫設定 ---
DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "hr_system.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

DATA_DIR.mkdir(exist_ok=True)

@st.cache_resource
def init_connection():
    """建立並快取資料庫連線。"""
    print(f"--- [INFO] Connecting to database at: {DB_PATH} ---")
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"資料庫連線失敗: {e}")
        return None

def init_db():
    """讀取 schema.sql 檔案並執行以建立所有資料表。"""
    if not SCHEMA_PATH.exists():
        print(f"錯誤: 找不到資料庫結構檔案 {SCHEMA_PATH}")
        return

    print("--- [INFO] Initializing database tables... ---")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        cursor.executescript(schema_sql)
        conn.commit()
        print("--- [SUCCESS] Database tables initialized successfully. ---")
    except sqlite3.Error as e:
        print(f"資料庫初始化時發生錯誤: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print(f"Database file is located at: {DB_PATH}")
    action = input("Type 'init' to create or update database tables from schema.sql: ").strip().lower()
    if action == 'init':
        init_db()
    else:
        print("Invalid action.")
