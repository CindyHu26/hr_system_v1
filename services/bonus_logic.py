# services/bonus_logic.py
import pandas as pd
from db import queries_employee as q_emp

def process_and_calculate_bonuses(conn, all_details_df, year, month):
    """
    【最終修正版】修正重複計算問題，確保每筆獎金只會被計算一次。
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
    df['is_fully_paid'] = df['total_received_for_bill'] >= (df['numeric_receivable'] - 1)
    
    current_month_str = f"{year}-{month:02d}"
    df['payment_month'] = pd.to_datetime(df['收款日'], errors='coerce').dt.strftime('%Y-%m')
    
    emp_map_df = q_emp.get_employee_map(conn)
    df_merged = pd.merge(df, emp_map_df, left_on='業務員姓名', right_on='name_ch', how='left')
    df_valid = df_merged.dropna(subset=['employee_id']).copy()

    if df_valid.empty:
        return pd.DataFrame(), df_merged

    # 1. 優先找出所有在本月付清的帳單
    fully_paid_bills_ids = df_valid[
        (df_valid['is_fully_paid']) & 
        (df_valid['payment_month'] == current_month_str)
    ]['unique_bill_id'].unique()

    # 2. 計算這些付清帳單的獎金 (以應收總額為準)
    abnormal_paid_off_records = df_valid[df_valid['unique_bill_id'].isin(fully_paid_bills_ids)].drop_duplicates(subset=['unique_bill_id'])
    abnormal_bonus_sum = abnormal_paid_off_records.groupby('employee_id')['numeric_receivable'].sum()

    # 3. 計算正常獎金，但必須排除掉已在步驟2中處理過的帳單
    normal_bonus_records = df_valid[
        (df_valid['is_abnormal'] == False) & 
        (df_valid['payment_month'] == current_month_str) & 
        (~df_valid['unique_bill_id'].isin(fully_paid_bills_ids)) # 關鍵修改：排除已付清的帳單
    ]
    normal_bonus_sum = normal_bonus_records.groupby('employee_id')['numeric_received'].sum()

    # 4. 將兩種獎金加總
    total_base_amount_series = normal_bonus_sum.add(abnormal_bonus_sum, fill_value=0)

    if total_base_amount_series.empty:
        return pd.DataFrame(), df_merged

    # 5. 整理最終報告
    summary_df = total_base_amount_series.reset_index()
    summary_df.columns = ['employee_id', '總收款(用於計算)']
    summary_df = pd.merge(summary_df, emp_map_df[['employee_id', 'name_ch']], on='employee_id', how='left')
    summary_df.rename(columns={'name_ch': '員工姓名'}, inplace=True)
    summary_df['bonus_amount'] = summary_df['總收款(用於計算)'] / 2
    summary_df['employee_id'] = summary_df['employee_id'].astype(int)

    final_cols = ['employee_id', '員工姓名', '總收款(用於計算)', 'bonus_amount']
    return summary_df[final_cols], df_merged