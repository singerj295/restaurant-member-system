from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
from functools import wraps
import os

Base = declarative_base()

# ============ Models ============
class Employee(Base):
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)  # 簡單儲存，生產環境應 hash
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    members = relationship("Member", back_populates="employee")

class Member(Base):
    __tablename__ = 'members'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    tier = Column(String(20), default='普通會員')  # 普通會員, 黑鑽會員
    balance = Column(Float, default=0)  # 儲值金額
    benefits_total = Column(Integer, default=0)   # 總權益次數
    benefits_used = Column(Integer, default=0)    # 已用次數
    # 甜品咖啡每週次數 (每週重置)
    weekly_dessert_coffee = Column(Integer, default=0)
    # 廚師發辦年度次數 (每年重置)
    yearly_omakase = Column(Integer, default=0)
    # 日期
    effective_date = Column(DateTime, default=datetime.utcnow)  # 生效日期
    expiry_date = Column(DateTime)  # 到期日期
    # 使用記錄
    dessert_coffee_used = Column(Integer, default=0)  # 甜品咖啡已用次數
    omakase_used = Column(Integer, default=0)  # 廚師發辦已用次數
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_employee_id = Column(Integer, ForeignKey('employees.id'))
    
    employee = relationship("Employee", back_populates="members")
    
    @property
    def benefits_remaining(self):
        return max(0, self.benefits_total - self.benefits_used)
    
    @property
    def is_active(self):
        """檢查會員是否有效"""
        if self.expiry_date:
            return datetime.utcnow() < self.expiry_date
        return True
    
    def get_weekly_remaining(self):
        """每週剩餘甜品咖啡次數"""
        if self.tier in ['普通會員', '黑鑽會員']:
            return max(0, 1 - self.dessert_coffee_used)
        return 0
    
    def get_yearly_remaining(self):
        """年度剩餘廚師發辦次數"""
        if self.tier == '黑鑽會員':
            return max(0, 2 - self.omakase_used)
        return 0
        if self.tier == '黑鑽會員':
            return max(0, 2 - self.yearly_omakase)
        return 0

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    restaurant_name = Column(String(100), default='我的餐廳')
    dark_mode = Column(Integer, default=0)  # 0 = light, 1 = dark

class Customer(Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    email = Column(String(100))
    birthday = Column(DateTime)
    tags = Column(String(500))  # 標籤，用逗號分隔
    address = Column(String(200))
    avg_spend = Column(Float, default=0.0)
    preferences = Column(Text)  # e.g. "愛辣、不吃蔥"
    allergies = Column(Text)  # 過敏食物
    notes = Column(Text)  # 額外備註
    visits = Column(Integer, default=0)
    total_spent = Column(Float, default=0)  # 總消費
    points = Column(Integer, default=0)  # 積分 (已停用)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class VisitRecord(Base):
    __tablename__ = 'visit_records'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    visit_date = Column(DateTime, default=datetime.utcnow)
    amount = Column(Float, default=0)
    table_number = Column(String(20))
    server = Column(String(100))
    party_size = Column(Integer, default=1)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Interaction(Base):
    __tablename__ = 'interactions'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    type = Column(String(50))  # call, complaint, compliment, request, marketing
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_employee_id = Column(Integer, ForeignKey('employees.id'))

class Reservation(Base):
    __tablename__ = 'reservations'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100))
    date = Column(DateTime, nullable=False)
    party_size = Column(Integer, default=1)
    table_number = Column(String(20))
    status = Column(String(20), default='confirmed')  # confirmed, seated, completed, no_show, cancelled
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_employee_id = Column(Integer, ForeignKey('employees.id'))

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey('members.id'), nullable=True)
    original_amount = Column(Float, nullable=False)  # 原始金額
    discount_amount = Column(Float, default=0)  # 折扣金額
    final_amount = Column(Float, nullable=False)  # 最終金額
    paid_from_balance = Column(Float, default=0)  # 由儲值扣款
    cash_paid = Column(Float, default=0)  # 現金支付
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_employee_id = Column(Integer, ForeignKey('employees.id'))
    note = Column(Text)

# ============ Database Setup ============
engine = create_engine('sqlite:///restaurant.db', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

app = Flask(__name__)
app.secret_key = 'restaurant-secret-key-change-in-production'

# Prevent caching
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ============ Context Processor for Dark Mode ============
@app.context_processor
def inject_dark_mode():
    db = get_db_session()
    settings_obj = db.query(Settings).first()
    dark_mode = settings_obj.dark_mode if settings_obj else 0
    restaurant_name = settings_obj.restaurant_name if settings_obj else '我的餐廳'
    db.close()
    return dict(dark_mode=dark_mode, restaurant_name=restaurant_name)

# ============ Helpers ============
def get_db_session():
    return Session()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============ Routes ============

@app.route('/')
def index():
    if 'employee_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# --- 員工登入 ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    db = get_db_session()
    settings_obj = db.query(Settings).first()
    dark_mode = settings_obj.dark_mode if settings_obj else 0
    db.close()
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db_session()
        employee = db.query(Employee).filter_by(username=username).first()
        
        if employee and employee.password == password:
            session['employee_id'] = employee.id
            session['employee_name'] = employee.name
            db.close()
            return redirect(url_for('dashboard'))
        
        db.close()
        flash('用戶名或密碼錯誤', 'error')
    
    return render_template('login.html', dark_mode=dark_mode)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/register_employee', methods=['GET', 'POST'])
def register_employee():
    """員工註冊"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        
        db = get_db_session()
        
        # 檢查 username 是否已存在
        existing = db.query(Employee).filter_by(username=username).first()
        if existing:
            flash('用戶名已存在', 'error')
            db.close()
            return render_template('register_employee.html')
        
        employee = Employee(username=username, password=password, name=name)
        db.add(employee)
        db.commit()
        db.close()
        
        flash('註冊成功，請登入', 'success')
        return redirect(url_for('login'))
    
    return render_template('register_employee.html')

# --- Dashboard ---
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db_session()
    member_count = db.query(Member).count()
    customer_count = db.query(Customer).count()
    employee_name = session.get('employee_name')
    
    # 獲取設定
    settings_obj = db.query(Settings).first()
    restaurant_name = settings_obj.restaurant_name if settings_obj else '我的餐廳'
    dark_mode = settings_obj.dark_mode if settings_obj else 0
    
    # 今日預訂
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    today_reservations = db.query(Reservation).filter(
        Reservation.date >= today,
        Reservation.date < tomorrow,
        Reservation.status.in_(['confirmed', 'seated', 'booked'])
    ).order_by(Reservation.date).all()
    
    # 今日營業額（從transactions表或顧客消費計算）
    today_revenue = db.query(Customer).with_entities(
        db.func.sum(Customer.total_spent)
    ).scalar() or 0
    
    # 最近加入的會員
    recent_members = db.query(Member).order_by(Member.effective_date.desc()).limit(5).all()
    
    # 總會員儲值
    total_balance = db.query(Member).with_entities(
        db.func.sum(Member.balance)
    ).scalar() or 0
    
    # 今日日期字符串
    today_str = today.strftime('%Y-%m-%d')
    
    db.close()
    return render_template('dashboard.html', 
                         member_count=member_count, 
                         customer_count=customer_count,
                         employee_name=employee_name,
                         restaurant_name=restaurant_name,
                         dark_mode=dark_mode,
                         today_reservations=today_reservations,
                         today_revenue=today_revenue,
                         recent_members=recent_members,
                         total_balance=total_balance,
                         today_str=today_str)

# --- 會員管理 ---
@app.route('/members')
@login_required
def members():
    db = get_db_session()
    search = request.args.get('search', '').strip()
    if search:
        members_list = db.query(Member).filter(
            (Member.name.like(f'%{search}%')) | 
            (Member.phone.like(f'%{search}%'))
        ).all()
    else:
        members_list = db.query(Member).all()
    db.close()
    return render_template('members.html', members=members_list, search=search)

@app.route('/members/add', methods=['GET', 'POST'])
@login_required
def add_member():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        tier = request.form.get('tier', '普通會員')
        balance = float(request.form.get('balance', 0))
        effective_date_str = request.form.get('effective_date')
        
        db = get_db_session()
        
        # 檢查手機是否已存在
        existing = db.query(Member).filter_by(phone=phone).first()
        if existing:
            flash('此手機號碼已註冊', 'error')
            db.close()
            return render_template('add_member.html')
        
        # 處理生效日期
        if effective_date_str:
            effective_date = datetime.strptime(effective_date_str, '%Y-%m-%d')
        else:
            effective_date = datetime.utcnow()
        
        # 計算到期日期 (1年後)
        expiry_date = effective_date + timedelta(days=365)
        
        member = Member(
            name=name,
            phone=phone,
            tier=tier,
            balance=balance,
            benefits_total=0,
            benefits_used=0,
            dessert_coffee_used=0,
            omakase_used=0,
            effective_date=effective_date,
            expiry_date=expiry_date,
            created_by_employee_id=session['employee_id']
        )
        db.add(member)
        db.commit()
        db.close()
        
        flash('會員註冊成功', 'success')
        return redirect(url_for('members'))
    
    return render_template('add_member.html')

@app.route('/members/use_benefit/<int:member_id>', methods=['POST'])
@login_required
def use_benefit(member_id):
    db = get_db_session()
    member = db.query(Member).get(member_id)
    
    if member and member.benefits_remaining > 0:
        member.benefits_used += 1
        db.commit()
        flash(f'已扣用一次權益，剩餘 {member.benefits_remaining} 次', 'success')
    else:
        flash('權益已用完', 'error')
    
    db.close()
    return redirect(url_for('members'))

@app.route('/members/use_dessert_coffee/<int:member_id>', methods=['POST'])
@login_required
def use_dessert_coffee(member_id):
    """扣用每週甜品咖啡"""
    db = get_db_session()
    member = db.query(Member).get(member_id)
    
    if member and (member.tier == '普通會員' or member.tier == '黑鑽會員'):
        if member.dessert_coffee_used < 1:
            member.dessert_coffee_used += 1
            db.commit()
            flash(f'已扣用甜品咖啡，共已用 {member.dessert_coffee_used} 次', 'success')
        else:
            flash('本週甜品咖啡已用完', 'error')
    else:
        flash('此會員級別無此權益', 'error')
    
    db.close()
    return redirect(url_for('members'))

@app.route('/members/use_omakase/<int:member_id>', methods=['POST'])
@login_required
def use_omakase(member_id):
    """扣用年度廚師發辦"""
    db = get_db_session()
    member = db.query(Member).get(member_id)
    
    if member and member.tier == '黑鑽會員':
        if member.omakase_used < 2:
            member.omakase_used += 1
            db.commit()
            flash(f'已扣用廚師發辦套餐，共已用 {member.omakase_used}/2 次', 'success')
        else:
            flash('本年度廚師發辦已用完', 'error')
    else:
        flash('只有黑鑽會員有此權益', 'error')
    
    db.close()
    return redirect(url_for('members'))

@app.route('/members/reset_weekly/<int:member_id>', methods=['POST'])
@login_required
def reset_weekly(member_id):
    """重置每週權益 (管理員手動)"""
    db = get_db_session()
    member = db.query(Member).get(member_id)
    
    if member:
        member.weekly_dessert_coffee = 0
        db.commit()
        flash('每週權益已重置', 'success')
    
    db.close()
    return redirect(url_for('members'))

@app.route('/members/edit/<int:member_id>', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    db = get_db_session()
    member = db.query(Member).get(member_id)
    
    if not member:
        db.close()
        flash('會員不存在', 'error')
        return redirect(url_for('members'))
    
    if request.method == 'POST':
        member.name = request.form['name']
        member.phone = request.form['phone']
        member.tier = request.form.get('tier', '普通會員')
        member.balance = float(request.form.get('balance', 0))
        
        effective_date_str = request.form.get('effective_date')
        if effective_date_str:
            member.effective_date = datetime.strptime(effective_date_str, '%Y-%m-%d')
        
        expiry_date_str = request.form.get('expiry_date')
        if expiry_date_str:
            member.expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        
        db.commit()
        flash('會員資料已更新', 'success')
        db.close()
        return redirect(url_for('members'))
    
    result = render_template('edit_member.html', member=member)
    db.close()
    return result

@app.route('/members/topup/<int:member_id>', methods=['GET', 'POST'])
@login_required
def topup_member(member_id):
    """儲值"""
    db = get_db_session()
    member = db.query(Member).get(member_id)
    
    if not member:
        db.close()
        flash('會員不存在', 'error')
        return redirect(url_for('members'))
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        if amount > 0:
            member.balance += amount
            new_balance = member.balance  # Save before closing
            db.commit()
            db.close()
            flash(f'儲值成功！現有餘額: ${new_balance:.2f}', 'success')
            return redirect(url_for('members'))
        else:
            result = render_template('topup.html', member=member)
            db.close()
            return result
    
    result = render_template('topup.html', member=member)
    db.close()
    return result

@app.route('/members/delete/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    db = get_db_session()
    member = db.query(Member).get(member_id)
    if member:
        db.delete(member)
        db.commit()
        flash('會員已刪除', 'success')
    db.close()
    return redirect(url_for('members'))

# --- 結帳 ---
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    db = get_db_session()
    search_phone = request.args.get('phone', '')
    
    # 如果有電話搜尋
    members = []
    if search_phone:
        members = db.query(Member).filter(
            Member.phone.like(f'%{search_phone}%')
        ).order_by(Member.name).all()
    # 如果有指定會員ID
    preselected_member_id = request.args.get('member_id')
    if preselected_member_id:
        member = db.query(Member).get(preselected_member_id)
        if member and member not in members:
            members.insert(0, member)
    
    db.close()
    
    if request.method == 'POST':
        member_id = request.form.get('member_id')
        original_amount = float(request.form.get('original_amount', 0))
        use_balance = request.form.get('use_balance') == 'on'
        
        if not member_id:
            flash('請選擇會員', 'error')
            db.close()
            return render_template('checkout.html', members=members, search_phone=search_phone)
        
        member = db.query(Member).get(member_id)
        
        if not member:
            flash('會員不存在', 'error')
            db.close()
            return render_template('checkout.html', members=members, search_phone=search_phone)
        
        # 獲取會員資料
        member_name = member.name
        member_tier = member.tier
        member_balance = member.balance
        
        # 計算折扣
        discount_amount = 0
        if member_tier == '黑鑽會員':
            discount_amount = original_amount * 0.20  # 20% 折扣
        
        final_amount = original_amount - discount_amount
        
        # 計算扣款
        paid_from_balance = 0
        if use_balance and member_balance > 0:
            paid_from_balance = min(member_balance, final_amount)
            member.balance -= paid_from_balance
        
        remaining_balance = member.balance
        cash_paid = final_amount - paid_from_balance
        
        # 記錄交易
        transaction = Transaction(
            member_id=member.id,
            original_amount=original_amount,
            discount_amount=discount_amount,
            final_amount=final_amount,
            paid_from_balance=paid_from_balance,
            cash_paid=cash_paid,
            created_by_employee_id=session['employee_id'],
            note=f"{member_tier} - 折扣${discount_amount:.2f}"
        )
        db.add(transaction)
        db.commit()
        db.close()
        
        # 顯示結果
        return render_template('checkout_result.html', 
                             member_name=member_name,
                             member_tier=member_tier,
                             original_amount=original_amount,
                             discount_amount=discount_amount,
                             final_amount=final_amount,
                             paid_from_balance=paid_from_balance,
                             cash_paid=cash_paid,
                             remaining_balance=remaining_balance)
    
    return render_template('checkout.html', members=members, search_phone=search_phone)

# --- 顧客管理 ---
@app.route('/customers')
@login_required
def customers():
    db = get_db_session()
    search = request.args.get('search', '').strip()
    if search:
        customers_list = db.query(Customer).filter(
            (Customer.name.like(f'%{search}%')) | 
            (Customer.phone.like(f'%{search}%'))
        ).all()
    else:
        customers_list = db.query(Customer).all()
    db.close()
    return render_template('customers.html', customers=customers_list, search=search)

@app.route('/customers/add', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        
        db = get_db_session()
        
        existing = db.query(Customer).filter_by(phone=phone).first()
        if existing:
            flash('此手機號碼已存在', 'error')
            db.close()
            return render_template('add_customer.html')
        
        # 處理生日
        birthday = None
        birthday_str = request.form.get('birthday')
        if birthday_str:
            birthday = datetime.strptime(birthday_str, '%Y-%m-%d')
        
        customer = Customer(
            name=name,
            phone=phone,
            email=request.form.get('email', ''),
            birthday=birthday,
            tags=request.form.get('tags', ''),
            address=request.form.get('address', ''),
            allergies=request.form.get('allergies', ''),
            preferences=request.form.get('preferences', ''),
            visits=0,
            total_spent=0,
            points=0
        )
        db.add(customer)
        db.commit()
        db.close()
        
        flash('顧客新增成功', 'success')
        return redirect(url_for('customers'))
    
    return render_template('add_customer.html')

@app.route('/customers/edit/<int:customer_id>', methods=['GET', 'POST'])
@login_required
def edit_customer(customer_id):
    db = get_db_session()
    customer = db.query(Customer).get(customer_id)
    
    if not customer:
        db.close()
        flash('顧客不存在', 'error')
        return redirect(url_for('customers'))
    
    if request.method == 'POST':
        customer.name = request.form['name']
        customer.phone = request.form['phone']
        customer.email = request.form.get('email', '')
        
        birthday_str = request.form.get('birthday')
        if birthday_str:
            customer.birthday = datetime.strptime(birthday_str, '%Y-%m-%d')
        
        customer.tags = request.form.get('tags', '')
        customer.address = request.form.get('address', '')
        customer.allergies = request.form.get('allergies', '')
        customer.preferences = request.form.get('preferences', '')
        
        db.commit()
        flash('顧客資料已更新', 'success')
        db.close()
        return redirect(url_for('customers'))
    
    result = render_template('edit_customer.html', customer=customer)
    db.close()
    return result

@app.route('/customers/visit/<int:customer_id>', methods=['POST'])
@login_required
def add_visit(customer_id):
    db = get_db_session()
    customer = db.query(Customer).get(customer_id)
    
    if customer:
        customer.visits += 1
        # 更新人均消費
        new_spend = float(request.form.get('spend', 0))
        if new_spend > 0:
            customer.avg_spend = ((customer.avg_spend * (customer.visits - 1)) + new_spend) / customer.visits
        db.commit()
        flash(f'已記錄訪問，總訪問次數: {customer.visits}', 'success')
    
    db.close()
    return redirect(url_for('customers'))

@app.route('/customers/delete/<int:customer_id>', methods=['POST'])
@login_required
def delete_customer(customer_id):
    db = get_db_session()
    customer = db.query(Customer).get(customer_id)
    if customer:
        db.delete(customer)
        db.commit()
        flash('顧客已刪除', 'success')
    db.close()
    return redirect(url_for('customers'))

# --- 顧客訪問記錄 ---
@app.route('/customers/<int:customer_id>/visits')
@login_required
def customer_visits(customer_id):
    db = get_db_session()
    customer = db.query(Customer).get(customer_id)
    visits = db.query(VisitRecord).filter_by(customer_id=customer_id).order_by(VisitRecord.visit_date.desc()).all()
    db.close()
    return render_template('customer_visits.html', customer=customer, visits=visits)

@app.route('/customers/<int:customer_id>/visits/add', methods=['GET', 'POST'])
@login_required
def add_visit_record(customer_id):
    db = get_db_session()
    customer = db.query(Customer).get(customer_id)
    
    if not customer:
        db.close()
        flash('顧客不存在', 'error')
        return redirect(url_for('customers'))
    
    if request.method == 'POST':
        visit_date = datetime.strptime(request.form.get('visit_date'), '%Y-%m-%dT%H:%M') if request.form.get('visit_date') else datetime.utcnow()
        amount = float(request.form.get('amount', 0))
        
        visit = VisitRecord(
            customer_id=customer_id,
            visit_date=visit_date,
            amount=amount,
            table_number=request.form.get('table_number', ''),
            server=request.form.get('server', ''),
            party_size=int(request.form.get('party_size', 1)),
            note=request.form.get('note', '')
        )
        
        # 更新顧客統計
        customer.visits += 1
        customer.total_spent += amount
        if customer.visits > 0:
            customer.avg_spend = customer.total_spent / customer.visits
        
        db.add(visit)
        db.commit()
        flash('訪問記錄已添加', 'success')
        db.close()
        return redirect(url_for('customer_visits', customer_id=customer_id))
    
    db.close()
    return render_template('add_visit_record.html', customer=customer, now=datetime.utcnow())

# --- 顧客互動記錄 ---
@app.route('/customers/<int:customer_id>/interactions')
@login_required
def customer_interactions(customer_id):
    db = get_db_session()
    customer = db.query(Customer).get(customer_id)
    interactions = db.query(Interaction).filter_by(customer_id=customer_id).order_by(Interaction.created_at.desc()).all()
    db.close()
    return render_template('customer_interactions.html', customer=customer, interactions=interactions)

@app.route('/customers/<int:customer_id>/interactions/add', methods=['GET', 'POST'])
@login_required
def add_interaction(customer_id):
    db = get_db_session()
    customer = db.query(Customer).get(customer_id)
    
    if not customer:
        db.close()
        flash('顧客不存在', 'error')
        return redirect(url_for('customers'))
    
    if request.method == 'POST':
        interaction = Interaction(
            customer_id=customer_id,
            type=request.form.get('type'),
            note=request.form.get('note', ''),
            created_by_employee_id=session['employee_id']
        )
        db.add(interaction)
        db.commit()
        flash('互動記錄已添加', 'success')
        db.close()
        return redirect(url_for('customer_interactions', customer_id=customer_id))
    
    db.close()
    return render_template('add_interaction.html', customer=customer)

# --- 預訂管理 ---
@app.route('/reservations')
@login_required
def reservations():
    db = get_db_session()
    date_filter = request.args.get('date')
    search = request.args.get('search', '').strip()
    
    query = db.query(Reservation)
    
    if search:
        query = query.filter(
            (Reservation.name.like(f'%{search}%')) | 
            (Reservation.phone.like(f'%{search}%'))
        )
    
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
            query = query.filter(
                Reservation.date >= filter_date,
                Reservation.date < filter_date + timedelta(days=1)
            )
        except:
            pass
    
    reservations_list = query.order_by(Reservation.date.desc()).limit(50).all()
    
    db.close()
    return render_template('reservations.html', reservations=reservations_list, search=search)

# --- 預訂日曆 ---
@app.route('/reservations/calendar')
@login_required
def reservations_calendar():
    db = get_db_session()
    
    # 獲取本月預訂
    today = datetime.utcnow()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if today.month == 12:
        month_end = today.replace(year=today.year+1, month=1, day=1)
    else:
        month_end = today.replace(month=today.month+1, day=1)
    
    reservations = db.query(Reservation).filter(
        Reservation.date >= month_start,
        Reservation.date < month_end
    ).all()
    
    # 轉換為JSON格式
    events = []
    for r in reservations:
        events.append({
            'id': r.id,
            'title': f"{r.name} ({r.party_size}位)",
            'start': r.date.strftime('%Y-%m-%dT%H:%M'),
            'phone': r.phone,
            'status': r.status,
            'table': r.table_number or '-'
        })
    
    db.close()
    return render_template('reservations_calendar.html', events=events, current_month=today.strftime('%Y-%m'))

@app.route('/reservations/add', methods=['GET', 'POST'])
@login_required
def add_reservation():
    db = get_db_session()
    
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        date = datetime.strptime(request.form['date'] + ' ' + request.form['time'], '%Y-%m-%d %H:%M')
        
        reservation = Reservation(
            name=name,
            phone=phone,
            email=request.form.get('email', ''),
            date=date,
            party_size=int(request.form.get('party_size', 1)),
            table_number=request.form.get('table_number', ''),
            note=request.form.get('note', ''),
            created_by_employee_id=session['employee_id']
        )
        
        db.add(reservation)
        db.commit()
        flash('預訂已添加', 'success')
        db.close()
        return redirect(url_for('reservations'))
    
    db.close()
    return render_template('add_reservation.html')

@app.route('/reservations/<int:res_id>/update', methods=['POST'])
@login_required
def update_reservation(res_id):
    db = get_db_session()
    reservation = db.query(Reservation).get(res_id)
    
    if reservation:
        reservation.status = request.form.get('status')
        reservation.table_number = request.form.get('table_number', '')
        db.commit()
        flash('預訂狀態已更新', 'success')
    
    db.close()
    return redirect(url_for('reservations'))

@app.route('/reservations/<int:res_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_reservation(res_id):
    db = get_db_session()
    reservation = db.query(Reservation).get(res_id)
    
    if not reservation:
        db.close()
        flash('預訂不存在', 'error')
        return redirect(url_for('reservations'))
    
    if request.method == 'POST':
        reservation.name = request.form.get('name')
        reservation.phone = request.form.get('phone')
        reservation.email = request.form.get('email', '')
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        if date_str and time_str:
            reservation.date = datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')
        reservation.party_size = int(request.form.get('party_size', 1))
        reservation.table_number = request.form.get('table_number', '')
        reservation.status = request.form.get('status')
        reservation.note = request.form.get('note', '')
        db.commit()
        flash('預訂已更新', 'success')
        db.close()
        return redirect(url_for('reservations'))
    
    db.close()
    return render_template('edit_reservation.html', reservation=reservation, restaurant_name=session.get('restaurant_name', '餐廳'))

@app.route('/reservations/<int:res_id>/delete', methods=['POST'])
@login_required
def delete_reservation(res_id):
    db = get_db_session()
    reservation = db.query(Reservation).get(res_id)
    
    if reservation:
        db.delete(reservation)
        db.commit()
        flash('預訂已刪除', 'success')
    
    db.close()
    return redirect(url_for('reservations'))

# --- 匯出功能 ---
@app.route('/export/<type>')
@login_required
def export_data(type):
    import io
    from openpyxl import Workbook
    
    db = get_db_session()
    wb = Workbook()
    
    if type == 'members':
        ws = wb.active
        ws.title = "會員"
        ws.append(['ID', '姓名', '電話', '等級', '儲值', '狀態', '入會日期'])
        members = db.query(Member).all()
        for m in members:
            ws.append([m.id, m.name, m.phone, m.tier, m.balance, '有效' if m.is_active else '過期', m.effective_date.strftime('%Y-%m-%d') if m.effective_date else ''])
        filename = 'members_export.xlsx'
    
    elif type == 'customers':
        ws = wb.active
        ws.title = "顧客"
        ws.append(['ID', '姓名', '電話', '電郵', '總消費', '訪問次數'])
        customers = db.query(Customer).all()
        for c in customers:
            ws.append([c.id, c.name, c.phone, c.email or '', c.total_spent, c.visits])
        filename = 'customers_export.xlsx'
    
    elif type == 'reservations':
        ws = wb.active
        ws.title = "預訂"
        ws.append(['ID', '姓名', '電話', '日期', '人數', '座位', '狀態'])
        reservations = db.query(Reservation).order_by(Reservation.date.desc()).all()
        for r in reservations:
            ws.append([r.id, r.name, r.phone, r.date.strftime('%Y-%m-%d %H:%M'), r.party_size, r.table_number or '', r.status])
        filename = 'reservations_export.xlsx'
    
    else:
        db.close()
        flash('無效的匯出類型', 'error')
        return redirect(url_for('dashboard'))
    
    db.close()
    
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    return send_file(buffer, download_name=filename, as_attachment=True)

# --- 分析儀表板 ---
@app.route('/analytics')
@login_required
def analytics():
    from sqlalchemy import func as sql_func
    db = get_db_session()
    
    # 顧客統計
    total_customers = db.query(Customer).count()
    total_visits = db.query(Customer).with_entities(sql_func.sum(Customer.visits)).scalar() or 0
    total_revenue = db.query(Customer).with_entities(sql_func.sum(Customer.total_spent)).scalar() or 0
    avg_spend = db.query(Customer).with_entities(sql_func.avg(Customer.avg_spend)).scalar() or 0
    
    # 會員統計
    total_members = db.query(Member).count()
    active_members = db.query(Member).filter(Member.expiry_date >= datetime.utcnow()).count()
    
    # 預訂統計
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    today_reservations = db.query(Reservation).filter(
        Reservation.date >= today,
        Reservation.date < tomorrow
    ).count()
    
    # 最近顧客 (消費最高)
    top_customers = db.query(Customer).order_by(Customer.total_spent.desc()).limit(10).all()
    
    # 最近預訂
    upcoming_reservations = db.query(Reservation).filter(
        Reservation.date >= datetime.utcnow(),
        Reservation.status.in_(['confirmed', 'seated'])
    ).order_by(Reservation.date).limit(10).all()
    
    db.close()
    
    return render_template('analytics.html',
                         total_customers=total_customers,
                         total_visits=total_visits,
                         total_revenue=total_revenue,
                         avg_spend=avg_spend,
                         total_members=total_members,
                         active_members=active_members,
                         today_reservations=today_reservations,
                         top_customers=top_customers,
                         upcoming_reservations=upcoming_reservations)

# ============ Init DB with default employee ============
def init_db():
    db = Session()
    # 檢查是否已有員工
    if db.query(Employee).count() == 0:
        # 預設員工: admin / admin123
        admin = Employee(username='admin', password='admin123', name='管理員')
        db.add(admin)
        db.commit()
        print("✅ 已建立預設管理員: admin / admin123")
    
    # 確保設定存在
    if db.query(Settings).count() == 0:
        settings = Settings(restaurant_name='我的餐廳', dark_mode=0)
        db.add(settings)
        db.commit()
    
    db.close()

# --- 設定 ---
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    db = get_db_session()
    settings_obj = db.query(Settings).first()
    
    if request.method == 'POST':
        settings_obj.restaurant_name = request.form.get('restaurant_name', '我的餐廳')
        settings_obj.dark_mode = 1 if request.form.get('dark_mode') else 0
        db.commit()
        flash('設定已儲存', 'success')
        db.close()
        return redirect(url_for('dashboard'))
    
    result = render_template('settings.html', settings=settings_obj)
    db.close()
    return result

@app.route('/toggle_dark_mode')
@login_required
def toggle_dark_mode():
    db = get_db_session()
    settings_obj = db.query(Settings).first()
    if settings_obj:
        settings_obj.dark_mode = 1 - settings_obj.dark_mode
        db.commit()
    db.close()
    return redirect(request.referrer or url_for('dashboard'))

# --- 顧客升級為會員 ---
@app.route('/customers/<int:customer_id>/upgrade', methods=['GET', 'POST'])
@login_required
def upgrade_to_member(customer_id):
    db = get_db_session()
    customer = db.query(Customer).get(customer_id)
    
    if not customer:
        flash('顧客不存在', 'error')
        db.close()
        return redirect(url_for('customers'))
    
    if request.method == 'POST':
        tier = request.form.get('tier', '普通會員')
        
        # 檢查手機是否已註冊會員
        existing_member = db.query(Member).filter_by(phone=customer.phone).first()
        if existing_member:
            flash('此電話已存在會員', 'error')
            db.close()
            return redirect(url_for('customers'))
        
        # 計算日期
        effective_date = datetime.utcnow()
        expiry_date = effective_date + timedelta(days=365)
        
        member = Member(
            name=customer.name,
            phone=customer.phone,
            tier=tier,
            email=customer.email,
            balance=0,
            effective_date=effective_date,
            expiry_date=expiry_date,
            created_by_employee_id=session['employee_id']
        )
        db.add(member)
        db.commit()
        flash(f'{customer.name} 已升級為會員 ({tier})', 'success')
        db.close()
        return redirect(url_for('members'))
    
    db.close()
    return render_template('upgrade_to_member.html', customer=customer)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
