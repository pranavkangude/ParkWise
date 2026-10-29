import re
from functools import wraps
from flask import Blueprint, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import config, db
from errors import ApiError
from ratelimit import FailureLimiter
from validate import json_body, text, opt_text, secret

bp = Blueprint("auth", __name__)

# One limiter for the whole app (Decision D-19): wrong passwords per e-mail address.
login_limiter = FailureLimiter(config.LOGIN_MAX_FAILS, config.LOGIN_WINDOW_MIN * 60)

def current_user():
    uid = session.get("uid")
    return {"user_id": uid, "role": session.get("role")} if uid else None

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("uid"):
            raise ApiError("Please log in.", 401)
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("uid"):
            raise ApiError("Please log in.", 401)
        if session.get("role") != "ADMIN":
            raise ApiError("Admin only.", 403)
        return f(*a, **k)
    w.admin_guard = True          # app.py refuses to start if an /api/admin or /api/analytics route lacks this
    return w

def is_admin():
    return session.get("role") == "ADMIN"

def need(data, *fields):
    for f in fields:
        if data.get(f) in (None, ""):
            raise ApiError(f"'{f}' is required.")

@bp.post("/auth/register")
def register():
    d = json_body()
    need(d, "full_name", "email", "password")
    name = text(d["full_name"], "full_name", 100)
    email = text(d["email"], "email", 120).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ApiError("Enter a valid email address.")
    password = secret(d["password"], "password", 6, 128)
    phone = opt_text(d.get("phone"), "phone", 15)
    if phone and not re.fullmatch(r"[0-9]{10,15}", phone):
        raise ApiError("Phone must be 10 to 15 digits.")
    if db.one("SELECT 1 AS x FROM users WHERE email = %s", (email,)):
        raise ApiError("This email is already registered.", 409)
    uid, _ = db.execute(
        "INSERT INTO users (full_name, email, phone, password_hash, role) VALUES (%s,%s,%s,%s,'USER')",
        (name, email, phone, generate_password_hash(password)))
    return jsonify(user_id=uid, message="Registered. You can log in now."), 201

@bp.post("/auth/login")
def login():
    d = json_body()
    need(d, "email", "password")
    email = text(d["email"], "email", 120).lower()
    password = secret(d["password"], "password", 0, 128)
    wait = login_limiter.retry_after(email)
    if wait:
        minutes = (wait + 59) // 60
        raise ApiError(f"Too many failed logins. Try again in {minutes} minute(s).", 429,
                       {"Retry-After": str(wait)})
    u = db.one("SELECT user_id, full_name, email, role, password_hash FROM users WHERE email = %s", (email,))
    if not u or not check_password_hash(u["password_hash"], password):
        login_limiter.record(email)               # unknown e-mails count too, so the answer never reveals who exists
        raise ApiError("Wrong email or password.", 401)
    login_limiter.clear(email)
    session.clear()
    session["uid"], session["role"] = u["user_id"], u["role"]
    u.pop("password_hash")
    return jsonify(u)

@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify(message="Logged out.")

@bp.get("/me")
def me():
    if not session.get("uid"):
        raise ApiError("Not logged in.", 401)
    return jsonify(db.one("SELECT user_id, full_name, email, phone, role FROM users WHERE user_id = %s",
                          (session["uid"],)))

def owns_vehicle(vehicle_id):
    """Regular users may only use their own vehicles. Returns the vehicle row."""
    v = db.one("SELECT * FROM vehicles WHERE vehicle_id = %s", (vehicle_id,))
    if not v:
        raise ApiError("Vehicle not found.", 404)
    if not is_admin() and v["user_id"] != session["uid"]:
        raise ApiError("This is not your vehicle.", 403)
    return v

def owns_session(session_id):
    s = db.one("""SELECT ps.session_id, v.user_id FROM parking_sessions ps
                  JOIN vehicles v ON v.vehicle_id = ps.vehicle_id WHERE ps.session_id = %s""", (session_id,))
    if not s:
        raise ApiError("Session not found.", 404)
    if not is_admin() and s["user_id"] != session["uid"]:
        raise ApiError("This is not your session.", 403)
    return s
