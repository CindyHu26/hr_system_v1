# db/queries_allowances.py
"""
資料庫查詢：專門處理員工的「常態薪資項設定(employee_salary_item)」，如固定津貼/扣款。
"""
import pandas as pd

def get_employee_recurring_items(conn, emp_id, year, month):
    """
    【V2 修正版】查詢單一員工在指定月份有效的常態薪資設定。
    - 使用 strftime 強化日期比較與排序的穩定性，確保永遠抓取到最新紀錄。
    """
    from utils.helpers import get_monthly_dates
    month_start, month_end = get_monthly_dates(year, month)
    
    sql = """
    WITH RankedItems AS (
        SELECT
            si.name,
            esi.amount,
            si.type,
            ROW_NUMBER() OVER(
                PARTITION BY esi.salary_item_id 
                ORDER BY strftime('%Y-%m-%d', esi.start_date) DESC
            ) as rn
        FROM employee_salary_item esi
        JOIN salary_item si ON esi.salary_item_id = si.id
        WHERE 
            esi.employee_id = ?
            AND strftime('%Y-%m-%d', esi.start_date) <= strftime('%Y-%m-%d', ?)
            AND (
                esi.end_date IS NULL OR 
                esi.end_date = '' OR 
                strftime('%Y-%m-%d', esi.end_date) >= strftime('%Y-%m-%d', ?)
            )
    )
    SELECT name, amount, type
    FROM RankedItems
    WHERE rn = 1;
    """
    return conn.execute(sql, (emp_id, month_end, month_start)).fetchall()

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
    ORDER BY e.hr_code, esi.start_date DESC
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
    return {
        amount: group[['employee_id', 'name_ch']].to_dict('records') 
        for amount, group in df.groupby('amount')
    }

def batch_add_or_update_employee_salary_items(conn, employee_ids, salary_item_id, amount, start_date, end_date, note):
    """批次新增或更新員工的常態薪資設定"""
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        # 尋找現有紀錄並更新或插入
        for emp_id in employee_ids:
            cursor.execute("""
                INSERT INTO employee_salary_item (employee_id, salary_item_id, amount, start_date, end_date, note)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(employee_id, salary_item_id, start_date) DO UPDATE SET
                    amount = excluded.amount,
                    end_date = excluded.end_date,
                    note = excluded.note;
            """, (emp_id, salary_item_id, amount, start_date, end_date, note))

        conn.commit()
        return len(employee_ids)
    except Exception as e:
        conn.rollback()
        raise e

def batch_upsert_allowances(conn, df: pd.DataFrame):
    """從 DataFrame 批次新增或更新員工常態薪資項。"""
    cursor = conn.cursor()
    report = {'inserted': 0, 'updated': 0, 'failed': 0, 'errors': []}
    
    emp_map = pd.read_sql("SELECT name_ch, id FROM employee", conn).set_index('name_ch')['id'].to_dict()
    item_map = pd.read_sql("SELECT name, id FROM salary_item", conn).set_index('name')['id'].to_dict()

    sql = """
    INSERT INTO employee_salary_item (employee_id, salary_item_id, amount, start_date, end_date, note)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(employee_id, salary_item_id, start_date) DO UPDATE SET
        amount = excluded.amount,
        end_date = excluded.end_date,
        note = excluded.note;
    """
    
    data_to_upsert = []
    for index, row in df.iterrows():
        emp_id = emp_map.get(row['name_ch'])
        item_id = item_map.get(row['item_name'])

        if not emp_id:
            report['errors'].append({'row': index + 2, 'reason': f"找不到員工 '{row['name_ch']}'"})
            continue
        if not item_id:
            report['errors'].append({'row': index + 2, 'reason': f"找不到薪資項目 '{row['item_name']}'"})
            continue
        
        data_to_upsert.append((
            emp_id, item_id, row['amount'],
            row['start_date'], row.get('end_date'), row.get('note')
        ))

    if data_to_upsert:
        try:
            cursor.executemany(sql, data_to_upsert)
            conn.commit()
            report['updated'] = cursor.rowcount 
        except Exception as e:
            conn.rollback()
            report['errors'].append({'row': 'N/A', 'reason': f'資料庫操作失敗: {e}'})
    
    report['failed'] = len(df) - len(data_to_upsert)
    return report

def get_monthly_adjustments(conn, year: int, month: int):
    """查詢特定月份的單次薪資調整紀錄。"""
    from utils.helpers import get_monthly_dates
    start_date, end_date = get_monthly_dates(year, month)
    
    query = """
    SELECT 
        esi.id, 
        e.name_ch as '員工姓名', 
        si.name as '項目名稱', 
        si.type as '類型',
        esi.amount as '金額',
        esi.note as '備註'
    FROM employee_salary_item esi
    JOIN employee e ON esi.employee_id = e.id 
    JOIN salary_item si ON esi.salary_item_id = si.id 
    WHERE esi.start_date = ? AND esi.end_date = ?
    ORDER BY e.hr_code
    """
    return pd.read_sql_query(query, conn, params=(start_date, end_date))