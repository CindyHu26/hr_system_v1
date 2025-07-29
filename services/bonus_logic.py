# services/bonus_logic.py
import pandas as pd
from db import queries_employee as q_emp

def process_and_calculate_bonuses(conn, all_details_df, year, month):
    """
    【V3 版】
    - 獎金金額四捨五入。
    - 回傳的明細表欄位進行中文化。
    - 【新】修改判斷同一帳單的唯一鍵。
    """
    if all_details_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = all_details_df.copy()
    # 將 DataFrame 的欄位名暫時改成對應資料庫的英文名
    df.rename(columns={
        'is_abnormal': '是否異常',
        'numeric_receivable': '應收金額(數字)',
        'numeric_received': '實收金額(數字)',
        'payment_month': '收款月份',
        'is_fully_paid': '是否付清'
    }, inplace=True, errors='ignore') # errors='ignore' 避免重複執行時報錯

    df['是否異常'] = df['實收金額'].astype(str).str.contains(r'\*', na=False)
    df['cleaned_amount'] = df['實收金額'].astype(str).str.replace(r'[^0-9.-]', '', regex=True)
    df['應收金額(數字)'] = pd.to_numeric(df['應收金額'], errors='coerce').fillna(0)
    df['實收金額(數字)'] = pd.to_numeric(df['cleaned_amount'], errors='coerce').fillna(0)

    # --- 【核心修改】採用您指定的7個欄位作為唯一鍵 ---
    group_cols = ["序號", "雇主姓名", "入境日", "外勞姓名", "帳款名稱", "帳款日", "應收金額"]
    df['unique_bill_id'] = df[group_cols].astype(str).agg('-'.join, axis=1)

    received_sum_map = df.groupby('unique_bill_id')['實收金額(數字)'].sum()
    df['total_received_for_bill'] = df['unique_bill_id'].map(received_sum_map)
    df['是否付清'] = df['total_received_for_bill'] >= (df['應收金額(數字)'] - 1)

    current_month_str = f"{year}-{month:02d}"
    # 將日期欄位轉換為 datetime 物件，以便進行月份比較
    df['收款月份'] = pd.to_datetime(df['收款日'], errors='coerce').dt.strftime('%Y-%m')

    emp_map_df = q_emp.get_employee_map(conn)
    df_merged = pd.merge(df, emp_map_df, left_on='業務員姓名', right_on='name_ch', how='left')
    df_valid = df_merged.dropna(subset=['employee_id']).copy()

    if df_valid.empty:
        return pd.DataFrame(), df_merged

    fully_paid_bills_ids = df_valid[
        (df_valid['是否付清']) &
        (df_valid['收款月份'] == current_month_str)
    ]['unique_bill_id'].unique()

    abnormal_paid_off_records = df_valid[df_valid['unique_bill_id'].isin(fully_paid_bills_ids)].drop_duplicates(subset=['unique_bill_id'])
    abnormal_bonus_sum = abnormal_paid_off_records.groupby('employee_id')['應收金額(數字)'].sum()

    normal_bonus_records = df_valid[
        (df_valid['是否異常'] == False) &
        (df_valid['收款月份'] == current_month_str) &
        (~df_valid['unique_bill_id'].isin(fully_paid_bills_ids))
    ]
    normal_bonus_sum = normal_bonus_records.groupby('employee_id')['實收金額(數字)'].sum()

    total_base_amount_series = normal_bonus_sum.add(abnormal_bonus_sum, fill_value=0)

    if total_base_amount_series.empty:
        return pd.DataFrame(), df_merged

    summary_df = total_base_amount_series.reset_index()
    summary_df.columns = ['employee_id', '總收款(用於計算)']
    summary_df = pd.merge(summary_df, emp_map_df[['employee_id', 'name_ch']], on='employee_id', how='left')
    summary_df.rename(columns={'name_ch': '員工姓名'}, inplace=True)

    summary_df['bonus_amount'] = (summary_df['總收款(用於計算)'] / 2).round().astype(int)
    summary_df['employee_id'] = summary_df['employee_id'].astype(int)

    final_cols = ['employee_id', '員工姓名', '總收款(用於計算)', 'bonus_amount']

    display_detail_cols = [
        '業務員姓名', '外勞姓名', '雇主姓名', '帳款名稱',
        '應收金額', '帳款日', '收款日', '入境日', '實收金額', '是否付清', '是否異常'
    ]
    for col in display_detail_cols:
        if col not in df_merged.columns:
            df_merged[col] = ''

    return summary_df[final_cols], df_merged[display_detail_cols]