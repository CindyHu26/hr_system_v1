-- db/schema.sql
-- 此檔案定義了所有人資系統資料表的結構。

-- 員工主資料表
CREATE TABLE IF NOT EXISTS employee (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name_ch TEXT NOT NULL, id_no TEXT NOT NULL UNIQUE,
    entry_date DATE, hr_code TEXT UNIQUE, gender TEXT, birth_date DATE,
    nationality TEXT DEFAULT 'TW', arrival_date DATE, phone TEXT, address TEXT,
    dept TEXT, title TEXT, resign_date DATE, bank_account TEXT, note TEXT
);

-- 公司（加保單位）表
CREATE TABLE IF NOT EXISTS company (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, uniform_no TEXT, address TEXT,
    owner TEXT, ins_code TEXT, note TEXT
);

-- 員工加保異動紀錄表
CREATE TABLE IF NOT EXISTS employee_company_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, company_id INTEGER NOT NULL,
    start_date DATE NOT NULL, end_date DATE, note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id), FOREIGN KEY(company_id) REFERENCES company(id)
);

-- 出勤紀錄表
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, date DATE NOT NULL,
    checkin_time TIME, checkout_time TIME, late_minutes INTEGER DEFAULT 0,
    early_leave_minutes INTEGER DEFAULT 0, absent_minutes INTEGER DEFAULT 0,
    overtime1_minutes INTEGER DEFAULT 0, overtime2_minutes INTEGER DEFAULT 0,
    overtime3_minutes INTEGER DEFAULT 0, note TEXT, source_file TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id), UNIQUE(employee_id, date)
);

-- 特別出勤紀錄表
CREATE TABLE IF NOT EXISTS special_attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, date DATE NOT NULL,
    checkin_time TIME NOT NULL, checkout_time TIME NOT NULL, note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id) ON DELETE CASCADE
);

-- 請假紀錄表
CREATE TABLE IF NOT EXISTS leave_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, request_id TEXT UNIQUE,
    leave_type TEXT NOT NULL, start_date DATETIME NOT NULL, end_date DATETIME NOT NULL,
    duration REAL, reason TEXT, status TEXT, approver TEXT, submit_date DATE, note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id)
);

-- 薪資項目定義表
CREATE TABLE IF NOT EXISTS salary_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1
);

-- 員工薪資基準歷史紀錄表
CREATE TABLE IF NOT EXISTS salary_base_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, base_salary INTEGER NOT NULL,
    insurance_salary INTEGER, dependents REAL DEFAULT 0, start_date DATE, end_date DATE, note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id) ON DELETE CASCADE
);

-- 薪資主紀錄表
CREATE TABLE IF NOT EXISTS salary (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
    status TEXT DEFAULT 'draft', total_payable REAL DEFAULT 0, total_deduction REAL DEFAULT 0,
    net_salary REAL DEFAULT 0, bank_transfer_amount REAL DEFAULT 0, cash_amount REAL DEFAULT 0, note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id), UNIQUE(employee_id, year, month)
);

-- 薪資明細表
CREATE TABLE IF NOT EXISTS salary_detail (
    id INTEGER PRIMARY KEY AUTOINCREMENT, salary_id INTEGER NOT NULL, salary_item_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    FOREIGN KEY(salary_id) REFERENCES salary(id) ON DELETE CASCADE,
    FOREIGN KEY(salary_item_id) REFERENCES salary_item(id)
);

-- 勞健保級距表
CREATE TABLE IF NOT EXISTS insurance_grade (
    id INTEGER PRIMARY KEY AUTOINCREMENT, start_date DATE NOT NULL, type TEXT NOT NULL, grade INTEGER NOT NULL,
    salary_min INTEGER NOT NULL, salary_max INTEGER NOT NULL, employee_fee INTEGER,
    employer_fee INTEGER, gov_fee INTEGER, note TEXT,
    UNIQUE(start_date, type, grade)
);

-- 員工常態薪資項設定
CREATE TABLE IF NOT EXISTS employee_salary_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, salary_item_id INTEGER NOT NULL,
    amount INTEGER NOT NULL, start_date DATE NOT NULL, end_date DATE, note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id) ON DELETE CASCADE,
    FOREIGN KEY(salary_item_id) REFERENCES salary_item(id) ON DELETE CASCADE
);

-- 每月業務獎金中繼站
CREATE TABLE IF NOT EXISTS monthly_bonus (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
    bonus_amount REAL NOT NULL, note TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_id, year, month)
);
