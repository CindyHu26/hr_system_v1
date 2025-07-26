# services/salary_item_logic.py
import pandas as pd
from db import queries_salary_items as q_items

def batch_import_salary_items(conn, uploaded_file):
    """
    處理上傳的薪資項目 Excel，進行驗證並呼叫資料庫函式進行儲存。
    """
    try:
        df = pd.read_excel(uploaded_file, dtype=str).fillna('')
        
        column_rename_map = {
            '項目名稱*': 'name', '類型*(earning/deduction)': 'type', '是否啟用*(1/0)': 'is_active'
        }
        df.rename(columns=column_rename_map, inplace=True)

        # 基本驗證
        errors = []
        df['is_active'] = pd.to_numeric(df['is_active'], errors='coerce').fillna(1).astype(bool)
        df = df[df['name'].notna() & (df['name'] != '')]
        df = df[df['type'].isin(['earning', 'deduction'])]

        if df.empty:
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': [{'row': 'N/A', 'reason': '沒有有效的資料可供匯入。'}]}

        db_report = q_items.batch_add_or_update_salary_items(conn, df)
        
        return {
            'inserted': db_report.get('inserted', 0),
            'updated': db_report.get('updated', 0),
            'failed': 0,
            'errors': []
        }
    except Exception as e:
        raise Exception(f"處理薪資項目 Excel 檔案時發生錯誤：{e}")