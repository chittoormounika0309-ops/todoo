# Taskflow — Full Stack To-Do App

A luxury-grade productivity app built with:
- **Frontend** — Pure HTML, CSS, JavaScript
- **Backend** — Python (Flask)
- **Database** — PostgreSQL (Railway)
- **Deployment** — Render (free tier)

---

## Project Structure

```
taskflow/
├── app.py               ← Flask backend (all API routes)
├── requirements.txt     ← Python dependencies
├── Procfile             ← For Render deployment
├── render.yaml          ← Render config
├── .env.example         ← Environment variable template
└── templates/
    ├── index.html       ← Home / landing page
    ├── login.html       ← Login & signup
    └── todo.html        ← Main to-do app
```

---

## Local Development Setup

### 1. Clone your repo
```bash
git clone https://github.com/yourusername/taskflow.git
cd taskflow
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up environment variables
```bash
cp .env.example .env
# Edit .env and fill in your DATABASE_URL and JWT_SECRET
```

### 5. Run the app
```bash
python app.py
```
Open http://localhost:5000

---

## Setting Up Railway PostgreSQL Database

1. Go to https://railway.app and sign in with GitHub
2. Click **New Project → Provision PostgreSQL**
3. Wait ~30 seconds for it to spin up
4. Click the PostgreSQL service → **Connect** tab
5. Copy the `DATABASE_URL` — looks like:
   ```
   postgresql://postgres:abc123@roundhouse.proxy.rlwy.net:12345/railway
   ```
6. Paste it in your `.env` file as `DATABASE_URL`

The app auto-creates the `users` and `tasks` tables on first run.

---

## Deploying to Render

1. Push your code to GitHub:
```bash
git add .
git commit -m "Initial commit"
git push origin main
```

2. Go to https://render.com → sign in with GitHub

3. Click **New → Web Service**

4. Connect your GitHub repository

5. Render auto-detects Python. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`

6. Add Environment Variables:
   - `DATABASE_URL` → paste from Railway
   - `JWT_SECRET` → any long random string (min 32 chars)

7. Click **Deploy** — your app will be live at:
   `https://taskflow.onrender.com`

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | /api/signup | No | Create account |
| POST | /api/login | No | Sign in |
| GET | /api/tasks | Yes | Get all tasks |
| POST | /api/tasks | Yes | Add a task |
| PATCH | /api/tasks/:id | Yes | Toggle done/pending |
| DELETE | /api/tasks/:id | Yes | Delete a task |
| DELETE | /api/tasks/done | Yes | Clear completed |
| GET | /api/health | No | Health check |

---

## Security

- Passwords hashed with **bcrypt** (never stored as plain text)
- Authentication via **JWT tokens** (expire after 7 days)
- All task routes require a valid token
- Database uses parameterized queries (no SQL injection)