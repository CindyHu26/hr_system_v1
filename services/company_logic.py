# **【請手動建立新檔案】: services/company_logic.py**

import pandas as pd
from db import queries_common as q_common

def batch_import_companies(conn, uploaded_file):
    """
    處理上傳的公司資料 Excel，進行驗證並呼叫資料庫函式進行儲存。
    """
    try:
        df = pd.read_excel(uploaded_file)
        
        column_rename_map = {
            '公司名稱*': 'name', '統一編號*': 'uniform_no', '地址': 'address',
            '負責人': 'owner', '投保代號': 'ins_code', '備註': 'note'
        }
        df.rename(columns=column_rename_map, inplace=True)

        records_to_process = []
        errors = []
        for index, row in df.iterrows():
            if pd.isna(row.get('name')) or pd.isna(row.get('uniform_no')):
                errors.append({'row': index + 2, 'reason': '公司名稱或統一編號為空，已跳過此行。'})
                continue
            records_to_process.append(row.to_dict())
            
        if not records_to_process:
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': errors}

        clean_df = pd.DataFrame(records_to_process)
        
        # 這裡我們需要一個批次處理公司的資料庫函式
        # 為了方便，我們直接在 logic 中實作，但理想上應該在 query 層
        # (這裡我們使用 q_common 中的通用函式來簡化)
        inserted_count = 0
        updated_count = 0
        
        for _, row_data in clean_df.iterrows():
            # 檢查統一編號是否存在
            existing = pd.read_sql_query("SELECT id FROM company WHERE uniform_no = ?", conn, params=(row_data['uniform_no'],))
            
            cleaned_data = {k: (v if pd.notna(v) else None) for k, v in row_data.items()}

            if existing.empty:
                q_common.add_record(conn, 'company', cleaned_data)
                inserted_count += 1
            else:
                record_id = existing['id'].iloc[0]
                q_common.update_record(conn, 'company', record_id, cleaned_data)
                updated_count += 1

        return {
            'inserted': inserted_count,
            'updated': updated_count,
            'failed': len(df) - (inserted_count + updated_count),
            'errors': errors
        }

    except Exception as e:
        raise Exception(f"處理公司 Excel 檔案時發生錯誤：{e}")