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
