# services/report_generator.py
import pandas as pd
import io
from datetime import time, datetime
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import Break
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

from db import queries_attendance as q_att
from db import queries_salary_records as q_records
from db import queries_employee as q_emp
from db import queries_insurance as q_ins

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

def _get_monthly_salary_data(conn, year, month):
    """
    獲取指定月份的薪資資料，並進行初步處理。
    """
    report_df, item_types = q_records.get_salary_report_for_editing(conn, year, month)
    
    final_df = report_df[report_df['status'] == 'final'].copy()
    
    if final_df.empty:
        raise ValueError(f"{year} 年 {month} 月沒有任何「已鎖定」的薪資紀錄可供產生報表。")

    emp_df = q_emp.get_all_employees(conn)
    ins_df = q_ins.get_all_insurance_history(conn)
    ins_df['start_date'] = pd.to_datetime(ins_df['start_date'])
    latest_ins = ins_df.loc[ins_df.groupby('name_ch')['start_date'].idxmax()]
    
    final_df = pd.merge(final_df, emp_df[['id', 'dept']], left_on='employee_id', right_on='id', how='left')
    final_df = pd.merge(final_df, latest_ins[['name_ch', 'company_name']], left_on='員工姓名', right_on='name_ch', how='left')

    for col in list(item_types.keys()) + ['應付總額', '應扣總額', '實發薪資']:
        if col in final_df.columns:
            final_df[col] = pd.to_numeric(final_df[col], errors='coerce').fillna(0)
            
    return final_df, item_types


def _generate_basic_salary_excel(conn, df: pd.DataFrame, year, month): # <-- 【修正點 1】新增 conn 參數
    """產生基礎薪資總表 (Excel)"""
    att_summary = q_att.get_monthly_attendance_summary(conn, year, month)
    
    df_merged = pd.merge(df, att_summary, on='employee_id', how='left').fillna(0)

    cols = {
        '員工姓名': '姓名', '員工編號': '編號', 'company_name': '加保', 'dept': '部門', '底薪': '底薪',
        '加班費(延長工時)': '加班費', '加班費(再延長工時)': '加班費2', '應付總額': '應付合計',
        '勞健保': '勞健保', '借支': '借支', '事假': '事假', '病假': '病假', 
        'late_minutes': '遲到(分)', '遲到': '遲到', 'early_leave_minutes': '早退(分)', '早退': '早退', 
        '其他': '其他', '稅款': '稅款', '應扣總額': '應扣合計', '實發薪資': '合計', 
        '勞退提撥(公司負擔)': '勞退提撥'
    }
    
    df_report = pd.DataFrame()
    for col_db, col_report in cols.items():
        df_report[col_report] = df_merged.get(col_db, 0)
    
    # 計算事病假時數
    # 避免底薪為0導致的除零錯誤
    hourly_rate = (df_merged['底薪'] / 240).replace(0, pd.NA)
    df_report['事假(時)'] = (df_report['事假'] / hourly_rate).abs().round(2).fillna(0)
    df_report['病假(時)'] = (df_report['病假'] / (hourly_rate * 0.5)).abs().round(2).fillna(0)

    output = io.BytesIO()
    df_report.to_excel(output, index=False, sheet_name="薪資計算")
    output.seek(0)
    return output.getvalue()


def _generate_full_salary_excel(df: pd.DataFrame, item_types: dict):
    """產生完整薪資總表 (Excel)"""
    df_report = df.copy()
    
    df_report['加班費'] = df_report.get('加班費(延長工時)', 0) + df_report.get('加班費(再延長工時)', 0)

    core_cols = ['員工姓名', '員工編號', 'company_name', 'dept']
    earning_cols = sorted([k for k, v in item_types.items() if v == 'earning' and '加班費' not in k and k != '底薪'])
    deduction_cols = sorted([k for k, v in item_types.items() if v == 'deduction' and k != '勞健保'])
    summary_cols = ['應付總額', '應扣總額', '實發薪資', '匯入銀行', '現金', '勞退提撥(公司負擔)']
    
    final_cols = core_cols + ['底薪', '加班費'] + earning_cols + ['勞健保'] + deduction_cols + summary_cols
    
    for col in final_cols:
        if col not in df_report.columns:
            df_report[col] = 0
            
    df_report = df_report[final_cols]
    
    output = io.BytesIO()
    df_report.to_excel(output, index=False, sheet_name="薪資計算(加)")
    output.seek(0)
    return output.getvalue()


def _generate_payslip_docx(df: pd.DataFrame, year: int, month: int, item_types: dict):
    """根據範本為所有員工產生薪資單 (Word)"""
    document = Document()
    font = document.styles['Normal'].font
    font.name = '標楷體'

    for index, emp_row in df.iterrows():
        table_header = document.add_table(rows=2, cols=4)
        table_header.cell(0, 0).text = str(year - 1911)
        table_header.cell(0, 1).text = "年度"
        table_header.cell(0, 2).text = str(month)
        table_header.cell(0, 3).text = "月份薪資明細表"
        table_header.cell(1, 0).text = "姓名"
        table_header.cell(1, 1).text = emp_row.get('員工姓名', '')
        table_header.cell(1, 2).text = "部門"
        table_header.cell(1, 3).text = emp_row.get('dept', '')

        table_details = document.add_table(rows=1, cols=4)
        hdr_cells = table_details.rows[0].cells
        hdr_cells[0].text = '給付項目'
        hdr_cells[1].text = '金額'
        hdr_cells[2].text = '扣除項目'
        hdr_cells[3].text = '金額'

        earnings = {'底薪': emp_row.get('底薪', 0)}
        if emp_row.get('加班費(延長工時)', 0) != 0: earnings['加班費(延長)'] = emp_row['加班費(延長工時)']
        if emp_row.get('加班費(再延長工時)', 0) != 0: earnings['加班費(再延長)'] = emp_row['加班費(再延長工時)']
        for item, type in item_types.items():
            if type == 'earning' and item not in earnings and emp_row.get(item, 0) != 0:
                 earnings[item] = emp_row[item]
        
        deductions = {}
        for item, type in item_types.items():
            if type == 'deduction' and emp_row.get(item, 0) != 0:
                deductions[item] = emp_row[item]

        max_rows = max(len(earnings), len(deductions))
        for i in range(max_rows):
            row_cells = table_details.add_row().cells
            if i < len(earnings):
                item, amount = list(earnings.items())[i]
                row_cells[0].text = item
                row_cells[1].text = f"{int(amount):,}"
            if i < len(deductions):
                item, amount = list(deductions.items())[i]
                row_cells[2].text = item
                row_cells[3].text = f"{int(abs(amount)):,}"

        table_total = document.add_table(rows=3, cols=4)
        table_total.cell(0, 0).text = "應付總額"
        table_total.cell(0, 1).text = f"{int(emp_row.get('應付總額', 0)):,}"
        table_total.cell(0, 2).text = "應扣總額"
        table_total.cell(0, 3).text = f"{int(abs(emp_row.get('應扣總額', 0))):,}"
        table_total.cell(1, 0).text = "實發薪資"
        table_total.cell(1, 1).text = f"{int(emp_row.get('實發薪資', 0)):,}"
        table_total.cell(2, 0).text = "備註"
        table_total.cell(2, 0).merge(table_total.cell(2, 3))

        if index < len(df) - 1:
            document.add_page_break()

    output = io.BytesIO()
    document.save(output)
    output.seek(0)
    return output.getvalue()


def generate_monthly_salary_reports(conn, year, month):
    """
    主函式：產生所有月度薪資報表。
    """
    final_df, item_types = _get_monthly_salary_data(conn, year, month)
    
    # 【修正點 2】將 conn 傳遞給子函式
    basic_excel = _generate_basic_salary_excel(conn, final_df, year, month)
    full_excel = _generate_full_salary_excel(final_df, item_types)
    payslip_docx = _generate_payslip_docx(final_df, year, month, item_types)
    
    return {
        "basic_excel": basic_excel,
        "full_excel": full_excel,
        "payslip_docx": payslip_docx
    }