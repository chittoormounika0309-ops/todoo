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

# ── DB connection ──────────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    conn.autocommit = True
    return conn

def init_db():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         SERIAL PRIMARY KEY,
            name       TEXT    NOT NULL,
            username   TEXT    UNIQUE NOT NULL,
            password   TEXT    NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
            text       TEXT    NOT NULL,
            done       BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.close()
    conn.close()
    print("Database tables ready.")

# ── JWT auth decorator ─────────────────────────────────────────
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "No token provided"}), 401
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Serve frontend pages ───────────────────────────────────────
@app.route("/")
def home():
    return send_from_directory("templates", "index.html")

@app.route("/login")
def login_page():
    return send_from_directory("templates", "login.html")

@app.route("/app")
def app_page():
    return send_from_directory("templates", "todo.html")

# ── Auth routes ────────────────────────────────────────────────
@app.route("/api/signup", methods=["POST"])
def signup():
    data     = request.get_json()
    name     = (data.get("name") or "").strip()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not name or not username or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        if cur.fetchone():
            return jsonify({"error": "Username already taken"}), 409

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (name, username, password) VALUES (%s,%s,%s) RETURNING id, name, username",
            (name, username, hashed)
        )
        user  = dict(cur.fetchone())
        token = jwt.encode(
            {"id": user["id"], "username": user["username"], "name": user["name"],
             "exp": datetime.utcnow() + timedelta(days=7)},
            JWT_SECRET, algorithm="HS256"
        )
        cur.close(); conn.close()
        return jsonify({"token": token, "user": user}), 201

    except Exception as e:
        print(e)
        return jsonify({"error": "Server error"}), 500


@app.route("/api/login", methods=["POST"])
def login():
    data     = request.get_json()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "All fields are required"}), 400

    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()

        if not user:
            return jsonify({"error": "Account not found"}), 404
        if not bcrypt.checkpw(password.encode(), user["password"].encode()):
            return jsonify({"error": "Incorrect password"}), 401

        token = jwt.encode(
            {"id": user["id"], "username": user["username"], "name": user["name"],
             "exp": datetime.utcnow() + timedelta(days=7)},
            JWT_SECRET, algorithm="HS256"
        )
        cur.close(); conn.close()
        return jsonify({"token": token, "user": {"id": user["id"], "name": user["name"], "username": user["username"]}})

    except Exception as e:
        print(e)
        return jsonify({"error": "Server error"}), 500


# ── Task routes ────────────────────────────────────────────────
@app.route("/api/tasks", methods=["GET"])
@require_auth
def get_tasks():
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM tasks WHERE user_id=%s ORDER BY created_at DESC",
            (request.user["id"],)
        )
        tasks = [dict(row) for row in cur.fetchall()]
        for t in tasks:
            t["created_at"] = t["created_at"].isoformat()
        cur.close(); conn.close()
        return jsonify(tasks)
    except Exception as e:
        print(e)
        return jsonify({"error": "Server error"}), 500


@app.route("/api/tasks", methods=["POST"])
@require_auth
def add_task():
    data = request.get_json()
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Task text required"}), 400
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "INSERT INTO tasks (user_id, text) VALUES (%s,%s) RETURNING *",
            (request.user["id"], text)
        )
        task = dict(cur.fetchone())
        task["created_at"] = task["created_at"].isoformat()
        cur.close(); conn.close()
        return jsonify(task), 201
    except Exception as e:
        print(e)
        return jsonify({"error": "Server error"}), 500


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
@require_auth
def toggle_task(task_id):
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "UPDATE tasks SET done = NOT done WHERE id=%s AND user_id=%s RETURNING *",
            (task_id, request.user["id"])
        )
        task = cur.fetchone()
        if not task:
            return jsonify({"error": "Task not found"}), 404
        task = dict(task)
        task["created_at"] = task["created_at"].isoformat()
        cur.close(); conn.close()
        return jsonify(task)
    except Exception as e:
        print(e)
        return jsonify({"error": "Server error"}), 500


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@require_auth
def delete_task(task_id):
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "DELETE FROM tasks WHERE id=%s AND user_id=%s",
            (task_id, request.user["id"])
        )
        cur.close(); conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(e)
        return jsonify({"error": "Server error"}), 500


@app.route("/api/tasks/done", methods=["DELETE"])
@require_auth
def clear_done():
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "DELETE FROM tasks WHERE user_id=%s AND done=TRUE",
            (request.user["id"],)
        )
        cur.close(); conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(e)
        return jsonify({"error": "Server error"}), 500


@app.route("/api/health")
def health():
    return jsonify({"status": "Taskflow API running", "time": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)