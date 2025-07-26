# services/reporting_logic.py
"""
此模組包含產生複雜報表的商業邏輯，例如年度薪資總表、二代健保試算等。
"""
import pandas as pd
import config
from db import queries_salary_records as q_records
from db import queries_salary_base as q_base

def generate_annual_salary_summary(conn, year: int, item_ids: list):
    """產生年度薪資總表的核心邏輯。"""
    if not item_ids:
        return pd.DataFrame(columns=['員工編號', '員工姓名'] + [f'{m}月' for m in range(1, 13)])

    # --- 【修正點】改為呼叫 q_records 中的函式 ---
    df = q_records.get_annual_salary_summary_data(conn, year, item_ids)
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
        # --- 【修正點】改為呼叫 q_records 中的函式 ---
        report_df, _ = q_records.get_salary_report_for_editing(conn, year, month)

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
        premium = round(diff * config.NHI_SUPPLEMENT_RATE) if diff > 0 else 0

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
    """為薪資基礎審核頁面準備資料。"""
    
    # 1. 取得當月薪資單的 DataFrame
    report_df, _ = q_records.get_salary_report_for_editing(conn, year, month)
    if report_df.empty:
        return pd.DataFrame()
        
    # 2. 篩選出需要的欄位
    preview_cols = [
        'employee_id', '員工姓名', '底薪', 
        '勞保費', '健保費', '勞退提撥(公司負擔)'
    ]
    
    # 確保所有欄位都存在，如果不存在則補 0
    for col in preview_cols:
        if col not in report_df.columns:
            report_df[col] = 0
            
    return report_df[preview_cols]