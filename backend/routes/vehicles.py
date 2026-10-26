import re
from flask import Blueprint, request, jsonify, session
import db
from auth import login_required, is_admin, need
from errors import ApiError
from .util import norm_reg

bp = Blueprint("vehicles", __name__)

@bp.get("/vehicles")
@login_required
def list_vehicles():
    sql = "SELECT v.*, u.full_name AS owner FROM vehicles v JOIN users u ON u.user_id = v.user_id"
    if is_admin():
        return jsonify(db.rows(sql + " ORDER BY v.vehicle_id"))
    return jsonify(db.rows(sql + " WHERE v.user_id = %s ORDER BY v.vehicle_id", (session["uid"],)))

@bp.post("/vehicles")
@login_required
def add_vehicle():
    d = request.get_json(silent=True) or {}
    need(d, "reg_number", "vehicle_type")
    reg = norm_reg(d["reg_number"])
    if not re.fullmatch(r"[A-Z0-9]{4,15}", reg):
        raise ApiError("Registration number must be 4-15 letters/digits.")
    if d["vehicle_type"] not in ("CAR", "TWO_WHEELER"):
        raise ApiError("vehicle_type must be CAR or TWO_WHEELER.")
    vid, _ = db.execute(
        "INSERT INTO vehicles (user_id, reg_number, vehicle_type, is_ev, has_accessible_permit) VALUES (%s,%s,%s,%s,%s)",
        (session["uid"], reg, d["vehicle_type"], 1 if d.get("is_ev") else 0, 1 if d.get("has_accessible_permit") else 0))
    return jsonify(vehicle_id=vid, reg_number=reg), 201
