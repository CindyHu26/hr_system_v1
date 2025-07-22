# services/overtime_logic.py
from datetime import datetime
from db import queries as q

def calculate_special_overtime_pay(conn, employee_id, year, month, hourly_rate):
    """計算特別加班費 (津貼)"""
    records = q.get_special_attendance_for_month(conn, employee_id, year, month)
    total_pay = 0
    for record in records:
        checkin_t = datetime.strptime(record['checkin_time'], '%H:%M:%S').time()
        checkout_t = datetime.strptime(record['checkout_time'], '%H:%M:%S').time()

        duration_seconds = (datetime.combine(datetime.min, checkout_t) - datetime.combine(datetime.min, checkin_t)).total_seconds()
        duration_hours = duration_seconds / 3600

        if duration_hours <= 2:
            pay = duration_hours * hourly_rate * 1.34
        else:
            pay = (2 * hourly_rate * 1.34) + ((duration_hours - 2) * hourly_rate * 1.67)
        total_pay += pay

    return int(round(total_pay))
