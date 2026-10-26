import re
from functools import wraps
from flask import Blueprint, request, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import db
from errors import ApiError

bp = Blueprint("auth", __name__)

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
    return w

def is_admin():
    return session.get("role") == "ADMIN"

def need(data, *fields):
    for f in fields:
        if data.get(f) in (None, ""):
            raise ApiError(f"'{f}' is required.")

@bp.post("/auth/register")
def register():
    d = request.get_json(silent=True) or {}
    need(d, "full_name", "email", "password")
    email = d["email"].strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ApiError("Enter a valid email address.")
    if len(d["password"]) < 6:
        raise ApiError("Password must be at least 6 characters.")
    phone = (d.get("phone") or "").strip() or None
    if phone and not re.fullmatch(r"\d{10,15}", phone):
        raise ApiError("Phone must be 10 to 15 digits.")
    if db.one("SELECT 1 AS x FROM users WHERE email = %s", (email,)):
        raise ApiError("This email is already registered.", 409)
    uid, _ = db.execute(
        "INSERT INTO users (full_name, email, phone, password_hash, role) VALUES (%s,%s,%s,%s,'USER')",
        (d["full_name"].strip(), email, phone, generate_password_hash(d["password"])))
    return jsonify(user_id=uid, message="Registered. You can log in now."), 201

@bp.post("/auth/login")
def login():
    d = request.get_json(silent=True) or {}
    need(d, "email", "password")
    u = db.one("SELECT user_id, full_name, email, role, password_hash FROM users WHERE email = %s",
               (d["email"].strip().lower(),))
    if not u or not check_password_hash(u["password_hash"], d["password"]):
        raise ApiError("Wrong email or password.", 401)
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
