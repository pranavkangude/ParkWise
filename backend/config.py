"""ParkWise settings. Put your values in backend/.env (copy .env.example) or set environment variables."""
import os
_env = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env):
    for line in open(_env, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB = dict(
    host=os.getenv("PW_DB_HOST", "127.0.0.1"),
    port=int(os.getenv("PW_DB_PORT", "3306")),
    user=os.getenv("PW_DB_USER", "root"),
    password=os.getenv("PW_DB_PASSWORD", ""),
    database=os.getenv("PW_DB_NAME", "parkwise"),
)
SECRET_KEY = os.getenv("PW_SECRET_KEY", "change-me-for-real-use")

# Failed-login limit (Member 3, task 3): this many wrong passwords per e-mail within this many minutes.
LOGIN_MAX_FAILS = int(os.getenv("PW_LOGIN_MAX_FAILS", "5"))
LOGIN_WINDOW_MIN = int(os.getenv("PW_LOGIN_WINDOW_MIN", "15"))
# Largest request body the API accepts (bytes).
MAX_BODY_BYTES = int(os.getenv("PW_MAX_BODY_BYTES", "65536"))
