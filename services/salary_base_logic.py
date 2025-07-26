# services/salary_base_logic.py
import pandas as pd
import re
from db import queries_salary_base as q_base
from db import queries_insurance as q_ins

def batch_import_salary_base(conn, uploaded_file):
    """
    處理上傳的員工薪資基準 Excel，進行驗證並呼叫資料庫函式進行儲存。
    V6: 修正批次匯入手動調整保費的功能。
    """
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        df.columns = df.columns.str.strip()
        df['original_index'] = df.index + 2
        
        # [核心修改] 更新預期欄位與重新命名映射，加入手動調整欄位
        expected_cols = {
            '員工姓名*': 'name_ch', '底薪*': 'base_salary',
            '健保眷屬數(<18歲)*': 'dependents_under_18', 
            '健保眷屬數(>=18歲)*': 'dependents_over_18',
            '生效日*(YYYY-MM-DD)': 'start_date'
        }
        column_rename_map = {
            '員工姓名*': 'name_ch', '底薪*': 'base_salary',
            '健保眷屬數(<18歲)*': 'dependents_under_18',
            '健保眷屬數(>=18歲)*': 'dependents_over_18',
            '勞保費(手動)': 'labor_insurance_override',
            '健保費(手動)': 'health_insurance_override',
            '勞退提撥(手動)': 'pension_override',
            '生效日*(YYYY-MM-DD)': 'start_date',
            '結束日(YYYY-MM-DD)': 'end_date', '備註': 'note'
        }
        
        missing_cols = [col for col in expected_cols.keys() if col not in df.columns]
        if missing_cols:
            reason = f"Excel 檔案缺少必要的欄位，請檢查範本是否正確: {', '.join(missing_cols)}"
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': [{'row': 'N/A', 'reason': reason}]}

        df.rename(columns=column_rename_map, inplace=True)

        emp_df_db = pd.read_sql("SELECT name_ch, id FROM employee", conn)
        emp_df_db['clean_name'] = emp_df_db['name_ch'].astype(str).str.replace(r'\s+', '', regex=True)
        emp_map = emp_df_db.set_index('clean_name')['id'].to_dict()

        errors = []
        valid_rows = []
        for _, row in df.iterrows():
            required_check = ['name_ch', 'base_salary', 'dependents_under_18', 'dependents_over_18', 'start_date']
            if row[required_check].isnull().any():
                errors.append({'row': row['original_index'], 'reason': '姓名、底薪、眷屬數或生效日等必填欄位為空。'})
                continue

            start_date = pd.to_datetime(row['start_date'], errors='coerce')
            if pd.isna(start_date):
                errors.append({'row': row['original_index'], 'reason': f"生效日 '{row['start_date']}' 格式無法辨識。"})
                continue

            clean_name_excel = re.sub(r'\s+', '', str(row['name_ch']))
            emp_id = emp_map.get(clean_name_excel)
            if not emp_id:
                errors.append({'row': row['original_index'], 'reason': f"在資料庫中找不到員工姓名 '{row['name_ch']}'。"})
                continue
            
            valid_rows.append(row)

        if not valid_rows:
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': errors}

        df_to_process = pd.DataFrame(valid_rows).copy()
        
        df_to_process['start_date'] = pd.to_datetime(df_to_process['start_date']).dt.strftime('%Y-%m-%d')
        if 'end_date' in df_to_process.columns:
            df_to_process['end_date'] = pd.to_datetime(df_to_process['end_date'], errors='coerce').apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else None)
        
        df_to_process['insurance_salary'] = df_to_process['base_salary'].apply(lambda x: q_ins.get_insurance_salary_level(conn, x))

        db_report = q_base.batch_add_or_update_salary_base_history(conn, df_to_process)
        
        final_report = {
            'inserted': db_report.get('inserted', 0),
            'updated': db_report.get('updated', 0),
            'failed': len(df) - len(valid_rows) + db_report.get('failed', 0),
            'errors': errors + db_report.get('errors', [])
        }
        
        return final_report
        
    except Exception as e:
        return {'inserted': 0, 'updated': 0, 'failed': df.shape[0] if 'df' in locals() else 0, 'errors': [{'row': 'N/A', 'reason': f'處理 Excel 檔案時發生嚴重錯誤: {e}'}]}