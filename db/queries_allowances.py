# db/queries_allowances.py
"""
資料庫查詢：專門處理員工的「常態薪資項設定(employee_salary_item)」，如固定津貼/扣款。
"""
import pandas as pd

def get_employee_recurring_items(conn, emp_id):
    """查詢單一員工的所有常態薪資設定。"""
    sql = "SELECT si.name, esi.amount, si.type FROM employee_salary_item esi JOIN salary_item si ON esi.salary_item_id = si.id WHERE esi.employee_id = ?"
    return conn.execute(sql, (emp_id,)).fetchall()

def get_all_employee_salary_items(conn):
    """查詢所有員工的所有常態薪資設定，用於總覽頁面。"""
    query = """
    SELECT 
        esi.id, 
        e.id as employee_id, 
        e.name_ch as '員工姓名', 
        si.id as salary_item_id, 
        si.name as '項目名稱', 
        si.type as '類型', 
        esi.amount as '金額', 
        esi.start_date as '生效日', 
        esi.end_date as '結束日', 
        esi.note as '備註' 
    FROM employee_salary_item esi 
    JOIN employee e ON esi.employee_id = e.id 
    JOIN salary_item si ON esi.salary_item_id = si.id 
    ORDER BY e.name_ch, si.name
    """
    return pd.read_sql_query(query, conn)

def get_settings_grouped_by_amount(conn, salary_item_id):
    """為批次修改功能，查詢特定薪資項目下，按金額分組的員工列表。"""
    if not salary_item_id: return {}
    query = """
    SELECT 
        esi.amount, 
        e.id as employee_id, 
        e.name_ch 
    FROM employee_salary_item esi 
    JOIN employee e ON esi.employee_id = e.id 
    WHERE esi.salary_item_id = ? 
    ORDER BY esi.amount, e.name_ch
    """
    df = pd.read_sql_query(query, conn, params=(int(salary_item_id),))
    if df.empty:
        return {}
    # 將查詢結果處理成 {金額: [員工列表]} 的字典格式
    return {
        amount: group[['employee_id', 'name_ch']].to_dict('records') 
        for amount, group in df.groupby('amount')
    }

def batch_add_or_update_employee_salary_items(conn, employee_ids, salary_item_id, amount, start_date, end_date, note):
    """批次新增或更新員工的常態薪資設定（如果已存在就覆蓋）。"""
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        # 先刪除這些員工已有的相同項目設定
        placeholders = ','.join('?' for _ in employee_ids)
        cursor.execute(f"DELETE FROM employee_salary_item WHERE salary_item_id = ? AND employee_id IN ({placeholders})", [salary_item_id] + employee_ids)
        
        # 再批次插入新的設定
        data_tuples = [(emp_id, salary_item_id, amount, start_date, end_date, note) for emp_id in employee_ids]
        cursor.executemany("INSERT INTO employee_salary_item (employee_id, salary_item_id, amount, start_date, end_date, note) VALUES (?, ?, ?, ?, ?, ?)", data_tuples)
        
        conn.commit()
        return len(data_tuples)
    except Exception as e:
        conn.rollback()
        raise e