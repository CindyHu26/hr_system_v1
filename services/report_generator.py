# services/report_generator.py
import pandas as pd
import io
from datetime import time
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import Break
from db import queries_attendance as q_att

def dataframe_to_report_excel(df_all_employees: pd.DataFrame, final_columns: list, numeric_columns: list):
    """將包含所有員工的單一 DataFrame 轉換為格式化的、可分頁列印的 Excel 檔案。"""
    output = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "出勤月報表"

    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.7, bottom=0.7)
    
    ws.print_title_rows = '1:1'

    header_fill = PatternFill(start_color="CCFFCC", end_color="CCFFCC", fill_type="solid")
    bold_font = Font(bold=True)
    
    for col_num, column_title in enumerate(final_columns, 1):
        cell = ws.cell(row=1, column=col_num, value=column_title)
        cell.fill = header_fill
        cell.font = bold_font

    current_row = 2
    for name, df_employee in df_all_employees.groupby('名稱', sort=False):
        for _, row_data in df_employee.iterrows():
            for c_idx, col_name in enumerate(final_columns, 1):
                ws.cell(row=current_row, column=c_idx, value=row_data.get(col_name))
            current_row += 1
        
        subtotal_row_idx = current_row
        ws.cell(row=subtotal_row_idx, column=3, value=f"{name}_小計").font = bold_font
        for c_idx, col_name in enumerate(final_columns, 1):
            if col_name in numeric_columns:
                col_letter = get_column_letter(c_idx)
                start_range = subtotal_row_idx - len(df_employee)
                end_range = subtotal_row_idx - 1
                ws.cell(row=subtotal_row_idx, column=c_idx, value=f"=SUM({col_letter}{start_range}:{col_letter}{end_range})").font = bold_font
        
        current_row += 1
        ws.row_breaks.append(Break(id=current_row - 1))

    # --- [核心修改] 自動調整與手動設定欄寬並行 ---
    column_widths = {}
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        for cell in row:
            if cell.value:
                length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in str(cell.value))
                column_widths[cell.column_letter] = max(column_widths.get(cell.column_letter, 0), length)
    
    for col, width in column_widths.items():
        # 如果是 I 到 N 欄，則使用您指定的固定寬度
        if col in ['I', 'J', 'K', 'L', 'M', 'N']:
            ws.column_dimensions[col].width = 7
        else:
            # 其他欄位維持自動調整，並設定一個最大和最小值
            ws.column_dimensions[col].width = min(max(width + 2, 8), 50)


    wb.save(output)
    output.seek(0)
    return output.getvalue()


def get_descriptive_leave_type(row):
    """根據請假時間判斷假別描述"""
    leave_type = row['leave_type']
    start_time = row['start_date'].time()
    end_time = row['end_date'].time()
    duration = row['duration']

    if pd.isna(leave_type):
        return ''
    
    if duration >= 8:
        return f"全天{leave_type}"
    if start_time < time(12, 0) and end_time <= time(13, 0):
        return f"上午{leave_type}"
    if start_time >= time(12, 0):
        return f"下午{leave_type}"
    
    return leave_type

def get_attendance_status(row):
    """根據紀錄決定出席狀態的優先級"""
    if row['缺席'] > 0:
        return '缺席'
    if row['請假'] > 0:
        return '請假/出差'
    
    is_late = row['遲到'] > 0
    is_early = row['早退'] > 0
    
    if is_late and is_early:
        return '遲到/早退'
    if is_late:
        return '遲到'
    if is_early:
        return '早退'
        
    return '一般'


def generate_attendance_excel(conn, year, month):
    """從資料庫獲取資料並產生 Excel 報表。"""
    
    df_att_raw = q_att.get_attendance_by_month(conn, year, month)
    if df_att_raw.empty:
        raise ValueError(f"{year} 年 {month} 月沒有任何出勤紀錄可供匯出。")

    df_leave_raw = q_att.get_leave_details_by_month(conn, year, month)
    
    df = df_att_raw.rename(columns={
        'hr_code': '人員 ID', 'name_ch': '名稱', 'date': '日期',
        'checkin_time': '簽到', 'checkout_time': '簽退', 'late_minutes': '遲到',
        'early_leave_minutes': '早退', 'absent_minutes': '缺席',
        'overtime1_minutes': '加班 1', 'overtime2_minutes': '加班 2',
        'overtime3_minutes': '加班 3', 'leave_minutes': '請假'
    })
    
    df['加班23'] = df['加班 2'] + df['加班 3']
    
    df['日期_dt'] = pd.to_datetime(df['日期'])
    weekday_map = {0: '一', 1: '二', 2: '三', 3: '四', 4: '五', 5: '六', 6: '日'}
    df['星期'] = df['日期_dt'].dt.weekday.map(weekday_map)
    
    if not df_leave_raw.empty:
        daily_leaves = []
        for _, leave in df_leave_raw.iterrows():
            d = leave['start_date'].date()
            while d <= leave['end_date'].date():
                daily_leaves.append({
                    'employee_id': leave['employee_id'],
                    'date_str': d.strftime('%Y-%m-%d'),
                    'leave_type': get_descriptive_leave_type(leave)
                })
                d += pd.Timedelta(days=1)
        df_daily_leaves = pd.DataFrame(daily_leaves).rename(columns={'date_str': '日期'})
        
        df = pd.merge(df, df_daily_leaves, on=['employee_id', '日期'], how='left')
        df['請假類型'] = df['leave_type'].fillna('')
    else:
        df['請假類型'] = ''
        
    df['出席狀態'] = df.apply(get_attendance_status, axis=1)
    
    df = df.sort_values(by=['人員 ID', '日期_dt'])
    
    final_columns = ['星期', '人員 ID', '名稱', '日期', '出席狀態', '請假類型', '簽到', '簽退',
                     '遲到', '早退', '缺席', '加班 1', '加班23', '請假']
    numeric_columns = ['遲到', '早退', '缺席', '加班 1', '加班23', '請假']
    
    excel_file = dataframe_to_report_excel(df, final_columns, numeric_columns)
    
    return excel_file