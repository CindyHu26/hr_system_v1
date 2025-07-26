# services/allowance_logic.py
import pandas as pd
from db import queries_allowances as q_allow

def batch_import_allowances(conn, uploaded_file):
    """
    處理上傳的員工常態薪資項 Excel，進行驗證並呼叫資料庫函式進行儲存。
    """
    try:
        df = pd.read_excel(uploaded_file, dtype=str).fillna('')
        
        column_rename_map = {
            '員工姓名*': 'name_ch', '項目名稱*': 'item_name', '金額*': 'amount',
            '生效日*(YYYY-MM-DD)': 'start_date', '結束日(YYYY-MM-DD)': 'end_date', '備註': 'note'
        }
        df.rename(columns=column_rename_map, inplace=True)

        # 基本驗證和資料清理
        errors = []
        required_cols = ['name_ch', 'item_name', 'amount', 'start_date']
        df.dropna(subset=required_cols, inplace=True)
        
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df.dropna(subset=['amount'], inplace=True)

        for date_col in ['start_date', 'end_date']:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.strftime('%Y-%m-%d')

        df.dropna(subset=['start_date'], inplace=True)

        if df.empty:
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': [{'row': 'N/A', 'reason': '沒有有效的資料可供匯入。'}]}

        db_report = q_allow.batch_upsert_allowances(conn, df)
        
        return {
            'inserted': db_report.get('inserted', 0),
            'updated': db_report.get('updated', 0),
            'failed': db_report.get('failed', 0),
            'errors': db_report.get('errors', [])
        }
    except Exception as e:
        raise Exception(f"處理常態薪資項 Excel 檔案時發生錯誤：{e}")