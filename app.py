import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
JWT_SECRET   = os.environ.get("JWT_SECRET", "taskflow_secret_change_this")

def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    conn.autocommit = True
    return conn

def init_db():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           SERIAL PRIMARY KEY,
            name         TEXT NOT NULL,
            username     TEXT UNIQUE NOT NULL,
            password     TEXT NOT NULL,
            bio          TEXT DEFAULT '',
            avatar_color TEXT DEFAULT '#2C3E50',
            created_at   TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
            text       TEXT NOT NULL,
            done       BOOLEAN DEFAULT FALSE,
            due_date   DATE DEFAULT NULL,
            remind_at  TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT DEFAULT '';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_color TEXT DEFAULT '#2C3E50';
        ALTER TABLE tasks ADD COLUMN IF NOT EXISTS due_date DATE DEFAULT NULL;
        ALTER TABLE tasks ADD COLUMN IF NOT EXISTS remind_at TIMESTAMP DEFAULT NULL;
    """)
    cur.close(); conn.close()
    print("Database tables ready.")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "No token provided"}), 401
        try:
            request.user = jwt.decode(header.split(" ")[1], JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

def serialize_task(row):
    t = dict(row)
    if t.get("created_at"): t["created_at"] = t["created_at"].isoformat()
    t["due_date"]  = t["due_date"].isoformat()  if t.get("due_date")  else None
    t["remind_at"] = t["remind_at"].isoformat() if t.get("remind_at") else None
    return t

# ── Pages ──────────────────────────────────────────────────────
@app.route("/")
def home():       return send_from_directory("templates", "index.html")
@app.route("/login")
def login_page(): return send_from_directory("templates", "login.html")
@app.route("/app")
def app_page():   return send_from_directory("templates", "todo.html")
@app.route("/profile")
def profile_page():return send_from_directory("templates", "profile.html")

# ── Auth ───────────────────────────────────────────────────────
@app.route("/api/signup", methods=["POST"])
def signup():
    d = request.get_json()
    name, username, password = (d.get("name","")).strip(), (d.get("username","")).strip(), (d.get("password","")).strip()
    if not name or not username or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        if cur.fetchone(): return jsonify({"error": "Username already taken"}), 409
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        palette = ["#2C3E50","#8E44AD","#2980B9","#16A085","#D35400","#C0392B","#1A252F","#6C3483"]
        color   = palette[ord(username[0].lower()) % len(palette)]
        cur.execute("INSERT INTO users (name,username,password,avatar_color) VALUES (%s,%s,%s,%s) RETURNING id,name,username,bio,avatar_color",
                    (name, username, hashed, color))
        user = dict(cur.fetchone())
        token = jwt.encode({"id":user["id"],"username":user["username"],"name":user["name"],
                            "exp": datetime.utcnow()+timedelta(days=7)}, JWT_SECRET, algorithm="HS256")
        cur.close(); conn.close()
        return jsonify({"token": token, "user": user}), 201
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json()
    username, password = (d.get("username","")).strip(), (d.get("password","")).strip()
    if not username or not password: return jsonify({"error": "All fields are required"}), 400
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        if not user: return jsonify({"error": "Account not found"}), 404
        if not bcrypt.checkpw(password.encode(), user["password"].encode()):
            return jsonify({"error": "Incorrect password"}), 401
        token = jwt.encode({"id":user["id"],"username":user["username"],"name":user["name"],
                            "exp": datetime.utcnow()+timedelta(days=7)}, JWT_SECRET, algorithm="HS256")
        cur.close(); conn.close()
        return jsonify({"token": token, "user": {
            "id": user["id"], "name": user["name"], "username": user["username"],
            "bio": user["bio"], "avatar_color": user["avatar_color"]
        }})
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

# ── Profile ────────────────────────────────────────────────────
@app.route("/api/profile", methods=["GET"])
@require_auth
def get_profile():
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id,name,username,bio,avatar_color,created_at FROM users WHERE id=%s", (request.user["id"],))
        user = dict(cur.fetchone())
        user["created_at"] = user["created_at"].isoformat()
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE user_id=%s", (request.user["id"],))
        user["total_tasks"] = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE user_id=%s AND done=TRUE", (request.user["id"],))
        user["done_tasks"] = cur.fetchone()["c"]
        cur.close(); conn.close()
        return jsonify(user)
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/profile", methods=["PATCH"])
@require_auth
def update_profile():
    d = request.get_json()
    name  = (d.get("name","")).strip()
    bio   = (d.get("bio","")).strip()
    color = (d.get("avatar_color","")).strip()
    if not name: return jsonify({"error": "Name is required"}), 400
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("UPDATE users SET name=%s,bio=%s,avatar_color=%s WHERE id=%s RETURNING id,name,username,bio,avatar_color",
                    (name, bio, color, request.user["id"]))
        user = dict(cur.fetchone())
        cur.close(); conn.close()
        return jsonify(user)
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/profile/password", methods=["PATCH"])
@require_auth
def change_password():
    d = request.get_json()
    cur_pass = (d.get("current_password","")).strip()
    new_pass = (d.get("new_password","")).strip()
    if not cur_pass or not new_pass: return jsonify({"error": "Both fields required"}), 400
    if len(new_pass) < 6: return jsonify({"error": "New password must be at least 6 characters"}), 400
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT password FROM users WHERE id=%s", (request.user["id"],))
        user = cur.fetchone()
        if not bcrypt.checkpw(cur_pass.encode(), user["password"].encode()):
            return jsonify({"error": "Current password is incorrect"}), 401
        hashed = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
        cur.execute("UPDATE users SET password=%s WHERE id=%s", (hashed, request.user["id"]))
        cur.close(); conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

# ── Tasks ──────────────────────────────────────────────────────
@app.route("/api/tasks", methods=["GET"])
@require_auth
def get_tasks():
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM tasks WHERE user_id=%s ORDER BY created_at DESC", (request.user["id"],))
        tasks = [serialize_task(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify(tasks)
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/tasks", methods=["POST"])
@require_auth
def add_task():
    d = request.get_json()
    text = (d.get("text","")).strip()
    if not text: return jsonify({"error": "Task text required"}), 400
    due_date  = d.get("due_date") or None
    remind_at = d.get("remind_at") or None
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("INSERT INTO tasks (user_id,text,due_date,remind_at) VALUES (%s,%s,%s,%s) RETURNING *",
                    (request.user["id"], text, due_date, remind_at))
        task = serialize_task(cur.fetchone())
        cur.close(); conn.close()
        return jsonify(task), 201
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
@require_auth
def update_task(task_id):
    d = request.get_json()
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if "done" in d:
            cur.execute("UPDATE tasks SET done=NOT done WHERE id=%s AND user_id=%s RETURNING *",
                        (task_id, request.user["id"]))
        else:
            cur.execute("UPDATE tasks SET text=%s,due_date=%s,remind_at=%s WHERE id=%s AND user_id=%s RETURNING *",
                        (d.get("text"), d.get("due_date") or None, d.get("remind_at") or None,
                         task_id, request.user["id"]))
        row = cur.fetchone()
        if not row: return jsonify({"error": "Task not found"}), 404
        task = serialize_task(row)
        cur.close(); conn.close()
        return jsonify(task)
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@require_auth
def delete_task(task_id):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE id=%s AND user_id=%s", (task_id, request.user["id"]))
        cur.close(); conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/tasks/done", methods=["DELETE"])
@require_auth
def clear_done():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE user_id=%s AND done=TRUE", (request.user["id"],))
        cur.close(); conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/reminders", methods=["GET"])
@require_auth
def get_reminders():
    try:
        conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT * FROM tasks WHERE user_id=%s AND done=FALSE AND (
                (remind_at IS NOT NULL AND remind_at <= NOW()+INTERVAL '24 hours' AND remind_at >= NOW())
                OR (due_date IS NOT NULL AND due_date <= CURRENT_DATE+1 AND due_date >= CURRENT_DATE)
            ) ORDER BY due_date ASC NULLS LAST
        """, (request.user["id"],))
        tasks = [serialize_task(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify(tasks)
    except Exception as e:
        print(e); return jsonify({"error": "Server error"}), 500

@app.route("/api/health")
def health():
    return jsonify({"status": "Taskflow API running", "time": datetime.utcnow().isoformat()})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)