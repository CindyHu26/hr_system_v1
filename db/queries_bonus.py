# db/queries_bonus.py
"""
資料庫查詢：專門處理「業務獎金(monthly_bonus)」相關的資料庫操作。
"""
import pandas as pd

def get_employee_bonus(conn, emp_id, year, month):
    """從中繼站讀取預先算好的業務獎金。"""
    sql = "SELECT bonus_amount FROM monthly_bonus WHERE employee_id = ? AND year = ? AND month = ?"
    return conn.execute(sql, (emp_id, year, month)).fetchone()

def save_bonuses_to_monthly_table(conn, year, month, summary_df):
    """將計算好的獎金總結存入 monthly_bonus 中繼站。"""
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM monthly_bonus WHERE year = ? AND month = ?", (year, month))
        to_insert = [
            (int(row['employee_id']), year, month, float(row['bonus_amount']), '爬蟲計算')
            for _, row in summary_df.iterrows()
        ]
        sql = "INSERT INTO monthly_bonus (employee_id, year, month, bonus_amount, note) VALUES (?, ?, ?, ?, ?)"
        cursor.executemany(sql, to_insert)
        conn.commit()
        return len(to_insert)
    except Exception as e:
        conn.rollback()
        raise e

# --- 【新增函式】 ---
def save_bonus_details_to_history(conn, year: int, month: int, details_df: pd.DataFrame):
    """
    將抓取的原始獎金明細存入歷史紀錄表。
    此操作會先刪除該月份的舊紀錄，再插入新紀錄。
    """
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        # 1. 刪除該月份的舊資料
        cursor.execute("DELETE FROM monthly_bonus_details WHERE year = ? AND month = ?", (year, month))
        
        # 2. 準備要插入的新資料
        df_to_insert = details_df.copy()
        # 確保欄位順序與資料庫一致
        columns = [
            'year', 'month', 'sequence_no', 'employer_name', 'entry_date', 
            'foreign_worker_name', 'item_name', 'bill_date', 'receivable_amount', 
            'received_date', 'received_amount', 'salesperson_name'
        ]
        # 將 DataFrame 的欄位名暫時改成對應資料庫的英文名
        df_to_insert.columns = [
            'sequence_no', 'employer_name', 'entry_date', 'foreign_worker_name', 
            'item_name', 'bill_date', 'receivable_amount', 'received_date', 
            'received_amount', 'salesperson_name'
        ]
        df_to_insert['year'] = year
        df_to_insert['month'] = month
        
        # 3. 執行批次插入
        df_to_insert.to_sql('monthly_bonus_details', conn, if_exists='append', index=False)
        
        conn.commit()
        return len(df_to_insert)
    except Exception as e:
        conn.rollback()
        raise e

# --- 【新增函式】 ---
def get_bonus_details_by_month(conn, year: int, month: int):
    """
    從歷史紀錄表中查詢指定月份的獎金明細。
    """
    query = "SELECT * FROM monthly_bonus_details WHERE year = ? AND month = ?"
    df = pd.read_sql_query(query, conn, params=(year, month))
    # 將欄位名稱改為中文以便顯示
    df.rename(columns={
        'sequence_no': '序號', 'employer_name': '雇主姓名', 'entry_date': '入境日',
        'foreign_worker_name': '外勞姓名', 'item_name': '帳款名稱', 'bill_date': '帳款日',
        'receivable_amount': '應收金額', 'received_date': '收款日',
        'received_amount': '實收金額', 'salesperson_name': '業務員姓名'
    }, inplace=True)
    return df.drop(columns=['id', 'year', 'month'])