# db/queries_bonus.py
"""
資料庫查詢：專門處理「業務獎金(monthly_bonus)」相關的資料庫操作。
【V2 版】：新增支援草稿(draft)與鎖定(final)狀態的函式。
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
        if summary_df.empty:
            conn.commit()
            return 0
        to_insert = [
            (int(row['employee_id']), year, month, float(row['bonus_amount']), '系統計算鎖定')
            for _, row in summary_df.iterrows()
        ]
        sql = "INSERT INTO monthly_bonus (employee_id, year, month, bonus_amount, note) VALUES (?, ?, ?, ?, ?)"
        cursor.executemany(sql, to_insert)
        conn.commit()
        return len(to_insert)
    except Exception as e:
        conn.rollback()
        raise e

def upsert_bonus_details_draft(conn, year: int, month: int, details_df: pd.DataFrame):
    """
    將抓取或手動編輯的獎金明細草稿存入歷史紀錄表。
    此操作會先刪除該月份的所有舊草稿，再插入新草稿。
    """
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        # 1. 刪除該月份的所有「草稿」資料
        cursor.execute("DELETE FROM monthly_bonus_details WHERE year = ? AND month = ? AND status = 'draft'", (year, month))

        if details_df.empty:
            conn.commit()
            return 0

        # 2. 準備要插入的新資料
        df_to_insert = details_df.copy()
        # 確保欄位齊全
        df_to_insert['year'] = year
        df_to_insert['month'] = month
        df_to_insert['status'] = 'draft' # 所有存入的都是草稿
        # 如果沒有 source 欄位，預設為 manual
        if 'source' not in df_to_insert.columns:
            df_to_insert['source'] = 'manual'

        # 轉換為符合 to_sql 的欄位名
        df_to_insert.rename(columns={
            '序號': 'sequence_no', '雇主姓名': 'employer_name', '入境日': 'entry_date',
            '外勞姓名': 'foreign_worker_name', '帳款名稱': 'item_name', '帳款日': 'bill_date',
            '應收金額': 'receivable_amount', '收款日': 'received_date',
            '實收金額': 'received_amount', '業務員姓名': 'salesperson_name'
        }, inplace=True)

        # 3. 執行批次插入
        df_to_insert.to_sql('monthly_bonus_details', conn, if_exists='append', index=False)

        conn.commit()
        return len(df_to_insert)
    except Exception as e:
        conn.rollback()
        raise e

def finalize_bonus_details(conn, year: int, month: int):
    """ 將指定月份的所有獎金明細草稿狀態更新為 'final'。"""
    sql = "UPDATE monthly_bonus_details SET status = 'final' WHERE year = ? AND month = ? AND status = 'draft'"
    cursor = conn.cursor()
    cursor.execute(sql, (year, month))
    conn.commit()
    return cursor.rowcount

def get_bonus_details_by_month(conn, year: int, month: int, status: str = 'draft'):
    """
    從歷史紀錄表中查詢指定月份、指定狀態的獎金明細。
    """
    query = "SELECT * FROM monthly_bonus_details WHERE year = ? AND month = ? AND status = ?"
    df = pd.read_sql_query(query, conn, params=(year, month, status))
    # 將欄位名稱改為中文以便顯示
    df.rename(columns={
        'sequence_no': '序號', 'employer_name': '雇主姓名', 'entry_date': '入境日',
        'foreign_worker_name': '外勞姓名', 'item_name': '帳款名稱', 'bill_date': '帳款日',
        'receivable_amount': '應收金額', 'received_date': '收款日',
        'received_amount': '實收金額', 'salesperson_name': '業務員姓名'
    }, inplace=True)
    # 返回不包含系統內部欄位的 DataFrame
    return df.drop(columns=['id', 'year', 'month', 'status'])