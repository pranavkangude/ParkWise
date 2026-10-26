from flask import Blueprint, request, jsonify, session
import db
from auth import login_required, is_admin, need, owns_vehicle
from .util import parse_dt, to_int
from errors import ApiError

bp = Blueprint("reservations", __name__)

@bp.post("/reservations")
@login_required
def create():
    d = request.get_json(silent=True) or {}
    need(d, "vehicle_id", "slot_id", "start", "end")
    vid, sid = to_int(d["vehicle_id"], "vehicle_id"), to_int(d["slot_id"], "slot_id")
    start, end = parse_dt(d["start"], "start"), parse_dt(d["end"], "end")
    if end <= start:
        raise ApiError("End time must be after start time.")
    v = owns_vehicle(vid)
    score = d.get("alloc_score")
    reason = (d.get("alloc_reason") or None)
    out, _ = db.call("sp_create_reservation",
                     (v["user_id"], vid, sid, start, end, score, reason[:255] if reason else None, 0))
    return jsonify(reservation_id=out[-1], message="Reservation created."), 201

@bp.get("/reservations")
@login_required
def mine():
    sql = """SELECT r.reservation_id, r.start_time, r.end_time, r.status, r.alloc_score, r.alloc_reason,
                    s.slot_code, v.reg_number, v.user_id
             FROM reservations r JOIN parking_slots s ON s.slot_id = r.slot_id
             JOIN vehicles v ON v.vehicle_id = r.vehicle_id"""
    if is_admin():
        return jsonify(db.rows(sql + " ORDER BY r.start_time DESC LIMIT 200"))
    return jsonify(db.rows(sql + " WHERE r.user_id = %s ORDER BY r.start_time DESC LIMIT 200", (session["uid"],)))

@bp.delete("/reservations/<int:rid>")
@login_required
def cancel(rid):
    r = db.one("SELECT user_id FROM reservations WHERE reservation_id = %s", (rid,))
    if not r:
        raise ApiError("Reservation not found.", 404)
    db.call("sp_cancel_reservation", (rid, r["user_id"] if is_admin() else session["uid"]))
    return jsonify(message="Reservation cancelled.")
