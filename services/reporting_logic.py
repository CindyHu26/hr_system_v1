# services/reporting_logic.py
"""
此模組包含產生複雜報表的商業邏輯，例如年度薪資總表、二代健保試算等。
"""
import pandas as pd
import config
from db import queries as q

def generate_annual_salary_summary(conn, year: int, item_ids: list):
    """產生年度薪資總表的核心邏輯。"""
    if not item_ids:
        return pd.DataFrame(columns=['員工編號', '員工姓名'] + [f'{m}月' for m in range(1, 13)])

    # 從資料庫獲取原始資料
    df = q.get_annual_salary_summary_data(conn, year, item_ids)
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
    results = []
    
    for month in range(1, 13):
        # 取得當月最終薪資報表 (包含所有計算)
        report_df, _ = q.get_salary_report_for_editing(conn, year, month)

        # A. 支付薪資總額
        total_paid_salary = report_df['應付總額'].sum() if '應付總額' in report_df.columns else 0

        # B. 健保投保薪資總額
        total_insured_salary = 0
        if not report_df.empty:
            # 取得員工當前的投保薪資
            emp_ids = report_df['employee_id'].tolist()
            insured_salaries = q.get_batch_employee_insurance_salary(conn, emp_ids, year, month)
            total_insured_salary = sum(insured_salaries.values())

        # 計算差額與應繳保費
        diff = total_paid_salary - total_insured_salary
        premium = round(diff * config.NHI_SUPPLEMENT_RATE) if diff > 0 else 0
        
        results.append({
            '月份': f"{month}月",
            '支付薪資總額 (A)': total_paid_salary,
            '健保投保薪資總額 (B)': total_insured_salary,
            '計費差額 (A - B)': diff,
            '單位應繳補充保費': premium
        })
        
    summary_df = pd.DataFrame(results)
    total_row = summary_df.sum(numeric_only=True).to_frame().T
    total_row['月份'] = '年度總計'
    final_df = pd.concat([summary_df, total_row], ignore_index=True)
    return final_df
