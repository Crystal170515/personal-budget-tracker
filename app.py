import csv
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash

# --- ตั้งค่า Flask App ---
app = Flask(__name__)
# 🚨 สำคัญมาก: เปลี่ยน 'your_very_secret_key' เป็นคีย์ลับของคุณเอง!
# ใช้สำหรับเข้ารหัส session ของผู้ใช้
app.config['SECRET_KEY'] = 'Test-project-PSCP101'


# --- ค่าคงที่และหมวดหมู่ (เหมือนเดิม) ---
USERS_FILE = "users.csv"
DATA_FILE = "transactions.csv"

EXPENSE_CATEGORIES = ["Bill", "Food and Drink",
                      "Transport", "Shopping", "Investment", "Utility", "Education"]
INCOME_CATEGORIES = ["Salary", "Gift", "Passive Income", "Refund"]


# --- ฟังก์ชันจัดการ User (เหมือนเดิม) ---
def load_users():
    """โหลดข้อมูลผู้ใช้ทั้งหมดจากไฟล์ users.csv และเก็บเป็น dict {username: password}"""
    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 2:
                    users[row[0]] = row[1]
    return users


def save_user(username, password):
    """บันทึกชื่อผู้ใช้และรหัสผ่านใหม่ลงไฟล์ users.csv"""
    # ⚠️ หมายเหตุ: ในแอปจริง ควร "hash" รหัสผ่านก่อนบันทึก
    # แต่สำหรับโปรเจกต์นี้ เราจะบันทึกแบบข้อความธรรมดาตามโค้ดเดิม
    with open(USERS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([username, password])


# --- ฟังก์ชัน Refactored สำหรับดึงข้อมูล (ปรับจากโค้ดเดิม) ---
# เราจะปรับฟังก์ชันที่เคย print() ให้ return ข้อมูลออกมาเป็น List/Dict แทน

def get_transactions(username):
    """ดึงธุรกรรมทั้งหมดของผู้ใช้ และคำนวณยอดคงเหลือ"""
    transactions = []
    balance = 0
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 6 and row[0] == username:
                    date_str, t_type, category, amount_str, desc = row[1], row[2], row[3], row[4], row[5]
                    amount = float(amount_str)
                    
                    if t_type == "income":
                        balance += amount
                    elif t_type == "expense":
                        balance -= amount
                    
                    transactions.append({
                        "date": datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d"),
                        "type": t_type,
                        "category": category,
                        "amount": amount,
                        "description": desc,
                        "sign": "+" if t_type == "income" else "-"
                    })
    # เรียงลำดับธุรกรรมจากใหม่ไปเก่า
    return sorted(transactions, key=lambda x: x['date'], reverse=True), balance


def save_transaction(username, t_type, category, amount, description):
    """บันทึกธุรกรรมใหม่ (ย้ายมาจาก add_transaction)"""
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         t_type, category, amount, description])


def get_weekly_average(username):
    """คำนวณค่าเฉลี่ยรายรับ/จ่ายต่อสัปดาห์ (ย้อนหลัง 30 วัน)"""
    now = datetime.now()
    last_month = now - timedelta(days=30)
    income_total, expense_total = 0, 0

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 6 and row[0] == username:
                    date = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
                    if date >= last_month:
                        amount = float(row[4])
                        if row[2] == "income":
                            income_total += amount
                        elif row[2] == "expense":
                            expense_total += amount
    
    # 30 วัน / 7 วันต่อสัปดาห์ ≈ 4.28 สัปดาห์
    # เราใช้ 4 เพื่อความง่ายตามโค้ดเดิม
    return income_total / 4, expense_total / 4


def get_budget_report(username, budget):
    """คำนวณยอดรวมรายจ่ายเทียบกับงบประมาณ"""
    total_expense = 0
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 6 and row[0] == username and row[2] == "expense":
                    total_expense += float(row[4])
    
    is_over_budget = total_expense > budget
    return total_expense, is_over_budget


def get_category_ratios(username):
    """คำนวณสัดส่วนรายรับ/รายจ่ายตามหมวดหมู่"""
    totals = {}
    overall_income, overall_expense = 0, 0

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 6 and row[0] == username:
                    t_type, category, amount = row[2], row[3], float(row[4])
                    totals[category] = totals.get(category, 0) + amount
                    if t_type == "income":
                        overall_income += amount
                    elif t_type == "expense":
                        overall_expense += amount
    
    income_ratios = []
    expense_ratios = []
    
    for category, total in totals.items():
        if category in INCOME_CATEGORIES and overall_income > 0:
            percent = (total / overall_income) * 100
            income_ratios.append({"category": category, "percent": percent})
        elif category in EXPENSE_CATEGORIES and overall_expense > 0:
            percent = (total / overall_expense) * 100
            expense_ratios.append({"category": category, "percent": percent})
            
    return income_ratios, expense_ratios


# --- Decorator สำหรับตรวจสอบการล็อกอิน ---
def login_required(f):
    """สร้าง Decorator เพื่อตรวจสอบว่าผู้ใช้ล็อกอินหรือยัง"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash("Please log in to access this page.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# --- Routes (เส้นทางเว็บ) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    """หน้าสำหรับล็อกอิน"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        users = load_users()
        if username in users and users[username] == password:
            session['username'] = username  # บันทึกการล็อกอินใน session
            flash(f"Welcome back, {username}!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password.", "danger")
            
    return render_template('login.html')


@app.route('/register', methods=['POST'])
def register():
    """ฟังก์ชันสำหรับสมัครสมาชิก (รับค่าจากฟอร์มในหน้า /login)"""
    username = request.form['username']
    password = request.form['password']
    
    users = load_users()
    if username in users:
        flash("Username already exists.", "warning")
    elif not username or not password:
         flash("Username and password are required.", "warning")
    else:
        save_user(username, password)
        flash("User registered successfully. Please log in.", "success")
        
    return redirect(url_for('login'))


@app.route('/logout')
@login_required
def logout():
    """ออกจากระบบ"""
    session.pop('username', None) # เคลียร์ session
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """หน้าหลัก (แดชบอร์ด) แสดงธุรกรรม"""
    username = session['username']
    transactions, balance = get_transactions(username)
    return render_template('index.html', 
                           transactions=transactions, 
                           balance=balance)


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """หน้าเพิ่มธุรกรรม"""
    if request.method == 'POST':
        username = session['username']
        t_type = request.form['type']
        category = request.form['category']
        description = request.form['description']
        
        # ตรวจสอบค่า
        try:
            amount = float(request.form['amount'])
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash("Amount must be a positive number.", "danger")
            return redirect(url_for('add'))
        
        # ตรวจสอบหมวดหมู่
        if (t_type == 'income' and category not in INCOME_CATEGORIES) or \
           (t_type == 'expense' and category not in EXPENSE_CATEGORIES):
            flash("Invalid category selected.", "danger")
            return redirect(url_for('add'))

        # บันทึกข้อมูล
        save_transaction(username, t_type, category, amount, description)
        flash("Transaction added successfully.", "success")
        return redirect(url_for('index'))

    # (GET Request) แสดงฟอร์ม
    return render_template('add.html', 
                           income_categories=INCOME_CATEGORIES, 
                           expense_categories=EXPENSE_CATEGORIES)


@app.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    """หน้ารายงานสรุปผล"""
    username = session['username']
    
    # 1. คำนวณค่าเฉลี่ยรายสัปดาห์
    avg_income, avg_expense = get_weekly_average(username)
    
    # 2. คำนวณสัดส่วนหมวดหมู่
    income_ratios, expense_ratios = get_category_ratios(username)
    
    # 3. จัดการเรื่องงบประมาณ (Budget)
    budget_data = None
    if request.method == 'POST':
        try:
            budget_input = float(request.form['budget'])
            total_expense, is_over = get_budget_report(username, budget_input)
            budget_data = {
                "budget": budget_input,
                "total_expense": total_expense,
                "is_over": is_over
            }
        except ValueError:
            flash("Budget must be a number.", "danger")

    return render_template('reports.html',
                           avg_income=avg_income,
                           avg_expense=avg_expense,
                           income_ratios=income_ratios,
                           expense_ratios=expense_ratios,
                           budget_data=budget_data)


# --- สั่งให้แอปทำงาน ---
if __name__ == "__main__":
    app.run(debug=True) # debug=True ช่วยให้เราเห็นข้อผิดพลาดตอนพัฒนา