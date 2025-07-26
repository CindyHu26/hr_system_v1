# db/queries_salary_records.py
"""
資料庫查詢：專門處理每月的「薪資單紀錄(salary)」的儲存、讀取與狀態管理。
"""
import pandas as pd
from utils.helpers import get_monthly_dates

def get_salary_report_for_editing(conn, year, month):
    """
    薪資報表產生器: 從資料庫讀取資料，並處理草稿/定版邏輯後呈現。
    這是薪資頁面最關鍵的查詢函式。
    """
    start_date, end_date = get_monthly_dates(year, month)
    active_emp_df = pd.read_sql_query(
        "SELECT id as employee_id, name_ch as '員工姓名', hr_code as '員工編號' FROM employee WHERE (entry_date <= ?) AND (resign_date IS NULL OR resign_date >= ?)",
        conn,
        params=(end_date, start_date)
    )
    if active_emp_df.empty:
        return pd.DataFrame(), {}

    salary_main_df = pd.read_sql_query("SELECT * FROM salary WHERE year = ? AND month = ?", conn, params=(year, month))
    details_query = """
    SELECT s.employee_id, si.name as item_name, sd.amount
    FROM salary_detail sd
    JOIN salary_item si ON sd.salary_item_id = si.id
    JOIN salary s ON sd.salary_id = s.id
    WHERE s.year = ? AND s.month = ?
    """
    details_df = pd.read_sql_query(details_query, conn, params=(year, month))

    pivot_details = pd.DataFrame()
    if not details_df.empty:
        pivot_details = details_df.pivot_table(index='employee_id', columns='item_name', values='amount').reset_index()

    report_df = pd.merge(active_emp_df, salary_main_df, on='employee_id', how='left')
    if not pivot_details.empty:
        report_df = pd.merge(report_df, pivot_details, on='employee_id', how='left')

    report_df['status'] = report_df['status'].fillna('draft')
    item_types = pd.read_sql("SELECT name, type FROM salary_item", conn).set_index('name')['type'].to_dict()

    for item in item_types.keys():
        if item not in report_df.columns: report_df[item] = 0
    report_df.fillna(0, inplace=True)

    earning_cols = [c for c, t in item_types.items() if t == 'earning' and c in report_df.columns]
    deduction_cols = [c for c, t in item_types.items() if t == 'deduction' and c in report_df.columns]

    draft_mask = report_df['status'] == 'draft'
    if draft_mask.any():
        report_df.loc[draft_mask, '應付總額'] = report_df.loc[draft_mask, earning_cols].sum(axis=1, numeric_only=True)
        report_df.loc[draft_mask, '應扣總額'] = report_df.loc[draft_mask, deduction_cols].sum(axis=1, numeric_only=True)
        report_df.loc[draft_mask, '實發薪資'] = report_df.loc[draft_mask, '應付總額'] + report_df.loc[draft_mask, '應扣總額']
        report_df.loc[draft_mask, '匯入銀行'] = report_df.loc[draft_mask, '實發薪資']
        report_df.loc[draft_mask, '現金'] = 0

    final_mask = report_df['status'] == 'final'
    if final_mask.any():
        report_df.loc[final_mask, '應付總額'] = report_df.loc[final_mask, 'total_payable']
        report_df.loc[final_mask, '應扣總額'] = report_df.loc[final_mask, 'total_deduction']
        report_df.loc[final_mask, '實發薪資'] = report_df.loc[final_mask, 'net_salary']
        report_df.loc[final_mask, '匯入銀行'] = report_df.loc[final_mask, 'bank_transfer_amount']
        report_df.loc[final_mask, '現金'] = report_df.loc[final_mask, 'cash_amount']

    final_cols = ['employee_id', '員工姓名', '員工編號', 'status'] + list(item_types.keys()) + ['應付總額', '應扣總額', '實發薪資', '匯入銀行', '現金']
    for col in final_cols:
        if col not in report_df.columns: report_df[col] = 0

    return report_df[final_cols].sort_values(by='員工編號').reset_index(drop=True), item_types

def save_salary_draft(conn, year, month, df: pd.DataFrame):
    cursor = conn.cursor()
    emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
    item_map = pd.read_sql("SELECT id, name FROM salary_item", conn).set_index('name')['id'].to_dict()
    
    for _, row in df.iterrows():
        emp_id = emp_map.get(row['員工姓名'])
        if not emp_id: continue

        # [核心修改] 儲存草稿時，一併寫入勞退提撥金額
        pension_contribution = row.get('勞退提撥(公司負擔)', 0)
        cursor.execute("""
            INSERT INTO salary (employee_id, year, month, status, employer_pension_contribution) 
            VALUES (?, ?, ?, 'draft', ?) 
            ON CONFLICT(employee_id, year, month) 
            DO UPDATE SET status = 'draft', employer_pension_contribution = excluded.employer_pension_contribution
            WHERE status != 'final'
        """, (emp_id, year, month, pension_contribution))
        
        salary_id = cursor.execute("SELECT id FROM salary WHERE employee_id = ? AND year = ? AND month = ?", (emp_id, year, month)).fetchone()[0]
        cursor.execute("DELETE FROM salary_detail WHERE salary_id = ?", (salary_id,))
        details_to_insert = [(salary_id, item_map.get(k), int(v)) for k, v in row.items() if item_map.get(k) and v != 0]
        if details_to_insert:
            cursor.executemany("INSERT INTO salary_detail (salary_id, salary_item_id, amount) VALUES (?, ?, ?)", details_to_insert)
    conn.commit()


def finalize_salary_records(conn, year, month, df: pd.DataFrame):
    """將薪資紀錄定版，寫入總額與支付方式等最終資訊。"""
    cursor = conn.cursor()
    emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
    for _, row in df.iterrows():
        emp_id = emp_map.get(row['員工姓名'])
        if not emp_id: continue
        params = {
            # ...
            'cash_amount': row.get('現金', 0), 'status': 'final',
            'employer_pension_contribution': row.get('勞退提撥(公司負擔)', 0),
            'employee_id': emp_id, 'year': year, 'month': month
        }
        cursor.execute("""
            UPDATE salary SET
            total_payable = :total_payable, total_deduction = :total_deduction,
            net_salary = :net_salary, bank_transfer_amount = :bank_transfer_amount,
            cash_amount = :cash_amount, status = :status,
            employer_pension_contribution = :employer_pension_contribution
            WHERE employee_id = :employee_id AND year = :year AND month = :month
        """, params)
    conn.commit()

def revert_salary_to_draft(conn, year, month, employee_ids: list):
    """將已定版的薪資紀錄恢復為草稿狀態。"""
    if not employee_ids: return 0
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in employee_ids)
    sql = f"UPDATE salary SET status = 'draft' WHERE year = ? AND month = ? AND employee_id IN ({placeholders}) AND status = 'final'"
    params = [year, month] + employee_ids
    cursor.execute(sql, params)
    conn.commit()
    return cursor.rowcount

def batch_upsert_salary_details(conn, data_to_upsert: list):
    """批次更新或插入薪資明細 (Upsert)。"""
    if not data_to_upsert: return 0
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        # 確保 unique index 存在，這是 ON CONFLICT 的前提
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_salary_item ON salary_detail (salary_id, salary_item_id);")
        sql = """
            INSERT INTO salary_detail (salary_id, salary_item_id, amount) VALUES (?, ?, ?)
            ON CONFLICT(salary_id, salary_item_id) DO UPDATE SET amount = excluded.amount;
        """
        cursor.executemany(sql, data_to_upsert)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback(); raise e

def get_annual_salary_summary_data(conn, year: int, item_ids: list):
    """獲取年度薪資總表的原始資料。"""
    if not item_ids:
        return pd.DataFrame()
    placeholders = ','.join('?' for _ in item_ids)
    query = f"""
    SELECT
        e.hr_code as '員工編號',
        e.name_ch as '員工姓名',
        s.month,
        SUM(sd.amount) as monthly_total
    FROM salary_detail sd
    JOIN salary s ON sd.salary_id = s.id
    JOIN employee e ON s.employee_id = e.id
    WHERE s.year = ? AND sd.salary_item_id IN ({placeholders})
    GROUP BY e.id, s.month
    ORDER BY e.hr_code, s.month;
    """
    params = [year] + item_ids
    return pd.read_sql_query(query, conn, params=params)

def get_cumulative_bonus_for_year(conn, employee_id: int, year: int, bonus_item_names: list):
    """
    查詢指定員工在特定年度中，所有獎金類項目的累計總額。
    同時也會查詢已扣繳的二代健保補充費總額。
    """
    if not bonus_item_names:
        return 0, 0

    placeholders = ','.join('?' for _ in bonus_item_names)
    
    # 查詢累計獎金
    bonus_query = f"""
    SELECT SUM(sd.amount)
    FROM salary_detail sd
    JOIN salary s ON sd.salary_id = s.id
    JOIN salary_item si ON sd.salary_item_id = si.id
    WHERE s.employee_id = ? AND s.year = ? AND si.name IN ({placeholders});
    """
    bonus_params = [employee_id, year] + bonus_item_names
    cursor = conn.cursor()
    cumulative_bonus = cursor.execute(bonus_query, bonus_params).fetchone()[0] or 0

    # 查詢已扣補充費
    premium_query = """
    SELECT SUM(sd.amount)
    FROM salary_detail sd
    JOIN salary s ON sd.salary_id = s.id
    JOIN salary_item si ON sd.salary_item_id = si.id
    WHERE s.employee_id = ? AND s.year = ? AND si.name = '二代健保補充費';
    """
    premium_params = (employee_id, year)
    deducted_premium = cursor.execute(premium_query, premium_params).fetchone()[0] or 0
    
    # 因為扣款是負數，所以要取絕對值
    return cumulative_bonus, abs(deducted_premium)