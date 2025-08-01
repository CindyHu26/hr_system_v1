# db/queries_salary_records.py
import pandas as pd
from utils.helpers import get_monthly_dates
from db import queries_insurance as q_ins

def get_salary_report_for_editing(conn, year, month):
    start_date, end_date = get_monthly_dates(year, month)
    active_emp_df = pd.read_sql_query(
        "SELECT id as employee_id, name_ch as '員工姓名', hr_code as '員工編號' FROM employee WHERE (entry_date <= ?) AND (resign_date IS NULL OR resign_date = '' OR resign_date >= ?)",
        conn,
        params=(end_date, start_date)
    )
    if active_emp_df.empty:
        return pd.DataFrame(), {}

    salary_main_df = pd.read_sql_query("SELECT *, employer_pension_contribution as '勞退提撥' FROM salary WHERE year = ? AND month = ?", conn, params=(year, month))
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

    for item in list(item_types.keys()) + ['勞保費', '健保費']:
        if item not in report_df.columns:
            report_df[item] = 0
    report_df.fillna(0, inplace=True)
    
    report_df['勞健保'] = pd.to_numeric(report_df['勞保費'], errors='coerce').fillna(0) + pd.to_numeric(report_df['健保費'], errors='coerce').fillna(0)
    
    if '勞保費' in item_types: del item_types['勞保費']
    if '健保費' in item_types: del item_types['健保費']
    item_types['勞健保'] = 'deduction'

    earning_cols = [c for c, t in item_types.items() if t == 'earning' and c in report_df.columns]
    deduction_cols = [c for c, t in item_types.items() if t == 'deduction' and c in report_df.columns]
    
    draft_mask = report_df['status'] == 'draft'
    if draft_mask.any():
        report_df.loc[draft_mask, '應付總額'] = report_df.loc[draft_mask, earning_cols].sum(axis=1, numeric_only=True)
        report_df.loc[draft_mask, '應扣總額'] = report_df.loc[draft_mask, deduction_cols].sum(axis=1, numeric_only=True)
        report_df.loc[draft_mask, '實支金額'] = report_df.loc[draft_mask, '應付總額'] + report_df.loc[draft_mask, '應扣總額']
        report_df.loc[draft_mask, '匯入銀行'] = report_df.loc[draft_mask, '實支金額']
        report_df.loc[draft_mask, '現金'] = 0

    final_mask = report_df['status'] == 'final'
    if final_mask.any():
        report_df.loc[final_mask, '應付總額'] = report_df.loc[final_mask, 'total_payable']
        report_df.loc[final_mask, '應扣總額'] = report_df.loc[final_mask, 'total_deduction']
        report_df.loc[final_mask, '實支金額'] = report_df.loc[final_mask, 'net_salary']
        report_df.loc[final_mask, '匯入銀行'] = report_df.loc[final_mask, 'bank_transfer_amount']
        report_df.loc[final_mask, '現金'] = report_df.loc[final_mask, 'cash_amount']

    final_cols = ['employee_id', '員工姓名', '員工編號', 'status'] + list(item_types.keys()) + ['應付總額', '應扣總額', '實支金額', '匯入銀行', '現金', '勞退提撥']
    for col in final_cols:
        if col not in report_df.columns:
            report_df[col] = 0

    return report_df[final_cols].sort_values(by='員工編號').reset_index(drop=True), item_types

def save_salary_draft(conn, year, month, df: pd.DataFrame):
    cursor = conn.cursor()
    emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
    item_map = pd.read_sql("SELECT id, name FROM salary_item", conn).set_index('name')['id'].to_dict()
    
    for _, row in df.iterrows():
        emp_id = emp_map.get(row['員工姓名'])
        if not emp_id: continue

        pension_contribution = row.get('勞退提撥', 0)
        cursor.execute("""
            INSERT INTO salary (employee_id, year, month, status, employer_pension_contribution) 
            VALUES (?, ?, ?, 'draft', ?) 
            ON CONFLICT(employee_id, year, month) 
            DO UPDATE SET status = 'draft', employer_pension_contribution = excluded.employer_pension_contribution
            WHERE status != 'final'
        """, (emp_id, year, month, pension_contribution))
        
        salary_id = cursor.execute("SELECT id FROM salary WHERE employee_id = ? AND year = ? AND month = ?", (emp_id, year, month)).fetchone()[0]
        cursor.execute("DELETE FROM salary_detail WHERE salary_id = ?", (salary_id,))
        
        details_to_insert = []
        for k, v in row.items():
            if item_map.get(k) and v != 0:
                details_to_insert.append((salary_id, item_map.get(k), int(v)))

        if details_to_insert:
            cursor.executemany("INSERT INTO salary_detail (salary_id, salary_item_id, amount) VALUES (?, ?, ?)", details_to_insert)
    conn.commit()

def finalize_salary_records(conn, year, month, df: pd.DataFrame):
    """
    【V4 修正版】根據使用者指定的精確公式計算銀行與現金分配。
    """
    cursor = conn.cursor()
    emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
    
    for _, row in df.iterrows():
        emp_id = emp_map.get(row['員工姓名'])
        if not emp_id: continue
        
        base_salary = row.get('底薪', 0)
        overtime_1 = row.get('加班費(延長工時)', 0)
        overtime_2 = row.get('加班費(再延長工時)', 0)
        total_overtime = overtime_1 + overtime_2
        
        insurance_fee = row.get('勞健保', 0)
        personal_leave = row.get('事假', 0)
        sick_leave = row.get('病假', 0)
        late_fee = row.get('遲到', 0)
        early_leave_fee = row.get('早退', 0)
        
        # 注意：扣項的值本身是負數，所以直接相加即可
        bank_transfer_amount = base_salary + total_overtime + insurance_fee + personal_leave + sick_leave + late_fee + early_leave_fee

        net_salary = row.get('實支金額', 0)
        cash_amount = net_salary - bank_transfer_amount
        
        params = {
            'total_payable': row.get('應付總額', 0),
            'total_deduction': row.get('應扣總額', 0),
            'net_salary': net_salary,
            'bank_transfer_amount': bank_transfer_amount,
            'cash_amount': cash_amount,
            'status': 'final',
            'employer_pension_contribution': row.get('勞退提撥', 0),
            'employee_id': emp_id,
            'year': year,
            'month': month
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
    if not employee_ids: return 0
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in employee_ids)
    sql = f"UPDATE salary SET status = 'draft' WHERE year = ? AND month = ? AND employee_id IN ({placeholders}) AND status = 'final'"
    params = [year, month] + employee_ids
    cursor.execute(sql, params)
    conn.commit()
    return cursor.rowcount

def batch_upsert_salary_details(conn, data_to_upsert: list):
    if not data_to_upsert: return 0
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
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
    if not item_ids: return pd.DataFrame()
    placeholders = ','.join('?' for _ in item_ids)
    query = f"""
    SELECT
        e.hr_code as '員工編號', e.name_ch as '員工姓名', s.month, SUM(sd.amount) as monthly_total
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
    if not bonus_item_names: return 0, 0
    placeholders = ','.join('?' for _ in bonus_item_names)
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
    premium_query = """
    SELECT SUM(sd.amount)
    FROM salary_detail sd
    JOIN salary s ON sd.salary_id = s.id
    JOIN salary_item si ON sd.salary_item_id = si.id
    WHERE s.employee_id = ? AND s.year = ? AND si.name = '二代健保補充費';
    """
    premium_params = (employee_id, year)
    deducted_premium = cursor.execute(premium_query, premium_params).fetchone()[0] or 0
    return cumulative_bonus, abs(deducted_premium)

def update_salary_preview_data(conn, year: int, month: int, df_to_update: pd.DataFrame):
    if df_to_update.empty: return 0
    cursor = conn.cursor()
    salary_id_map = pd.read_sql("SELECT id, employee_id FROM salary WHERE year = ? AND month = ?", conn, params=(year, month)).set_index('employee_id')['id'].to_dict()
    item_map = pd.read_sql("SELECT id, name FROM salary_item", conn).set_index('name')['id'].to_dict()
    base_salary_id, labor_fee_id, health_fee_id = item_map.get('底薪'), item_map.get('勞保費'), item_map.get('健保費')
    updates_for_details, updates_for_pension = [], []
    for _, row in df_to_update.iterrows():
        emp_id = row['employee_id']
        salary_id = salary_id_map.get(emp_id)
        if not salary_id: continue
        if base_salary_id: updates_for_details.append((row['底薪'], salary_id, base_salary_id))
        if labor_fee_id: updates_for_details.append((row['勞保費'], salary_id, labor_fee_id))
        if health_fee_id: updates_for_details.append((row['健保費'], salary_id, health_fee_id))
        updates_for_pension.append((row['勞退提撥'], salary_id))
    try:
        detail_sql = """
        INSERT INTO salary_detail (amount, salary_id, salary_item_id) VALUES (?, ?, ?)
        ON CONFLICT(salary_id, salary_item_id) DO UPDATE SET amount = excluded.amount;
        """
        cursor.executemany(detail_sql, updates_for_details)
        pension_sql = "UPDATE salary SET employer_pension_contribution = ? WHERE id = ?"
        cursor.executemany(pension_sql, updates_for_pension)
        conn.commit()
        return len(df_to_update)
    except Exception as e:
        conn.rollback(); raise e