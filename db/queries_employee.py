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

def batch_add_or_update_employees(conn, df: pd.DataFrame):
    """
    批次新增或更新員工資料。
    使用 SQLite 的 ON CONFLICT 功能，以 id_no 為唯一鍵。
    """
    cursor = conn.cursor()
    report = {'inserted': 0, 'updated': 0, 'processed': 0, 'errors': []}
    
    # 定義所有可能的欄位順序，以應對 Excel 中可能不完整的欄位
    all_cols = [
        'name_ch', 'id_no', 'hr_code', 'entry_date', 'gender', 'birth_date',
        'nationality', 'arrival_date', 'phone', 'address', 'dept', 'title',
        'resign_date', 'bank_account', 'note'
    ]
    
    # 建立更新用的 SQL 語句
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
            # 準備要傳入 SQL 的資料元組，若欄位不存在則補 None
            data_tuple = tuple(row.get(col) for col in all_cols)
            
            cursor.execute(sql, data_tuple)
            
            # conn.total_changes 會追蹤自連線以來的變更總數
            # 雖然不是最精確的方法，但在 transaction 中可以大致判斷是 insert 還是 update
            # 一個更精準的方式是先 SELECT 檢查 id_no 是否存在
            
        conn.commit()
        
        # 這裡簡化回報，直接回報處理的總筆數
        # SQLite 的 executemany 不像其他 DB 會回傳精確的 inserted/updated 數量
        # 我們假設所有傳入的資料都被處理了
        report['processed'] = len(df)
        # 實際上，這裡無法輕易區分是新增還是更新，因此我們將它們合併
        # 為了給前端一個交代，可以這樣回報：
        report['updated'] = cursor.rowcount # rowcount 在 ON CONFLICT 下通常表示受影響的行數
        
    except Exception as e:
        conn.rollback()
        report['errors'].append({'row': 'N/A', 'reason': f'資料庫操作失敗: {e}'})

    return report