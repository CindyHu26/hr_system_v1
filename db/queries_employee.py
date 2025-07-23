# db/queries_employee.py
"""
資料庫查詢：專門處理「員工(employee)」與「公司(company)」相關的資料庫操作。
"""
import pandas as pd
from utils.helpers import get_monthly_dates

def get_all_employees(conn):
    """取得所有員工的資料，並按員工編號排序。"""
    return pd.read_sql_query("SELECT * FROM employee ORDER BY hr_code", conn)

def get_employee_map(conn):
    """獲取員工姓名與ID的對應表，並包含一個用於匹配的「淨化姓名」。"""
    df = pd.read_sql_query("SELECT id as employee_id, name_ch FROM employee", conn)
    df['clean_name'] = df['name_ch'].str.replace(r'\s+', '', regex=True)
    return df
    
def get_active_employees_for_month(conn, year, month):
    """查詢指定月份仍在職的員工。"""
    start_date, end_date = get_monthly_dates(year, month)
    query = """
    SELECT e.id, e.name_ch, e.hr_code FROM employee e
    WHERE (e.entry_date IS NOT NULL AND e.entry_date <= ?) 
      AND (e.resign_date IS NULL OR e.resign_date >= ?)
    ORDER BY e.hr_code ASC
    """
    # 使用 fetchall() 確保返回的是與舊版相容的格式
    return conn.execute(query, (end_date, start_date)).fetchall()
    
def get_all_companies(conn):
    """取得所有公司的資料，並按公司名稱排序。"""
    return pd.read_sql_query("SELECT * FROM company ORDER BY name", conn)