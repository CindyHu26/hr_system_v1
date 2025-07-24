# services/salary_base_logic.py
import pandas as pd
from db import queries_salary_base as q_base

def batch_import_salary_base(conn, uploaded_file):
    """
    處理上傳的員工薪資基準 Excel，進行驗證並呼叫資料庫函式進行儲存。
    """
    try:
        df = pd.read_excel(uploaded_file, dtype=str).fillna('')
        
        column_rename_map = {
            '員工姓名*': 'name_ch', '底薪*': 'base_salary', '勞健保投保薪資*': 'insurance_salary',
            '健保眷屬數*': 'dependents', '生效日*(YYYY-MM-DD)': 'start_date', 
            '結束日(YYYY-MM-DD)': 'end_date', '備註': 'note'
        }
        df.rename(columns=column_rename_map, inplace=True)

        errors = []
        for index, row in df.iterrows():
            # 驗證姓名欄位
            required_cols = ['name_ch', 'base_salary', 'insurance_salary', 'dependents', 'start_date']
            if any(not row.get(col) for col in required_cols):
                errors.append({'row': index + 2, 'reason': '有必填欄位為空，已跳過此行。'})
                df.drop(index, inplace=True)
                continue
            
            date_val = row.get('start_date')
            try:
                parsed_date = pd.to_datetime(date_val, errors='coerce')
                if pd.isna(parsed_date): raise ValueError
                df.loc[index, 'start_date'] = parsed_date.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                errors.append({'row': index + 2, 'reason': f"生效日 '{date_val}' 格式錯誤。"})
                df.drop(index, inplace=True)

        if df.empty:
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': errors}

        db_report = q_base.batch_add_or_update_salary_base_history(conn, df)
        
        return {
            'inserted': db_report.get('inserted', 0),
            'updated': db_report.get('updated', 0),
            'failed': len(df) - (db_report.get('inserted', 0) + db_report.get('updated', 0)),
            'errors': errors + db_report.get('errors', [])
        }
    except Exception as e:
        raise Exception(f"處理薪資基準 Excel 檔案時發生錯誤：{e}")