# app.py (再次修改)
from flask import Flask, render_template, request, redirect, url_for, flash
from database import init_db, get_all_contracts_with_tenant, add_tenant, add_contract, get_contracts_due_in_days_or_before, log_reminder, get_all_tenants, update_contract_payment_status, get_payment_cycle_days, get_db_connection
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# 初始化数据库 (会自动插入假数据)
init_db()

# --- 邮件发送函数 ---
def send_email_via_smtp(to_email, subject, body):
    """
    使用 SMTP 发送邮件（以QQ邮箱为例）
    需要先在邮箱设置中开启 POP3/SMTP 服务，获取授权码
    """
    # 请替换为你自己的邮箱和授权码
    smtp_server = "smtp.qq.com"  # QQ邮箱SMTP服务器
    smtp_port = 587
    sender_email = "your_qq_email@qq.com"  # 你的邮箱
    sender_password = "your_authorization_code"  # 你的邮箱授权码，不是密码！

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # 启用加密传输
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, to_email, text)
        server.quit()
        return True, "邮件发送成功"
    except Exception as e:
        return False, f"邮件发送失败: {str(e)}"

def send_email_via_sendgrid(to_email, subject, body):
    """
    使用 SendGrid API 发送邮件
    需要先注册 SendGrid 账号，获取 API Key
    pip install sendgrid
    """
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        # 请替换为你自己的 API Key
        api_key = "YOUR_SENDGRID_API_KEY"
        sg = SendGridAPIClient(api_key=api_key)

        message = Mail(
            from_email='your_verified_sender@yourdomain.com',  # 必须是 SendGrid 验证过的邮箱
            to_emails=to_email,
            subject=subject,
            plain_text_content=body
        )

        response = sg.send(message)
        if response.status_code == 202:  # 202 表示接受请求，不代表送达
            return True, "邮件已提交至 SendGrid"
        else:
            return False, f"SendGrid 返回错误: {response.status_code}"
    except Exception as e:
        return False, f"SendGrid 发送失败: {str(e)}"

# --- 核心催收逻辑 ---
def send_reminders():
    """发送催收提醒"""
    print(f"[{datetime.now()}] 开始执行催收任务...")
    
    # 获取 7 天内或之前到期的合同 (即 next_due_date <= today + 7)
    contracts = get_contracts_due_in_days_or_before(7)
    
    if not contracts:
        print("没有需要催收的合同")
        return
    
    for contract in contracts:
        tenant_name = contract['tenant_name'] # 使用联系人姓名
        tenant_email = contract['email']
        due_date = contract['next_due_date']
        unit = contract['unit_number']
        rent = contract['rent_amount']
        
        subject = f"租金催缴提醒 - {unit}"
        body = f"""
亲爱的 {tenant_name}，

您好！

您位于 {unit} 的物业租金即将到期，到期日为：{due_date}。
租金金额为：¥{rent}

请您及时安排付款，以免影响您的正常使用。

如有任何疑问，请随时与我们联系。

此致
敬礼！

物业管理部
        """.strip()

        # 发送邮件（这里以 SMTP 为例，你可以切换为 SendGrid）
        success, message = send_email_via_smtp(tenant_email, subject, body)
        # success, message = send_email_via_sendgrid(tenant_email, subject, body)  # 如果使用 SendGrid，取消注释此行

        # 记录日志
        log_reminder(contract['id'], 'email', 'success' if success else 'failed', message)
        print(f"向 {tenant_name} ({tenant_email}) 发送催收邮件: {message}")

# --- 定时任务设置 ---
scheduler = BackgroundScheduler()
# 每天早上 9 点执行催收任务
scheduler.add_job(send_reminders, 'cron', hour=9, minute=0)
scheduler.start()

# 确保应用退出时关闭定时任务
atexit.register(lambda: scheduler.shutdown())

# --- Flask 路由 ---
@app.route('/')
def index():
    """主页：显示所有合同列表和添加表单"""
    contracts = get_all_contracts_with_tenant()
    tenants = get_all_tenants() # 获取所有租户用于下拉列表
    return render_template('index.html', contracts=contracts, tenants=tenants)

# 将添加租户和合同合并到一个路由
@app.route('/add_tenant_contract', methods=['POST'])
def add_tenant_contract_route():
    """添加租户和合同"""
    # 从表单获取数据
    company_name = request.form.get('company_name') # 新字段
    contact_person = request.form.get('contact_person') # 新字段
    email = request.form.get('email')
    phone = request.form.get('phone')
    payment_cycle = request.form.get('payment_cycle')
    move_in_date = request.form.get('move_in_date') or None # 可选
    unit_number = request.form.get('unit_number')
    rent_amount = request.form.get('rent_amount')
    last_payment_date = request.form.get('last_payment_date') or None # 新增字段

    # 验证必填字段
    if not all([company_name, contact_person, email, payment_cycle, unit_number, rent_amount]):
        flash('公司名称、联系人、邮箱、付费方式、单元号、租金为必填项', 'error')
        return redirect(url_for('index'))

    try:
        rent_amount = float(rent_amount)
    except ValueError:
        flash('租金必须是数字', 'error')
        return redirect(url_for('index'))

    if not last_payment_date:
        flash('上次付费时间不能为空，用于计算下次到期日', 'error')
        return redirect(url_for('index'))

    # 添加租户
    tenant_id = add_tenant(company_name, contact_person, email, phone, payment_cycle, move_in_date)

    # 根据付费周期和上次付费日期计算下次到期日
    cycle_days = get_payment_cycle_days(payment_cycle)
    if cycle_days == 0:
        flash('无效的付费周期', 'error')
        return redirect(url_for('index'))

    last_pay_date_obj = datetime.strptime(last_payment_date, '%Y-%m-%d')
    next_due_date_obj = last_pay_date_obj + timedelta(days=cycle_days)
    next_due_date = next_due_date_obj.strftime('%Y-%m-%d')

    # 添加合同
    contract_id = add_contract(tenant_id, unit_number, rent_amount, next_due_date, last_payment_date)

    flash(f'租户 {company_name} 和合同添加成功！租户ID: {tenant_id}, 合同ID: {contract_id}', 'success')
    return redirect(url_for('index'))

@app.route('/mark_paid/<int:contract_id>', methods=['POST'])
def mark_paid_route(contract_id):
    """标记合同为已付款，计算并更新下次到期日"""
    # 从表单获取实际付款日期，默认为今天
    actual_payment_date_str = request.form.get('payment_date') or datetime.now().strftime('%Y-%m-%d')

    try:
        actual_payment_date = datetime.strptime(actual_payment_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('付款日期格式不正确', 'error')
        return redirect(url_for('index'))

    # 获取当前合同信息
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT t.payment_cycle FROM contracts c JOIN tenants t ON c.tenant_id = t.id WHERE c.id = ?', (contract_id,))
    result = c.fetchone()
    if not result:
        flash('合同不存在', 'error')
        return redirect(url_for('index'))
    
    payment_cycle = result['payment_cycle']
    conn.close()

    # 计算下次到期日（基于实际付款日期）
    cycle_days = get_payment_cycle_days(payment_cycle)
    if cycle_days == 0:
        flash('无效的付费周期', 'error')
        return redirect(url_for('index'))

    new_due_date_obj = actual_payment_date + timedelta(days=cycle_days)
    new_due_date = new_due_date_obj.strftime('%Y-%m-%d')

    # 更新合同状态
    update_contract_payment_status(contract_id, new_due_date, actual_payment_date_str)

    flash(f'合同已标记为已付款，付款日期: {actual_payment_date_str}，下次到期日更新为: {new_due_date}', 'success')
    return redirect(url_for('index'))

@app.route('/send_now')
def send_now():
    """手动触发催收（用于演示）"""
    send_reminders()
    flash('催收任务已手动执行！', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    print("启动物业催收系统...")
    print("访问 http://127.0.0.1:5000 查看系统")
    print("系统将每天早上 9 点自动检查并发送催收邮件")
    app.run(debug=True, host='127.0.0.1', port=5000)
