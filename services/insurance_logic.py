# services/insurance_logic.py
"""
此模組包含解析外部勞健保資料來源的商業邏輯。
它負責將非結構化的檔案（Excel, HTML）轉換為結構化的 DataFrame。
"""
import pandas as pd
import io

def parse_labor_insurance_excel(file_obj):
    """根據官方 Excel 檔案的特定格式，解析勞保級距表。"""
    try:
        # 【關鍵修正】將讀取引擎從 'openpyxl' 改為 'xlrd'，以兼容舊版 .xls 檔案格式
        df = pd.read_excel(file_obj, header=None, engine='xlrd')
        
        # 根據經驗，關鍵資料通常在這些行（可能會隨檔案版本變動）
        grade_row_data = df.iloc[36]
        salary_row_data = df.iloc[37]
        fee_row_data = df.iloc[68]
        
        start_col_index = next((i for i, text in enumerate(grade_row_data) if isinstance(text, str) and "第1級" in text), -1)
        if start_col_index == -1:
            raise ValueError("在第37列中找不到 '第1級'，無法定位勞工級距表。")

        records = []
        for i in range(start_col_index, len(salary_row_data)):
            salary = salary_row_data.get(i)
            grade_text = grade_row_data.get(i)
            if pd.notna(salary) and isinstance(salary, (int, float)) and isinstance(grade_text, str):
                try:
                    records.append({
                        'grade': int(''.join(filter(str.isdigit, grade_text))),
                        'salary_max': salary,
                        'employee_fee': fee_row_data.get(i),
                        'employer_fee': fee_row_data.get(i + 1),
                    })
                except (ValueError, TypeError):
                    continue
        
        if not records:
            raise ValueError("無法從指定的行號中提取有效的級距資料。")

        df_final = pd.DataFrame(records).dropna(subset=['grade', 'salary_max']).drop_duplicates(subset=['grade'], keep='first')
        df_final['salary_min'] = df_final['salary_max'].shift(1).fillna(0) + 1
        df_final.loc[df_final.index[0], 'salary_min'] = 1 # 投保下限通常從1開始
        return df_final[['grade', 'salary_min', 'salary_max', 'employee_fee', 'employer_fee']]
    except Exception as e:
        raise ValueError(f"解析勞保 Excel 檔案時發生錯誤: {e}")

def parse_health_insurance_html(html_content):
    """從健保署網頁的 HTML 原始碼中解析健保級距表。"""
    try:
        tables = pd.read_html(io.StringIO(html_content))
        target_df = next((df for df in tables if '月投保金額' in ''.join(map(str, df.columns))), None)
        if target_df is None:
            raise ValueError("在 HTML 中找不到包含 '月投保金額' 的表格。")

        df = target_df.copy()
        # 清理多層級的欄位名稱
        df.columns = ['_'.join(map(str, col)).strip() for col in df.columns.values]
        df.ffill(inplace=True)

        # 根據欄位位置和名稱進行映射
        rename_map = {
            df.columns[0]: 'grade', 
            df.columns[1]: 'salary_max', 
            df.columns[2]: 'employee_fee', 
            df.columns[6]: 'employer_fee', 
            df.columns[7]: 'gov_fee'
        }
        df.rename(columns=rename_map, inplace=True)
        
        for col in ['grade', 'salary_max', 'employee_fee', 'employer_fee', 'gov_fee']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[\s,元$]', '', regex=True), errors='coerce')

        df.dropna(subset=['grade', 'salary_max'], inplace=True)
        df.drop_duplicates(subset=['grade'], keep='first', inplace=True)
        df['salary_min'] = df['salary_max'].shift(1).fillna(0) + 1
        df.loc[df.index[0], 'salary_min'] = 1
        
        required_cols = ['grade', 'salary_min', 'salary_max', 'employee_fee', 'employer_fee', 'gov_fee']
        return df[[col for col in required_cols if col in df.columns]]
    except Exception as e:
        raise ValueError(f"解析健保 HTML 時發生錯誤: {e}")