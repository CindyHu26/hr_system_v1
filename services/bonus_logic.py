# services/bonus_logic.py
import pandas as pd
# 修正 import，明確指向 employee 查詢模組
from db import queries_employee as q_emp

def process_and_calculate_bonuses(conn, all_details_df, year, month):
    """
    處理抓取到的明細，實現分期付款獎金邏輯，並計算每個人的獎金。
    """
    if all_details_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = all_details_df.copy()
    df['is_abnormal'] = df['實收金額'].str.contains(r'\*', na=False)
    df['cleaned_amount'] = df['實收金額'].str.replace(r'[^0-9]', '', regex=True)
    df['numeric_receivable'] = pd.to_numeric(df['應收金額'], errors='coerce').fillna(0)
    df['numeric_received'] = pd.to_numeric(df['cleaned_amount'], errors='coerce').fillna(0)
    
    group_cols = ["序號", "雇主姓名", "外勞姓名", "帳款名稱", "應收金額"]
    df['unique_bill_id'] = df[group_cols].astype(str).agg('-'.join, axis=1)
    
    received_sum_map = df.groupby('unique_bill_id')['numeric_received'].sum()
    df['total_received_for_bill'] = df['unique_bill_id'].map(received_sum_map)

    # 判斷帳款是否已付清 (允許有些微誤差)
    df['is_fully_paid'] = df['total_received_for_bill'] >= (df['numeric_receivable'] - 1)
    
    current_month_str = f"{year}-{month:02d}"
    df['payment_month'] = pd.to_datetime(df['收款日'], errors='coerce').dt.strftime('%Y-%m')
    
    # 找出所有在本月有收款紀錄，且已付清的帳款ID
    fully_paid_bills_with_current_month_payment = df[
        (df['is_fully_paid']) & 
        (df['payment_month'] == current_month_str)
    ]['unique_bill_id'].unique()

    # 正常獎金：非異常、在本月收款
    normal_bonus_records = df[(df['is_abnormal'] == False) & (df['payment_month'] == current_month_str)]
    
    # 異常獎金：帳款ID屬於本月付清的
    abnormal_paid_off_records = df[df['unique_bill_id'].isin(fully_paid_bills_with_current_month_payment)].drop_duplicates(subset=['unique_bill_id'])
    
    # 匹配員工 ID
    emp_map_df = q_emp.get_employee_map(conn)
    df['clean_name'] = df['外勞姓名'].str.replace(r'\s+', '', regex=True)
    df = pd.merge(df, emp_map_df, on='clean_name', how='left')
    
    bonus_per_employee = {}
    
    # 加總正常獎金
    for _, row in normal_bonus_records.iterrows():
        if pd.notna(row['employee_id']):
            bonus_per_employee[row['employee_id']] = bonus_per_employee.get(row['employee_id'], 0) + row['numeric_received']

    # 加總本月付清的異常獎金 (用「應收金額」計算)
    for _, row in abnormal_paid_off_records.iterrows():
        if pd.notna(row['employee_id']):
            bonus_per_employee[row['employee_id']] = bonus_per_employee.get(row['employee_id'], 0) + row['numeric_receivable']

    if not bonus_per_employee:
        return pd.DataFrame(), df

    # 整理總結報告
    summary_list = []
    for emp_id, total_base_amount in bonus_per_employee.items():
        emp_name = emp_map_df[emp_map_df['employee_id'] == emp_id]['name_ch'].iloc[0]
        summary_list.append({
            'employee_id': emp_id,
            '員工姓名': emp_name,
            '總收款(用於計算)': total_base_amount,
            'bonus_amount': total_base_amount / 2
        })
    
    final_summary = pd.DataFrame(summary_list)
    return final_summary, df
