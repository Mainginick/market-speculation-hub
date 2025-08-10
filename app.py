
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField
from wtforms.validators import InputRequired, Length, EqualTo
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf

# ----------------------
# Config
# ----------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)

# Prefer DATABASE_URL if provided (e.g., Render Postgres)
db_url = os.environ.get("DATABASE_URL")
if db_url:
    # Render gives a postgres URL without the "postgresql+" dialect sometimes; SQLAlchemy expects postgresql
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # Fallback to SQLite (works with a Render Disk)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'app.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Allowed image types
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# ----------------------
# Extensions
# ----------------------
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ----------------------
# Models
# ----------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(200), nullable=False)
    caption = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('posts', lazy=True))

# ----------------------
# Forms
# ----------------------
class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=4)])
    confirm = PasswordField('Confirm password', validators=[InputRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired()])
    password = PasswordField('Password', validators=[InputRequired()])
    submit = SubmitField('Login')

class PostForm(FlaskForm):
    caption = TextAreaField('Caption', validators=[Length(max=500)])
    submit = SubmitField('Post')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------
# DB init
# ----------------------
with app.app_context():
    db.create_all()

# ----------------------
# Market data
# ----------------------
market_data_cache = {}

def fetch_market_data():
    tickers = ['^DJI', '^GSPC', '^IXIC', 'AAPL', 'MSFT']
    data = {}
    try:
        yf_tickers = yf.Tickers(' '.join(tickers))
        for t in tickers:
            tk = yf_tickers.tickers.get(t) or yf.Ticker(t)
            info = tk.history(period='1d')
            last_price = None
            change = None
            if not info.empty:
                last_price = float(info['Close'][-1])
                open_price = float(info['Open'][-1])
                change = last_price - open_price
            else:
                q = getattr(tk, 'fast_info', {}) or {}
                last_price = q.get('last_price')
            data[t] = {'last': last_price, 'change': change}
    except Exception as e:
        print("Market fetch error:", e)
        return
    global market_data_cache
    market_data_cache = data

# Start the scheduler only if explicitly enabled (to avoid multiple schedulers under Gunicorn)
if os.environ.get("ENABLE_SCHEDULER", "0") == "1":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=fetch_market_data, trigger="interval", minutes=5, max_instances=1, coalesce=True)
    scheduler.start()
    # Initial fetch
    fetch_market_data()

# ----------------------
# Routes
# ----------------------
@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route('/')
def index():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    form = PostForm()
    return render_template('index.html', posts=posts, form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already taken', 'danger')
            return redirect(url_for('register'))
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Account created. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Logged in successfully', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'image' not in request.files:
        flash('No image part', 'danger')
        return redirect(url_for('index'))
    file = request.files['image']
    caption = request.form.get('caption', '')
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('index'))
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        post = Post(image_filename=filename, caption=caption, user_id=current_user.id)
        db.session.add(post)
        db.session.commit()
        flash('Posted!', 'success')
    else:
        flash('Invalid file type', 'danger')
    return redirect(url_for('index'))

@app.route('/user/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    return render_template('profile.html', user=user, posts=posts)

@app.route('/market')
def market():
    # If scheduler disabled, fetch on-demand once per request
    if os.environ.get("ENABLE_SCHEDULER", "0") != "1":
        fetch_market_data()
    return jsonify(market_data_cache)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    # For local testing only. In Render, Gunicorn runs the app.
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
