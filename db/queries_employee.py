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
    """查詢指定月份仍在職的員工，並包含健保狀態與職稱。"""
    start_date, end_date = get_monthly_dates(year, month)
    
    query = """
    SELECT e.id, e.name_ch, e.hr_code, e.entry_date, e.nationality,
           e.nhi_status, e.nhi_status_expiry, e.title, e.dept
    FROM employee e
    WHERE (e.entry_date IS NOT NULL AND e.entry_date <= ?) 
      AND (e.resign_date IS NULL OR e.resign_date = '' OR e.resign_date >= ?)
    ORDER BY e.hr_code ASC
    """
    return conn.execute(query, (end_date, start_date)).fetchall()
    
def get_all_companies(conn):
    """取得所有公司的資料，並按公司名稱排序。"""
    return pd.read_sql_query("SELECT * FROM company ORDER BY name", conn)

def batch_add_or_update_employees(conn, df: pd.DataFrame):
    """
    批次新增或更新員工資料。
    """
    cursor = conn.cursor()
    report = {'inserted': 0, 'updated': 0, 'processed': 0, 'errors': []}
    
    all_cols = [
        'name_ch', 'id_no', 'hr_code', 'entry_date', 'gender', 'birth_date',
        'nationality', 'arrival_date', 'phone', 'address', 'dept', 'title',
        'resign_date', 'bank_account', 'note', 'nhi_status', 'nhi_status_expiry'
    ]
    
    update_cols = [col for col in all_cols if col != 'id_no']
    update_clause = ", ".join([f"{col} = excluded.{col}" for col in update_cols])

    sql = f"""
    INSERT INTO employee ({', '.join(all_cols)})
    VALUES ({', '.join(['?'] * len(all_cols))})
    ON CONFLICT(id_no) DO UPDATE SET
        {update_clause};
    """

    try:
        cursor.execute("BEGIN TRANSACTION")
        
        for index, row in df.iterrows():
            data_tuple = tuple(row.get(col) for col in all_cols)
            cursor.execute(sql, data_tuple)
            
        conn.commit()
        report['processed'] = len(df)
        report['updated'] = cursor.rowcount
        
    except Exception as e:
        conn.rollback()
        report['errors'].append({'row': 'N/A', 'reason': f'資料庫操作失敗: {e}'})

    return report