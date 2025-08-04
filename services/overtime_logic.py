# services/overtime_logic.py
from datetime import datetime, date, timedelta
from db import queries_attendance as q_att

def calculate_special_overtime_pay(conn, employee_id, year, month, hourly_rate):
    """
    (修正版) 計算特別加班費 (津貼)
    - 修正時間差計算的邏輯，使其更穩健。
    """
    records = q_att.get_special_attendance_for_month(conn, employee_id, year, month)
    total_pay = 0

    for record in records:
        try:
            checkin_t = datetime.strptime(record['checkin_time'], '%H:%M:%S').time()
            checkout_t = datetime.strptime(record['checkout_time'], '%H:%M:%S').time()

            # 使用 date.today() 作為一個固定的日期基準來計算時間差，避免潛在的日期問題
            today = date.today()
            checkin_dt = datetime.combine(today, checkin_t)
            checkout_dt = datetime.combine(today, checkout_t)

            # 如果下班時間早於上班時間，假定為跨日加班
            if checkout_dt < checkin_dt:
                checkout_dt += timedelta(days=1)

            duration_seconds = (checkout_dt - checkin_dt).total_seconds()
            duration_hours = duration_seconds / 3600

            if duration_hours <= 2:
                pay = duration_hours * hourly_rate * 1.34
            else:
                pay = (2 * hourly_rate * 1.34) + ((duration_hours - 2) * hourly_rate * 1.67)
            
            total_pay += pay

        except (ValueError, TypeError):
            # 如果時間格式有誤，跳過該筆紀錄，避免整個計算崩潰
            continue

    return int(round(total_pay))