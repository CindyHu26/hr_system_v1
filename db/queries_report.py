# db/queries_report.py
import pandas as pd
from datetime import date

def get_employee_basic_data_for_report(conn):
    """
    查詢所有在職員工的基本資料，並包含他們最新的、且當前有效的加保公司。
    V3: 修正 latest_insurance 邏輯，確保只抓取當前有效的加保紀錄。
    """
    today_str = date.today().strftime('%Y-%m-%d')
    
    query = f"""
    WITH latest_insurance AS (
        SELECT
            employee_id,
            company_id,
            -- 核心修改：只在當前有效的加保紀錄中進行排序
            ROW_NUMBER() OVER(
                PARTITION BY employee_id 
                ORDER BY start_date DESC
            ) as rn
        FROM employee_company_history
        WHERE 
            -- 加保日必須在今天或今天之前
            date(start_date) <= date('{today_str}')
            -- 退保日必須是空的，或是還沒到
            AND (end_date IS NULL OR TRIM(end_date) = '' OR date(end_date) >= date('{today_str}'))
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
    WHERE (e.resign_date IS NULL OR TRIM(e.resign_date) = '')
    ORDER BY c.name, e.hr_code;
    """
    df = pd.read_sql_query(query, conn)
    return df