-- db/schema.sql
-- 此檔案定義了所有人資系統資料表的結構。

-- 系統通用參數設定表 (Key-Value Store)
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 系統參數 - 基本工資歷史紀錄表
CREATE TABLE IF NOT EXISTS minimum_wage_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL UNIQUE,
    wage INTEGER NOT NULL,
    effective_date DATE,
    note TEXT
);

-- 員工主資料表
CREATE TABLE IF NOT EXISTS employee (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name_ch TEXT NOT NULL, id_no TEXT NOT NULL UNIQUE,
    entry_date DATE, hr_code TEXT UNIQUE, gender TEXT, birth_date DATE,
    nationality TEXT DEFAULT 'TW', arrival_date DATE, phone TEXT, address TEXT,
    dept TEXT, title TEXT, resign_date DATE, bank_account TEXT, note TEXT,
    nhi_status TEXT DEFAULT '一般', -- 一般, 低收入戶, 自理
    nhi_status_expiry DATE
);

-- 公司（加保單位）表
CREATE TABLE IF NOT EXISTS company (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    uniform_no TEXT,
    debit_account TEXT,
    enterprise_id TEXT,
    address TEXT,
    owner TEXT,
    ins_code TEXT,
    note TEXT
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
    leave_minutes INTEGER DEFAULT 0,
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
    insurance_salary INTEGER, 
    dependents_under_18 REAL DEFAULT 0,
    dependents_over_18 REAL DEFAULT 0,
    labor_insurance_override REAL,
    health_insurance_override REAL,
    pension_override REAL,
    start_date DATE, end_date DATE, note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id) ON DELETE CASCADE,
    UNIQUE(employee_id, start_date)
);

-- 薪資主紀錄表
CREATE TABLE IF NOT EXISTS salary (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
    status TEXT DEFAULT 'draft', total_payable REAL DEFAULT 0, total_deduction REAL DEFAULT 0,
    net_salary REAL DEFAULT 0, bank_transfer_amount REAL DEFAULT 0, cash_amount REAL DEFAULT 0, 
    employer_pension_contribution REAL DEFAULT 0,
    note TEXT,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    salary_item_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employee(id) ON DELETE CASCADE,
    FOREIGN KEY(salary_item_id) REFERENCES salary_item(id) ON DELETE CASCADE,
    UNIQUE(employee_id, salary_item_id, start_date)
);

-- 每月業務獎金中繼站
CREATE TABLE IF NOT EXISTS monthly_bonus (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL,
    bonus_amount REAL NOT NULL, note TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_id, year, month)
);

-- 每月業務獎金抓取明細歷史紀錄表
CREATE TABLE IF NOT EXISTS monthly_bonus_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    sequence_no TEXT,
    employer_name TEXT,
    entry_date TEXT,
    foreign_worker_name TEXT,
    item_name TEXT,
    bill_date TEXT,
    receivable_amount TEXT,
    received_date TEXT,
    received_amount TEXT,
    salesperson_name TEXT,
    status TEXT NOT NULL DEFAULT 'draft', -- 'draft' 或 'final'
    source TEXT NOT NULL DEFAULT 'scraped'  -- 'scraped' 或 'manual'
);

-- 每月績效獎金中繼站
CREATE TABLE IF NOT EXISTS monthly_performance_bonus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    bonus_amount REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_id, year, month)
);

-- 特殊不計薪日設定表
CREATE TABLE IF NOT EXISTS special_unpaid_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    description TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- --- 索引優化 (Index Optimizations) ---
CREATE INDEX IF NOT EXISTS idx_employee_id_on_attendance ON attendance (employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_id_on_special_attendance ON special_attendance (employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_id_on_leave_record ON leave_record (employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_id_on_salary_base_history ON salary_base_history (employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_id_on_salary ON salary (employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_id_on_employee_salary_item ON employee_salary_item (employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_id_on_monthly_bonus ON monthly_bonus (employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_id_on_employee_company_history ON employee_company_history (employee_id);
CREATE INDEX IF NOT EXISTS idx_date_on_attendance ON attendance (date);
CREATE INDEX IF NOT EXISTS idx_date_on_leave_record ON leave_record (start_date);
CREATE INDEX IF NOT EXISTS idx_year_month_on_monthly_bonus_details ON monthly_bonus_details (year, month);
CREATE INDEX IF NOT EXISTS idx_employee_id_on_monthly_performance_bonus ON monthly_performance_bonus (employee_id);