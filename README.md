# Shell Car Wash - Backend API Service

Django REST Framework backend for the **Shell Car Wash Management & Worker Commission System**.

Engineered for deployment on **Render** (with PostgreSQL support, Gunicorn WSGI, Whitenoise static asset hosting, and token-based JWT authentication), and fully decoupled to power the frontend hosted on **Vercel**.

---

## 🚀 One-Click Deployment to Render

### Option 1: Render Blueprint (Recommended)
1. Go to your [Render Dashboard](https://dashboard.render.com/) -> **Blueprints** -> **New Blueprint Instance**.
2. Connect your GitHub repository: `stevedev-ops/carwash_backend`.
3. Render automatically reads `render.yaml`, provisions a free **PostgreSQL Database**, configures the Python web service, runs `./build.sh` (collectstatic, migrations, seed data), and launches Gunicorn!

---

### Option 2: Manual Web Service Setup on Render
1. Click **New +** -> **Web Service**.
2. Connect repository: `stevedev-ops/carwash_backend`.
3. Configure the service:
   - **Environment**: `Python 3`
   - **Branch**: `main`
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn carwash_backend.wsgi:application`
4. **Environment Variables**:
   | Variable | Value | Description |
   | :--- | :--- | :--- |
   | `PYTHON_VERSION` | `3.12.0` | Python runtime version |
   | `SECRET_KEY` | *(Generate a secure string)* | Django secret key |
   | `DEBUG` | `False` | Production security setting |
   | `ALLOWED_HOSTS` | `*` | Or your custom Render domain |
   | `CORS_ALLOW_ALL_ORIGINS` | `True` | Allows Vercel frontend requests |
   | `DATABASE_URL` | *(Optional PostgreSQL URI)* | Render Postgres internal connection string |

---

## 🛠️ Local Development

### 1. Setup Virtual Environment & Install Dependencies
```bash
python -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows:
.\venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Run Database Migrations & Seed Demo Data
```bash
python manage.py migrate
python manage.py seed_data
```

### 3. Run Development Server
```bash
python manage.py runserver
```
Backend API will be live at: `http://127.0.0.1:8000/api/`

---

## 🔑 Pre-Seeded Demo Credentials

| Role | Username | Password | Access |
| :--- | :--- | :--- | :--- |
| **Admin / Manager** | `admin` | `admin123` | Full dashboard, payouts, reports, configuration |
| **Cashier** | `cashier` | `cashier123` | Counter billing, approvals & payment collection |
| **Worker (Senior)** | `john` | `worker123` | Bay submission, personal earnings & cashout |
| **Worker** | `peter` | `worker123` | Bay submission, personal earnings & cashout |
| **Worker** | `james` | `worker123` | Bay submission, personal earnings & cashout |
| **Worker** | `mary` | `worker123` | Bay submission, personal earnings & cashout |

---

## 🔌 API Endpoints Reference

- **Auth**: `POST /api/auth/login/`, `GET /api/auth/me/`
- **Dashboard**: `GET /api/reports/summary/`
- **Washes**: `GET, POST /api/washes/`, `GET /api/washes/pending/`, `POST /api/washes/{id}/approve/`
- **Workers**: `GET, POST /api/workers/`, `GET /api/workers/{id}/`
- **Payouts**: `GET, POST /api/worker-payments/`
- **Services**: `GET, POST /api/services/`
- **Expenses**: `GET, POST /api/expenses/`
- **Attendance**: `GET, POST /api/attendance/`
- **Daily Closings**: `GET, POST /api/daily-closings/`
- **Exports**: `GET /api/reports/export/excel/`, `GET /api/reports/export/pdf/`, `GET /api/reports/export/csv/{entity}/`

