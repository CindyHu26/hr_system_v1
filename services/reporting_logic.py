# services/reporting_logic.py
"""
此模組包含產生複雜報表的商業邏輯，例如年度薪資總表、二代健保試算等。
"""
import pandas as pd
from db import queries_salary_read as q_read
from db import queries_salary_base as q_base
from db import queries_config as q_config
from db import queries_insurance as q_ins
from db import queries_employee as q_emp

def generate_annual_salary_summary(conn, year: int, item_ids: list):
    """產生年度薪資總表的核心邏輯。"""
    if not item_ids:
        return pd.DataFrame(columns=['員工編號', '員工姓名'] + [f'{m}月' for m in range(1, 13)])

    # --- 呼叫 q_records 中的函式 ---
    df = q_read.get_annual_salary_summary_data(conn, year, item_ids)
    if df.empty:
        return pd.DataFrame(columns=['員工編號', '員工姓名'] + [f'{m}月' for m in range(1, 13)])

    # 使用 pivot_table 進行資料重塑 (長格式轉寬格式)
    pivot_df = df.pivot_table(
        index=['員工編號', '員工姓名'],
        columns='month',
        values='monthly_total',
        fill_value=0
    ).reset_index()

    # 重新命名欄位並確保所有月份都存在
    pivot_df.columns = ['員工編號', '員工姓名'] + [f'{col}月' for col in pivot_df.columns[2:]]
    for m in range(1, 13):
        month_col = f'{m}月'
        if month_col not in pivot_df.columns:
            pivot_df[month_col] = 0

    # 重新排序欄位
    final_df = pivot_df[['員工編號', '員工姓名'] + [f'{m}月' for m in range(1, 13)]]
    return final_df

def generate_nhi_employer_summary(conn, year: int):
    """計算公司應負擔的二代健保補充保費。"""
    db_configs = q_config.get_all_configs(conn)
    NHI_SUPPLEMENT_RATE = float(db_configs.get('NHI_SUPPLEMENT_RATE', '0.0211'))
    results = []

    for month in range(1, 13):
        # --- 呼叫 q_read 中的函式 ---
        report_df, _ = q_read.get_salary_report_for_editing(conn, year, month)

        # A. 支付薪資總額
        total_paid_salary = report_df['應付總額'].sum() if '應付總額' in report_df.columns else 0

        # B. 健保投保薪資總額
        total_insured_salary = 0
        if not report_df.empty:
            # 取得員工當前的投保薪資
            emp_ids = report_df['employee_id'].tolist()
            # --- 【修正點】改為呼叫 q_base 中的函式 ---
            insured_salaries = q_base.get_batch_employee_insurance_salary(conn, emp_ids, year, month)
            total_insured_salary = sum(insured_salaries.values())

        # 計算差額與應繳保費
        diff = total_paid_salary - total_insured_salary
        premium = round(diff * NHI_SUPPLEMENT_RATE) if diff > 0 else 0

        results.append({
            '月份': f"{month}月",
            '支付薪資總額 (A)': total_paid_salary,
            '健保投保薪資總額 (B)': total_insured_salary,
            '計費差額 (A - B)': diff,
            '單位應繳補充保費': premium
        })

    summary_df = pd.DataFrame(results)
    # 計算年度總計
    if not summary_df.empty:
        total_row = summary_df.sum(numeric_only=True).to_frame().T
        total_row['月份'] = '年度總計'
        summary_df = pd.concat([summary_df, total_row], ignore_index=True)
        
    return summary_df

def get_salary_preview_data(conn, year: int, month: int):
    """為薪資基礎審核頁面準備資料。(V2: 使用獨立查詢，與總表脫鉤)"""
    
    # 1. 直接查詢當月的薪資主表和明細表
    query = """
    SELECT 
        s.employee_id,
        e.name_ch as '員工姓名',
        si.name as item_name,
        sd.amount,
        s.employer_pension_contribution as '勞退提撥'
    FROM salary_detail sd
    JOIN salary s ON sd.salary_id = s.id
    JOIN salary_item si ON sd.salary_item_id = si.id
    JOIN employee e ON s.employee_id = e.id
    WHERE s.year = ? 
      AND s.month = ?
      AND si.name IN ('底薪', '勞保費', '健保費')
    """
    df_raw = pd.read_sql_query(query, conn, params=(year, month))

    if df_raw.empty:
        return pd.DataFrame()
        
    # 2. 將長格式資料轉換為寬格式（每個員工一行）
    preview_df = df_raw.pivot_table(
        index=['employee_id', '員工姓名', '勞退提撥'], 
        columns='item_name', 
        values='amount'
    ).reset_index()

    # 3. 確保所有需要的欄位都存在，若無則補 0
    preview_cols = [
        'employee_id', '員工姓名', '底薪', 
        '勞保費', '健保費', '勞退提撥'
    ]
    for col in preview_cols:
        if col not in preview_df.columns:
            preview_df[col] = 0
            
    return preview_df[preview_cols]

def calculate_nhi_personal_bonus_for_period(conn, year: int, start_month: int, end_month: int):
    """
    (通用版) 試算每位員工在指定期間內，因高額獎金應繳納的健保補充保費。
    """
    db_configs = q_config.get_all_configs(conn)
    NHI_SUPPLEMENT_RATE = float(db_configs.get('NHI_SUPPLEMENT_RATE', '0.0211'))
    NHI_BONUS_MULTIPLIER = int(float(db_configs.get('NHI_BONUS_MULTIPLIER', '4')))
    NHI_BONUS_ITEMS = [item.strip() for item in db_configs.get('NHI_BONUS_ITEMS', '').split(',')]

    salary_details_query = "SELECT s.employee_id, e.name_ch, si.name as item_name, sd.amount FROM salary_detail sd JOIN salary s ON sd.salary_id = s.id JOIN salary_item si ON sd.salary_item_id = si.id JOIN employee e ON s.employee_id = e.id WHERE s.year = ? AND s.status = 'final' AND s.month BETWEEN ? AND ?"
    df_details = pd.read_sql_query(salary_details_query, conn, params=(year, start_month, end_month))
    if df_details.empty: return pd.DataFrame()

    df_bonus = df_details[df_details['item_name'].isin(NHI_BONUS_ITEMS)]
    period_bonus_summary = df_bonus.groupby(['employee_id', 'name_ch'])['amount'].sum().reset_index()
    period_bonus_summary.rename(columns={'amount': '期間獎金總額'}, inplace=True)
    emp_ids = period_bonus_summary['employee_id'].tolist()
    insured_salaries_map = q_base.get_batch_employee_insurance_salary(conn, emp_ids, year, end_month)
    period_bonus_summary['投保薪資'] = period_bonus_summary['employee_id'].map(insured_salaries_map).fillna(0)
    period_bonus_summary['計費門檻'] = period_bonus_summary['投保薪資'] * NHI_BONUS_MULTIPLIER
    period_bonus_summary['應計費金額'] = period_bonus_summary.apply(lambda row: max(0, row['期間獎金總額'] - row['計費門檻']), axis=1)
    period_bonus_summary['應繳補充保費'] = (period_bonus_summary['應計費金額'] * NHI_SUPPLEMENT_RATE).round().astype(int)
    result_df = period_bonus_summary[['name_ch', '期間獎金總額', '投保薪資', '計費門檻', '應計費金額', '應繳補充保費']].rename(columns={'name_ch': '員工姓名'})
    return result_df[result_df['應繳補充保費'] > 0].sort_values(by='應繳補充保費', ascending=False)

def generate_nhi_accountant_summary(conn, year: int, item_ids: list):
    """為會計事務所產生年度二代健保計算用的獎金總表 (基於原始版本修改)。"""
    if not item_ids:
        return pd.DataFrame()

    # 1. 查詢薪資資料，確保包含 employee_id, 員工編號, 員工姓名, 身分證字號
    #    假設 q_read.get_annual_salary_summary_data 已按要求修改
    df_raw = q_read.get_annual_salary_summary_data(conn, year, item_ids, include_id_no=True)
    if df_raw.empty:
        return pd.DataFrame()

    # --- 獲取 employee_id (如果 df_raw 尚未包含) ---
    if 'employee_id' not in df_raw.columns:
         emp_map_df = q_emp.get_all_employees(conn)[['hr_code', 'id']]
         hr_code_to_id = dict(zip(emp_map_df['hr_code'], emp_map_df['id']))
         df_raw['employee_id'] = df_raw['員工編號'].map(hr_code_to_id)
         df_raw.dropna(subset=['employee_id'], inplace=True)
         df_raw['employee_id'] = df_raw['employee_id'].astype(int)

    # 2. 樞紐分析：每個員工一行
    pivot_df = df_raw.pivot_table(
        index=['employee_id', '員工編號', '員工姓名', '身分證字號'], # 確保索引包含所有需要的員工資訊
        columns='month',
        values='monthly_total',
        fill_value=0
    ).reset_index()

    # 3. 獲取年底 (12月) 的底薪和投保級距
    emp_ids_in_report = pivot_df['employee_id'].unique().tolist()
    base_salaries = {}
    insurance_salaries = {}
    if emp_ids_in_report:
        # 獲取投保薪資
        insurance_salaries_map = q_base.get_batch_employee_insurance_salary(conn, emp_ids_in_report, year, 12)
        insurance_salaries = {emp_id: salary for emp_id, salary in insurance_salaries_map.items()}
        # 獲取底薪
        for emp_id in emp_ids_in_report:
             base_info = q_base.get_employee_base_salary_info(conn, emp_id, year, 12)
             base_salaries[emp_id] = base_info['base_salary'] if base_info else 0

    # 合併查詢到的資料
    pivot_df['底薪'] = pivot_df['employee_id'].map(base_salaries).fillna(0).astype(int)
    pivot_df['投保級距'] = pivot_df['employee_id'].map(insurance_salaries).fillna(0).astype(int)

    # 4. 獲取年度 "最後" 的加保公司
    df_ins_all = q_ins.get_all_insurance_history(conn) # 假設已包含 employee_id
    latest_ins = pd.DataFrame()
    if not df_ins_all.empty:
        df_ins = df_ins_all[['employee_id', 'company_name', 'start_date']].copy()
        df_ins['start_date'] = pd.to_datetime(df_ins['start_date'], errors='coerce')
        # 篩選出 start_date 在目標年份或之前的紀錄
        df_ins_filtered = df_ins[df_ins['start_date'].dt.year <= year].copy()
        if not df_ins_filtered.empty:
            # 找出每個 employee_id 最晚的 start_date 對應的紀錄
            latest_ins = df_ins_filtered.loc[df_ins_filtered.groupby('employee_id')['start_date'].idxmax()]
            latest_ins = latest_ins[['employee_id', 'company_name']].copy()

    # 5. 合併 "最後" 加保公司資訊
    if not latest_ins.empty:
        final_df = pd.merge(pivot_df, latest_ins, on='employee_id', how='left')
    else:
        final_df = pivot_df.copy()
        final_df['company_name'] = pd.NA # 預設

    # 重新命名並填補缺失值
    final_df.rename(columns={'company_name': '加保公司'}, inplace=True)
    final_df['加保公司'] = final_df['加保公司'].fillna('') # 將 NA 改為空白

    # 6. 確保所有月份欄位存在並計算總和
    month_cols_map = {}
    for m in range(1, 13):
        col_name = f'{m}月'
        month_cols_map[m] = col_name
        # 處理樞紐分析後可能的數字欄位名
        if m in final_df.columns:
            final_df.rename(columns={m: col_name}, inplace=True)
        elif str(m) in final_df.columns:
             final_df.rename(columns={str(m): col_name}, inplace=True)
        # 如果月份不存在，補 0
        if col_name not in final_df.columns:
            final_df[col_name] = 0

    final_df['端午 (1-5月)'] = final_df[[month_cols_map[m] for m in range(1, 6)]].sum(axis=1)
    final_df['中秋 (6-10月)'] = final_df[[month_cols_map[m] for m in range(6, 11)]].sum(axis=1)
    final_df['年終 (11-12月)'] = final_df[[month_cols_map[m] for m in range(11, 13)]].sum(axis=1)
    final_df['全年度 (1-12月)'] = final_df[[month_cols_map[m] for m in range(1, 13)]].sum(axis=1)

    # 7. 整理並排序最終欄位
    final_cols_order = [
        '員工編號', '員工姓名', '加保公司', '身分證字號',
        '底薪', '投保級距', # <-- 新增的欄位
        '1月', '2月', '3月', '4月', '5月', '端午 (1-5月)',
        '6月', '7月', '8月', '9月', '10月', '中秋 (6-10月)',
        '11月', '12月', '年終 (11-12月)', '全年度 (1-12月)'
    ]

    # 確保所有需要的欄位都存在，移除不需要的輔助欄位
    for col in final_cols_order:
        if col not in final_df.columns:
            final_df[col] = 0 # 數值欄位補 0

    # 移除 employee_id
    final_df = final_df[final_cols_order].copy()

    # 按員工編號排序
    final_df = final_df.sort_values(by=['員工編號'])

    return final_df