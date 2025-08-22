# db/queries_salary_read.py
"""
資料庫查詢：專門處理「讀取」薪資相關紀錄。
"""
import pandas as pd
from utils.helpers import get_monthly_dates

def get_salary_report_for_editing(conn, year, month):
    """
    V3: 修正版
    - 確保「勞保費」、「健保費」與加總後的「勞健保」欄位都存在於最終的 DataFrame 中，
      以解決 data_editor 儲存後資料遺失的問題。
    """
    start_date, end_date = get_monthly_dates(year, month)
    active_emp_df = pd.read_sql_query(
        "SELECT id as employee_id, name_ch as '員工姓名', hr_code as '員工編號' FROM employee WHERE (entry_date <= ?) AND (resign_date IS NULL OR resign_date = '' OR resign_date >= ?)",
        conn,
        params=(end_date, start_date)
    )
    if active_emp_df.empty:
        return pd.DataFrame(), {}

    salary_main_df = pd.read_sql_query("""
        SELECT
            employee_id, status, note,
            total_payable as '應付總額',
            total_deduction as '應扣總額',
            net_salary as '實支金額',
            bank_transfer_amount as '匯入銀行',
            cash_amount as '現金',
            employer_pension_contribution as '勞退提撥'
        FROM salary
        WHERE year = ? AND month = ?
    """, conn, params=(year, month))

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
        pivot_details = details_df.pivot_table(index='employee_id', columns='item_name', values='amount', aggfunc='sum').reset_index()

    report_df = pd.merge(active_emp_df, salary_main_df, on='employee_id', how='left')
    if not pivot_details.empty:
        report_df = pd.merge(report_df, pivot_details, on='employee_id', how='left')

    report_df['status'] = report_df['status'].fillna('draft')
    item_types = pd.read_sql("SELECT name, type FROM salary_item", conn).set_index('name')['type'].to_dict()

    all_items = list(item_types.keys())
    for item in all_items:
        if item not in report_df.columns:
            report_df[item] = 0

    # 確保先填補缺失值再進行計算
    report_df.fillna(0, inplace=True)
    
    # 【核心修正】在這裡確保 '勞保費' 和 '健保費' 欄位存在且為數字
    report_df['勞保費'] = pd.to_numeric(report_df.get('勞保費', 0), errors='coerce').fillna(0)
    report_df['健保費'] = pd.to_numeric(report_df.get('健保費', 0), errors='coerce').fillna(0)
    report_df['勞健保'] = report_df['勞保費'] + report_df['健保費']

    core_info = ['employee_id', '員工姓名', '員工編號', 'status']
    earning_cols = [c for c, t in item_types.items() if t == 'earning' and c in report_df.columns]
    deduction_cols = [c for c, t in item_types.items() if t == 'deduction' and c in report_df.columns]
    
    earning_order = ['底薪', '加班費(延長工時)', '加班費(再延長工時)']
    other_earnings = sorted([c for c in earning_cols if c not in earning_order])
    all_earnings = earning_order + other_earnings
    
    # 【核心修正】重新定義扣除項的順序，確保三個欄位都包含在內
    deduction_order = ['勞保費', '健保費', '勞健保', '遲到', '早退', '事假', '病假']
    # 這裡的邏輯也要跟著調整，避免重複包含
    other_deductions = sorted([c for c in deduction_cols if c not in deduction_order])
    all_deductions = deduction_order + other_deductions
    
    summary_cols = ['應付總額', '應扣總額', '實支金額', '匯入銀行', '現金', '勞退提撥', 'note']
    
    final_cols_ordered = core_info + all_earnings + all_deductions + summary_cols
    
    for col in final_cols_ordered:
        if col not in report_df.columns:
            report_df[col] = 0 if col not in ['note', 'status', '員工姓名', '員工編號'] else ''
            
    report_df.rename(columns={'note': '備註'}, inplace=True)
    if 'note' in final_cols_ordered:
        final_cols_ordered[final_cols_ordered.index('note')] = '備註'
    
    # 確保最終 DataFrame 的欄位是唯一的
    final_cols_ordered_unique = list(dict.fromkeys(final_cols_ordered))

    return report_df[final_cols_ordered_unique].sort_values(by='員工編號').reset_index(drop=True), item_types

def get_annual_salary_summary_data(conn, year: int, item_ids: list, include_id_no: bool = False):
    """
    (V2) 產生年度薪資總表的基礎查詢。
    - 新增 include_id_no 參數以決定是否連帶查詢身分證號。
    - 只查詢 status = 'final' 的薪資紀錄。
    """
    if not item_ids: return pd.DataFrame()
    placeholders = ','.join('?' for _ in item_ids)
    
    # 根據參數決定要查詢的欄位
    select_cols = "e.hr_code as '員工編號', e.name_ch as '員工姓名'"
    if include_id_no:
        select_cols += ", e.id_no as '身分證字號'"
    
    query = f"""
    SELECT
        {select_cols}, s.month, SUM(sd.amount) as monthly_total
    FROM salary_detail sd
    JOIN salary s ON sd.salary_id = s.id
    JOIN employee e ON s.employee_id = e.id
    WHERE s.year = ? AND sd.salary_item_id IN ({placeholders}) AND s.status = 'final'
    GROUP BY e.id, s.month
    ORDER BY e.hr_code, s.month;
    """
    params = [year] + item_ids
    return pd.read_sql_query(query, conn, params=params)

def get_cumulative_bonus_for_period(conn, employee_id: int, year: int, start_month: int, end_month: int, bonus_item_names: list):
    if not bonus_item_names:
        return 0, 0
        
    placeholders = ','.join('?' for _ in bonus_item_names)
    
    bonus_query = f"""
    SELECT SUM(sd.amount)
    FROM salary_detail sd
    JOIN salary s ON sd.salary_id = s.id
    JOIN salary_item si ON sd.salary_item_id = si.id
    WHERE s.employee_id = ? AND s.year = ? AND s.month BETWEEN ? AND ? AND si.name IN ({placeholders});
    """
    bonus_params = [employee_id, year, start_month, end_month] + bonus_item_names
    cursor = conn.cursor()
    cumulative_bonus = cursor.execute(bonus_query, bonus_params).fetchone()[0] or 0
    
    premium_query = """
    SELECT SUM(sd.amount)
    FROM salary_detail sd
    JOIN salary s ON sd.salary_id = s.id
    JOIN salary_item si ON sd.salary_item_id = si.id
    WHERE s.employee_id = ? AND s.year = ? AND s.month BETWEEN ? AND ? AND si.name = '二代健保(高額獎金)';
    """
    premium_params = (employee_id, year, start_month, end_month)
    deducted_premium = cursor.execute(premium_query, premium_params).fetchone()[0] or 0
    
    return cumulative_bonus, abs(deducted_premium)

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
    WHERE s.employee_id = ? AND s.year = ? AND si.name = '二代健保(高額獎金)';
    """
    premium_params = (employee_id, year)
    deducted_premium = cursor.execute(premium_query, premium_params).fetchone()[0] or 0
    return cumulative_bonus, abs(deducted_premium)

def check_if_final_records_exist(conn, year: int, month: int) -> bool:
    """檢查指定月份是否存在任何已定版 ('final') 的薪資紀錄。"""
    query = "SELECT 1 FROM salary WHERE year = ? AND month = ? AND status = 'final' LIMIT 1"
    result = conn.execute(query, (year, month)).fetchone()
    return result is not None