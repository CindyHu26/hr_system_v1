# db/queries_report.py
import pandas as pd
from datetime import date

def get_employee_basic_data_for_report(conn):
    """
    查詢所有在職員工的基本資料，並包含他們最新的加保公司。
    V2: 修正篩選在職員工的邏輯，使其更穩健。
    """
    query = """
    WITH latest_insurance AS (
        SELECT
            employee_id,
            company_id,
            ROW_NUMBER() OVER(PARTITION BY employee_id ORDER BY start_date DESC) as rn
        FROM employee_company_history
    )
    SELECT
        e.id,
        c.name as '加保公司',
        e.name_ch as '員工姓名',
        e.id_no as '身分證字號',
        e.entry_date as '到職日',
        e.birth_date as '生日'
    FROM employee e
    LEFT JOIN latest_insurance li ON e.id = li.employee_id AND li.rn = 1
    LEFT JOIN company c ON li.company_id = c.id
    /* 使用 TRIM 函數來處理可能存在的空格，讓判斷更準確 */
    WHERE (e.resign_date IS NULL OR TRIM(e.resign_date) = '')
    ORDER BY c.name, e.hr_code;
    """
    df = pd.read_sql_query(query, conn)
    return df