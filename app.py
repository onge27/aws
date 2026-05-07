import os
import re
import json
import secrets as pysecrets
import sqlite3
from functools import wraps
from datetime import datetime

import bcrypt
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# ─── Gemini AI ───────────────────────────────────────────────────────────────
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
import google.generativeai as genai

_gemini_key = os.getenv('GEMINI_API_KEY')
if _gemini_key:
    genai.configure(api_key=_gemini_key)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    gemini_model = None

# ─── Database ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('NEON_DATABASE_URL')

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    USE_POSTGRES = True
else:
    USE_POSTGRES = False


def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect('examination.db')
        conn.row_factory = sqlite3.Row
        return conn


def db_cursor(conn):
    if USE_POSTGRES:
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()


def db_execute(conn, sql, params=()):
    if USE_POSTGRES:
        sql = sql.replace('?', '%s')
    cur = db_cursor(conn)
    cur.execute(sql, params)
    return cur


def db_lastid(cur):
    if USE_POSTGRES:
        row = cur.fetchone()
        return row['id'] if row else None
    return cur.lastrowid


# ─── App ──────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'wmsu-oes-secure-key-2026')

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx'}
app.config['CLERK_PUBLISHABLE_KEY'] = os.getenv('CLERK_PUBLISHABLE_KEY', '')
app.config['CLERK_SECRET_KEY'] = os.getenv('CLERK_SECRET_KEY', '')
app.config['YEAR'] = 2026

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ─── DB Init ─────────────────────────────────────────────────────────────────
def init_db():
    conn = get_db()
    cur = db_cursor(conn)

    # (UNCHANGED — your full schema remains here)
    # ... keep your existing tables exactly as you wrote them ...

    conn.commit()
    conn.close()


init_db()


# ─── Helpers ─────────────────────────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to continue.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') != role:
                flash('You do not have permission to access that page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def check_password(stored, provided):
    if isinstance(stored, str):
        stored = stored.encode()
    return bcrypt.checkpw(provided.encode(), stored)


# ─────────────────────────────────────────────────────────────
# FIXED ROUTE (UPLOAD STUDENTS) — MAIN BUG WAS HERE
# ─────────────────────────────────────────────────────────────
@app.route('/teacher/upload_students', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def upload_students():
    conn = get_db()
    subjects = db_execute(conn, "SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    conn.close()

    if request.method == 'POST':
        subject_id = request.form['subject_id']

        if 'file' not in request.files:
            flash('No file uploaded.', 'danger')
            return redirect(url_for('upload_students'))

        file = request.files['file']

        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('upload_students'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath)
                else:
                    df = pd.read_excel(filepath)

                if 'student_name' not in df.columns:
                    flash('File must have column: student_name', 'danger')
                    return redirect(url_for('upload_students'))

                conn = get_db()
                count = 0

                for _, row in df.iterrows():
                    sname = str(row['student_name']).strip()
                    if not sname:
                        continue

                    if USE_POSTGRES:
                        db_execute(conn,
                            "INSERT INTO allowed_students (student_name, subject_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (sname, subject_id))
                    else:
                        db_execute(conn,
                            "INSERT OR IGNORE INTO allowed_students (student_name, subject_id) VALUES (?, ?)",
                            (sname, subject_id))

                    count += 1

                conn.commit()
                conn.close()

                flash(f'Successfully imported {count} students.', 'success')
                return redirect(url_for('view_allowed_students', subject_id=subject_id))

            except Exception as e:
                flash(f'Error reading file: {str(e)}', 'danger')

            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

        else:
            flash('Invalid file type.', 'danger')

        return redirect(url_for('upload_students'))

    return render_template('upload_students.html', subjects=subjects)


# ─── ALL YOUR OTHER ROUTES (UNCHANGED) ─────────────────────
# (keep everything you already wrote here exactly as-is)


# ─── FIXED APP RUN (IMPORTANT FOR RENDER/GUNICORN) ───────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

