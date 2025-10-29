# database.py (再次修改)
import sqlite3
import os
from datetime import datetime, timedelta

DB_NAME = 'rental.db'

def init_db():
    """初始化数据库和表，并插入假数据"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 创建租户表 (修改为租户名称和联系人)
    c.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL, -- 租户名称 (公司名)
            contact_person TEXT NOT NULL, -- 联系人
            email TEXT NOT NULL,
            phone TEXT,
            payment_cycle TEXT NOT NULL, -- 'quarterly', 'semi_annually', 'yearly'
            move_in_date DATE -- 可选
        )
    ''')
    
    # 创建合同表 (添加 last_payment_date 字段)
    c.execute('''
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            unit_number TEXT NOT NULL,
            rent_amount REAL NOT NULL,
            next_due_date DATE NOT NULL,
            last_payment_date DATE, -- 新增字段
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
    ''')
    
    # 创建提醒日志表
    c.execute('''
        CREATE TABLE IF NOT EXISTS reminder_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            method TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            FOREIGN KEY (contract_id) REFERENCES contracts(id)
        )
    ''')

    # 检查是否已有数据，避免重复插入
    c.execute("SELECT COUNT(*) FROM tenants")
    tenant_count = c.fetchone()[0]
    if tenant_count == 0:
        print("数据库为空，正在插入假数据...")
        
        # 插入假租户数据 (公司名, 联系人)
        tenants_data = [
            ('创新科技有限公司', '张三', 'zhangsan@example.com', '13800138001', 'quarterly', '2024-01-15'),
            ('未来教育集团', '李四', 'lisi@example.com', '13800138002', 'semi_annually', '2023-11-20'),
            ('绿洲生态农场', '王五', 'wangwu@example.com', '13800138003', 'yearly', '2023-05-10'),
            ('星辰设计工作室', '赵六', 'zhaoliu@example.com', '13800138004', 'quarterly', '2024-02-01'),
            ('海纳百川贸易公司', '钱七', 'qianqi@example.com', '13800138005', 'yearly', None), # 入住日期可选
        ]
        c.executemany('INSERT INTO tenants (company_name, contact_person, email, phone, payment_cycle, move_in_date) VALUES (?, ?, ?, ?, ?, ?)', tenants_data)

        # 获取插入的租户ID
        c.execute("SELECT id FROM tenants ORDER BY id")
        tenant_ids = [row[0] for row in c.fetchall()]

        # 根据租户ID和付费周期计算并插入假合同数据
        contracts_data = []
        # 创新科技 (按季度, 上次付费 2025-07-01, 下次应为 2025-10-01)
        last_payment = datetime(2025, 7, 1).date()
        next_due = last_payment + timedelta(days=90) # 90天 = 1季度
        contracts_data.append((tenant_ids[0], 'A栋101', 3000.00, next_due.strftime('%Y-%m-%d'), last_payment.strftime('%Y-%m-%d')))

        # 未来教育 (按半年, 上次付费 2025-04-01, 下次应为 2025-10-01 + 2天 = 2025-10-03 (模拟不同到期日))
        last_payment = datetime(2025, 4, 1).date()
        next_due = last_payment + timedelta(days=180) # 180天 = 半年
        contracts_data.append((tenant_ids[1], 'B栋202', 6000.00, next_due.strftime('%Y-%m-%d'), last_payment.strftime('%Y-%m-%d')))

        # 绿洲生态 (按年, 上次付费 2024-08-01, 下次应为 2025-08-01)
        last_payment = datetime(2024, 8, 1).date()
        next_due = last_payment + timedelta(days=365) # 365天 = 1年
        contracts_data.append((tenant_ids[2], 'C栋303', 12000.00, next_due.strftime('%Y-%m-%d'), last_payment.strftime('%Y-%m-%d')))

        # 星辰设计 (按季度, 上次付费 2025-08-15, 下次应为 2025-11-15, 已超过7天提醒期)
        last_payment = datetime(2025, 8, 15).date()
        next_due = last_payment + timedelta(days=90)
        contracts_data.append((tenant_ids[3], 'D栋404', 3200.00, next_due.strftime('%Y-%m-%d'), last_payment.strftime('%Y-%m-%d')))

        # 海纳百川 (按年, 上次付费 2024-10-01, 下次应为 2025-10-01)
        last_payment = datetime(2024, 10, 1).date()
        next_due = last_payment + timedelta(days=365)
        contracts_data.append((tenant_ids[4], 'E栋505', 15000.00, next_due.strftime('%Y-%m-%d'), last_payment.strftime('%Y-%m-%d')))

        c.executemany('INSERT INTO contracts (tenant_id, unit_number, rent_amount, next_due_date, last_payment_date) VALUES (?, ?, ?, ?, ?)', contracts_data)

        conn.commit()
        print("假数据插入完成！")
    else:
        print("数据库已存在数据，跳过假数据插入。如需重新生成，请删除 rental.db 文件。")

    conn.close()

def get_db_connection():
    """获取数据库连接 (统一管理)"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # 这样可以像字典一样访问行
    return conn

def get_all_contracts_with_tenant():
    """获取所有合同及其租户信息 (包括已过期的)"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT c.*, t.company_name, t.contact_person, t.email, t.phone, t.payment_cycle, t.move_in_date
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        -- 移除 is_active = 1 的限制，以显示所有合同
        ORDER BY c.is_active DESC, c.next_due_date -- 有效合同在前，再按到期日排序
    ''')
    contracts = c.fetchall()
    conn.close()
    return [dict(row) for row in contracts]

def get_all_tenants():
    """获取所有租户信息 (用于下拉列表)"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, company_name, contact_person, email FROM tenants ORDER BY company_name')
    tenants = c.fetchall()
    conn.close()
    return [dict(row) for row in tenants]

def add_tenant(company_name, contact_person, email, phone, payment_cycle, move_in_date=None): # 移除 name, 增加 company_name, contact_person
    """添加租户"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO tenants (company_name, contact_person, email, phone, payment_cycle, move_in_date) VALUES (?, ?, ?, ?, ?, ?)',
              (company_name, contact_person, email, phone, payment_cycle, move_in_date))
    tenant_id = c.lastrowid
    conn.commit()
    conn.close()
    return tenant_id

def add_contract(tenant_id, unit_number, rent_amount, next_due_date, last_payment_date=None): # last_payment_date 可选
    """添加合同"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO contracts (tenant_id, unit_number, rent_amount, next_due_date, last_payment_date) 
        VALUES (?, ?, ?, ?, ?)
    ''', (tenant_id, unit_number, rent_amount, next_due_date, last_payment_date))
    contract_id = c.lastrowid
    conn.commit()
    conn.close()
    return contract_id

def update_contract_payment_status(contract_id, new_due_date, last_payment_date):
    """更新合同的付款状态和下次到期日"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE contracts 
        SET next_due_date = ?, last_payment_date = ?
        WHERE id = ?
    ''', (new_due_date, last_payment_date, contract_id))
    conn.commit()
    conn.close()

def get_contracts_due_in_days_or_before(days_ahead):
    """获取指定天数内或之前到期的合同 (核心催收逻辑)"""
    from datetime import datetime, timedelta
    target_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    c = conn.cursor()
    # 检查 next_due_date <= 今天 + 7天 的所有有效合同
    c.execute('''
        SELECT c.*, t.contact_person as tenant_name, t.email -- 使用联系人姓名作为发送邮件的称呼
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        WHERE c.next_due_date <= ?
        AND c.is_active = 1
    ''', (target_date,))
    contracts = c.fetchall()
    conn.close()
    return [dict(row) for row in contracts]

def log_reminder(contract_id, method, status, message=''):
    """记录提醒日志"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO reminder_logs (contract_id, method, status, message)
        VALUES (?, ?, ?, ?)
    ''', (contract_id, method, status, message))
    conn.commit()
    conn.close()

def get_payment_cycle_days(payment_cycle):
    """根据付费周期返回天数"""
    cycle_map = {
        'quarterly': 90,
        'semi_annually': 180,
        'yearly': 365,
    }
    return cycle_map.get(payment_cycle, 0)
