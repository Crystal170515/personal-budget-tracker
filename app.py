from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import os, sqlite3
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'change_this_to_something_secret'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'tracker.db')
print("📁 Using database:", DB_PATH)

EXPENSE_CATEGORIES = ['Bill','Food and Drink','Transport','Shopping','Investment','Utility','Education']
INCOME_CATEGORIES = ['Salary','Gift','Passive Income','Refund']

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def add_column_if_missing(conn, table, col_name, col_sql):
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if col_name not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_sql}")
        conn.commit()

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT
        -- อย่าระบุคอลัมน์ใหม่ตรงนี้ซ้ำ เดี๋ยวเราเติมด้วย ALTER TABLE ด้านล่าง
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS budgets(
        user_id INTEGER PRIMARY KEY,
        amount REAL NOT NULL DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS goals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        target_amount REAL NOT NULL,
        current_amount REAL NOT NULL DEFAULT 0,
        deadline TEXT
    )''')

    add_column_if_missing(conn, "transactions", "currency", "TEXT DEFAULT 'THB'")
    add_column_if_missing(conn, "transactions", "amount_thb", "REAL DEFAULT 0")

    conn.commit()
    conn.close()


@app.before_request
def before_request():
    init_db()

def current_user():
    if 'user_id' in session:
        return {'id': session['user_id'], 'username': session.get('username')}
    return None

@app.route('/')
def index():
    if current_user():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        if not username or not password:
            flash('Username and password required','danger')
            return render_template('register.html')
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username,password_hash) VALUES (?,?)',
                      (username, generate_password_hash(password)))
            conn.commit()
            flash('Registered successfully ✅','success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists ❌','danger')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username=?',(username,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful ✅','success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password ❌','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out 👋','info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            SUM(CASE WHEN type='income' THEN amount_thb ELSE 0 END) AS inc,
            SUM(CASE WHEN type='expense' THEN amount_thb ELSE 0 END) AS exp
        FROM transactions WHERE user_id=?
    """, (user['id'],))
    row = c.fetchone()
    inc = row['inc'] or 0
    exp = row['exp'] or 0
    balance = inc - exp

    c.execute('SELECT amount FROM budgets WHERE user_id=?',(user['id'],))
    b = c.fetchone()
    budget_amount = b['amount'] if b else None

    month_start = date.today().replace(day=1)
    if month_start.month == 12:
        next_month_start = date(month_start.year + 1, 1, 1)
    else:
        next_month_start = date(month_start.year, month_start.month + 1, 1)
    start_str = month_start.strftime('%Y-%m-%d') + ' 00:00:00'
    end_str   = next_month_start.strftime('%Y-%m-%d') + ' 00:00:00'

    c.execute("""
        SELECT COALESCE(SUM(amount_thb), 0) AS mexp
        FROM transactions
        WHERE user_id=? AND type='expense' AND date >= ? AND date < ?
    """, (user['id'], start_str, end_str))
    mexp = c.fetchone()['mexp'] or 0

    warn_over = bool(budget_amount and mexp >= 0.8*budget_amount)

    c.execute("""
        SELECT date,
               SUM(CASE WHEN type='income' THEN amount_thb ELSE 0 END) AS inc,
               SUM(CASE WHEN type='expense' THEN amount_thb ELSE 0 END) AS exp
        FROM transactions
        WHERE user_id=?
        GROUP BY substr(date,1,10)
        ORDER BY date DESC
        LIMIT 7
    """, (user['id'],))
    rows = c.fetchall()

    c.execute('SELECT id, name, target_amount, current_amount FROM goals WHERE user_id=? ORDER BY id DESC',
              (user['id'],))
    grows = c.fetchall()
    conn.close()

    labels = []; inc_data=[]; exp_data=[]
    for r in reversed(rows):
        labels.append(r['date'][:10])
        inc_data.append(r['inc'] or 0)
        exp_data.append(r['exp'] or 0)

    goals = []
    for g in grows:
        target = g['target_amount'] or 0
        current = g['current_amount'] or 0
        percent = 0 if target <= 0 else min(100.0, (current / target) * 100.0)
        goals.append({
            'id': g['id'],
            'name': g['name'],
            'target': float(target),
            'current': float(current),
            'percent': float(percent)
        })

    return render_template('dashboard.html',
                           username=user['username'],
                           balance=balance,
                           total_income=inc,
                           total_expense=exp,
                           budget_amount=budget_amount,
                           month_expense=mexp,
                           warn_over=warn_over,
                           labels=labels,
                           income_data=inc_data,
                           expense_data=exp_data,
                           goals=goals)   # << ส่งไป template



@app.route('/add', methods=['GET','POST'])
def add_transaction():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        category = request.form.get('category', '').strip()
        if not category:
            flash('Please choose a category', 'danger')
            return redirect(url_for('add_transaction'))

        if category == 'Other':
            typed = request.form.get('other_category', '').strip()
            if not typed:
                flash('Please type your category name', 'danger')
                return redirect(url_for('add_transaction'))
            category = typed

        t_type = request.form['type']
        desc = request.form.get('description', '')
        date_str = request.form.get('date') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        currency = request.form.get('currency', 'THB')

        try:
            amount = float(request.form['amount'])
        except ValueError:
            flash('Amount must be a number', 'danger')
            return redirect(url_for('add_transaction'))

        amount_thb = amount
        if currency != 'THB':
            try:
                res = requests.get(f'https://v6.exchangerate-api.com/v6/{api_key}/latest/{currency}').json()
                if res.get('result') == 'success':
                    rate = res['conversion_rates']['THB']
                    amount_thb = amount * rate
                    flash(f'Converted {amount} {currency} ≈ {amount_thb:.2f} THB (Rate {rate:.4f})', 'info')
                else:
                    flash('Error fetching conversion rate', 'warning')
            except Exception as e:
                flash(f'Currency conversion failed: {e}', 'danger')

        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO transactions (user_id, date, type, category, amount, description, currency, amount_thb)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user['id'], date_str, t_type, category, amount, desc, currency, amount_thb))
        conn.commit()
        conn.close()

        flash('Transaction added successfully ✅', 'success')
        return redirect(url_for('view_transactions'))

    return render_template('add_transaction.html',
                           income_categories=INCOME_CATEGORIES,
                           expense_categories=EXPENSE_CATEGORIES)



@app.route('/transactions')
def view_transactions():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    month = request.args.get('month')
    cat = request.args.get('category')
    conn = get_db(); c = conn.cursor()
    q = 'SELECT * FROM transactions WHERE user_id=?'
    params = [user['id']]
    if month:
        q += ' AND date LIKE ?'; params.append(month+'%')
    if cat and cat != 'all':
        q += ' AND category=?'; params.append(cat)
    q += ' ORDER BY date DESC'
    c.execute(q, params); rows = c.fetchall()
    c.execute("""
    SELECT
      SUM(CASE WHEN type='income' THEN amount_thb ELSE 0 END) AS inc,
      SUM(CASE WHEN type='expense' THEN amount_thb ELSE 0 END) AS exp
    FROM transactions WHERE user_id=?
""", (user['id'],))

    r = c.fetchone()
    balance = (r['inc'] or 0) - (r['exp'] or 0)
    conn.close()
    return render_template('view_transactions.html',
                           transactions=rows,
                           balance=balance,
                           month=month,
                           category=cat,
                           expense_categories=EXPENSE_CATEGORIES,
                           income_categories=INCOME_CATEGORIES)

@app.route('/budget', methods=['GET','POST'])
def budget():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    conn = get_db(); c = conn.cursor()
    if request.method == 'POST':
        amount = request.form['amount']
        try:
            amount = float(amount)
        except:
            flash('Budget must be number','danger'); return redirect(url_for('budget'))
        c.execute("INSERT INTO budgets (user_id,amount) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET amount=excluded.amount",
                  (user['id'], amount))
        conn.commit(); flash('Budget saved ✅','success')
    c.execute('SELECT amount FROM budgets WHERE user_id=?',(user['id'],))
    b = c.fetchone(); budget_amount = b['amount'] if b else None
    today = date.today().strftime('%Y-%m')
    c.execute("SELECT SUM(amount) AS mexp FROM transactions WHERE user_id=? AND type='expense' AND date LIKE ?",
              (user['id'], today+'%'))
    mexp = c.fetchone()['mexp'] or 0
    conn.close()
    return render_template('budget.html', budget=budget_amount, month_expense=mexp)

@app.route('/category-ratio')
def category_ratio():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT category,type,SUM(amount) AS total
                 FROM transactions WHERE user_id=? GROUP BY category,type""", (user['id'],))
    rows = c.fetchall(); conn.close()
    inc_rat=[]; exp_rat=[]
    tot_inc = sum(r['total'] for r in rows if r['type']=='income')
    tot_exp = sum(r['total'] for r in rows if r['type']=='expense')
    for r in rows:
        if r['type']=='income' and tot_inc>0:
            inc_rat.append((r['category'], r['total']/tot_inc*100))
        elif r['type']=='expense' and tot_exp>0:
            exp_rat.append((r['category'], r['total']/tot_exp*100))
    return render_template('category_ratio.html',
                           income_ratios=inc_rat,
                           expense_ratios=exp_rat)

@app.route('/goals', methods=['GET','POST'])
def goals():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    conn = get_db(); c = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        target = request.form['target_amount']
        deadline = request.form.get('deadline')
        try: target = float(target)
        except: flash('Target must be number','danger'); return redirect(url_for('goals'))
        c.execute('INSERT INTO goals (user_id,name,target_amount,deadline,current_amount) VALUES (?,?,?,?,0)',
                  (user['id'], name, target, deadline))
        conn.commit(); flash('Goal created ✅','success')
    c.execute('SELECT * FROM goals WHERE user_id=? ORDER BY id DESC',(user['id'],))
    gs = c.fetchall(); conn.close()
    return render_template('goals.html', goals=gs)

@app.route('/goals/deposit/<int:goal_id>', methods=['POST'])
def goal_deposit(goal_id):
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    amt = request.form['amount']
    try:
        amt = float(amt)
        if amt <= 0:
            raise ValueError()
    except:
        flash('Amount must be a positive number', 'danger')
        return redirect(url_for('goals'))

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            SUM(CASE WHEN type='income' THEN amount_thb ELSE 0 END) AS inc,
            SUM(CASE WHEN type='expense' THEN amount_thb ELSE 0 END) AS exp
        FROM transactions WHERE user_id=?
    """, (user['id'],))
    row = c.fetchone()
    balance = (row['inc'] or 0) - (row['exp'] or 0)

    if amt > balance:
        conn.close()
        flash(f'❌ Not enough balance! You only have {balance:,.2f} THB available.', 'danger')
        return redirect(url_for('goals'))


    c.execute('SELECT id, name, target_amount, current_amount FROM goals WHERE id=? AND user_id=?',
              (goal_id, user['id']))
    g = c.fetchone()
    if not g:
        conn.close()
        flash('Goal not found', 'danger')
        return redirect(url_for('goals'))

    c.execute('UPDATE goals SET current_amount = current_amount + ? WHERE id=? AND user_id=?',
              (amt, goal_id, user['id']))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("""
        INSERT INTO transactions (user_id, date, type, category, amount, description, currency, amount_thb)
        VALUES (?, ?, 'expense', ?, ?, 'Transfer to Goal', 'THB', ?)
    """, (user['id'], now_str, f"Goal: {g['name']}", amt, amt))

    conn.commit()
    conn.close()

    flash('Goal updated and money transferred ✅', 'success')
    return redirect(url_for('goals'))


if __name__ == '__main__':
    os.makedirs(os.path.join(BASE_DIR,'data'), exist_ok=True)
    init_db()
    app.run(debug=True, host='0.0.0.0')
