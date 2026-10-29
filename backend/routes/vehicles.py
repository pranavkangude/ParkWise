import re
from flask import Blueprint, jsonify, session
import db
from auth import login_required, is_admin, need, owns_vehicle
from errors import ApiError
from validate import json_body, flag
from .util import norm_reg

bp = Blueprint("vehicles", __name__)
TYPES = ("CAR", "TWO_WHEELER")


def _reg(value):
    reg = norm_reg(value)
    if not re.fullmatch(r"[A-Z0-9]{4,15}", reg):
        raise ApiError("Registration number must be 4-15 letters/digits.")
    return reg


def _type(value):
    if value not in TYPES:
        raise ApiError("vehicle_type must be CAR or TWO_WHEELER.")
    return value


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
    d = json_body()
    need(d, "reg_number", "vehicle_type")
    reg, vtype = _reg(d["reg_number"]), _type(d["vehicle_type"])
    ev, permit = flag(d.get("is_ev"), "is_ev"), flag(d.get("has_accessible_permit"), "has_accessible_permit")
    if db.one("SELECT 1 AS x FROM vehicles WHERE reg_number = %s", (reg,)):
        raise ApiError("This registration number is already registered.", 409)
    vid, _ = db.execute(
        "INSERT INTO vehicles (user_id, reg_number, vehicle_type, is_ev, has_accessible_permit) VALUES (%s,%s,%s,%s,%s)",
        (session["uid"], reg, vtype, ev, permit))
    return jsonify(vehicle_id=vid, reg_number=reg), 201


@bp.put("/vehicles/<int:vid>")
@login_required
def edit_vehicle(vid):
    """Change plate, type, EV flag or permit. Send only the fields you want to change."""
    v = owns_vehicle(vid)                                   # 404 unknown, 403 someone else's
    d = json_body()
    fields = ("reg_number", "vehicle_type", "is_ev", "has_accessible_permit")
    if not any(k in d for k in fields):
        raise ApiError("Send at least one of: " + ", ".join(fields) + ".")
    new = {k: v[k] for k in fields}
    if "reg_number" in d:
        new["reg_number"] = _reg(d["reg_number"])
    if "vehicle_type" in d:
        new["vehicle_type"] = _type(d["vehicle_type"])
    if "is_ev" in d:
        new["is_ev"] = flag(d["is_ev"], "is_ev")
    if "has_accessible_permit" in d:
        new["has_accessible_permit"] = flag(d["has_accessible_permit"], "has_accessible_permit")
    if all(new[k] == v[k] for k in fields):
        return jsonify(message="No change.", changed=False)
    if new["reg_number"] != v["reg_number"] and db.one(
            "SELECT 1 AS x FROM vehicles WHERE reg_number = %s", (new["reg_number"],)):
        raise ApiError("This registration number is already registered.", 409)

    params = (new["reg_number"], new["vehicle_type"], new["is_ev"], new["has_accessible_permit"], vid)
    if any(new[k] != v[k] for k in ("vehicle_type", "is_ev", "has_accessible_permit")):
        # Type, EV flag and permit decide which slots the vehicle may use, so they cannot change while it
        # is parked or has an open reservation. The guard sits inside the UPDATE itself (no gap for a race).
        _, n = db.execute(
            """UPDATE vehicles SET reg_number=%s, vehicle_type=%s, is_ev=%s, has_accessible_permit=%s
               WHERE vehicle_id=%s
                 AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.vehicle_id = vehicles.vehicle_id AND s.status = 'ACTIVE')
                 AND NOT EXISTS (SELECT 1 FROM reservations r WHERE r.vehicle_id = vehicles.vehicle_id
                                 AND r.status IN ('PENDING','ACTIVE'))""", params)
        if n == 0:
            raise ApiError("Type, EV and permit cannot change while the vehicle is parked or has an open "
                           "reservation. Exit or cancel first.", 409)
    else:
        db.execute("UPDATE vehicles SET reg_number=%s, vehicle_type=%s, is_ev=%s, has_accessible_permit=%s "
                   "WHERE vehicle_id=%s", params)
    return jsonify(message="Vehicle updated.", changed=True)


@bp.delete("/vehicles/<int:vid>")
@login_required
def delete_vehicle(vid):
    """Only a vehicle with no history can be deleted. History (bills, fines) must stay in the database."""
    v = owns_vehicle(vid)
    c = db.one("""SELECT (SELECT COUNT(*) FROM reservations WHERE vehicle_id = %s) AS reservations,
                         (SELECT COUNT(*) FROM parking_sessions WHERE vehicle_id = %s) AS sessions,
                         (SELECT COUNT(*) FROM violations WHERE vehicle_id = %s) AS violations""", (vid, vid, vid))
    used = [f"{n} {name}" for name, n in c.items() if n]
    if used:
        raise ApiError(f"Cannot delete {v['reg_number']}: it has " + ", ".join(used) +
                       ". Vehicles with history are kept for billing and audit.", 409)
    db.execute("DELETE FROM vehicles WHERE vehicle_id = %s", (vid,))     # a late FK error (1451) also maps to 409
    return jsonify(message=f"Vehicle {v['reg_number']} deleted.")
