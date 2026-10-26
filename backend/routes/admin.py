from flask import Blueprint, request, jsonify, session
import db
from auth import admin_required, need
from errors import ApiError
from .util import to_int

bp = Blueprint("admin", __name__)

def audited(fn):
    """Run fn() with @app_user_id set, then always reset it."""
    db.as_admin(session["uid"])
    try:
        return fn()
    finally:
        db.clear_admin()

@bp.get("/admin/tariffs")
@admin_required
def tariffs():
    return jsonify(db.rows("SELECT * FROM tariff_rules ORDER BY vehicle_type, is_premium"))

@bp.put("/admin/tariffs")
@admin_required
def update_tariff():
    d = request.get_json(silent=True) or {}
    need(d, "tariff_id", "hourly_rate", "grace_minutes", "min_charge", "overstay_fine_per_hour")
    cap = d.get("daily_cap")
    cap = None if cap in (None, "") else cap
    def go():
        return db.execute("""UPDATE tariff_rules SET hourly_rate=%s, grace_minutes=%s, min_charge=%s,
                             daily_cap=%s, overstay_fine_per_hour=%s WHERE tariff_id=%s""",
                          (d["hourly_rate"], d["grace_minutes"], d["min_charge"], cap,
                           d["overstay_fine_per_hour"], to_int(d["tariff_id"], "tariff_id")))
    _, n = audited(go)
    if n == 0:
        raise ApiError("Tariff not found, or nothing changed.", 404)
    return jsonify(message="Tariff updated.")

@bp.put("/admin/slots/<int:sid>/status")
@admin_required
def slot_status(sid):
    d = request.get_json(silent=True) or {}
    if d.get("status") not in ("AVAILABLE", "MAINTENANCE"):
        raise ApiError("status must be AVAILABLE or MAINTENANCE.")
    if not db.one("SELECT 1 AS x FROM parking_slots WHERE slot_id = %s", (sid,)):
        raise ApiError("Slot not found.", 404)
    audited(lambda: db.execute("UPDATE parking_slots SET status=%s WHERE slot_id=%s", (d["status"], sid)))
    return jsonify(message=f"Slot set to {d['status']}.")

@bp.get("/admin/violations")
@admin_required
def violations():
    return jsonify(db.rows("""SELECT x.*, v.reg_number FROM violations x
                              JOIN vehicles v ON v.vehicle_id = x.vehicle_id
                              ORDER BY x.detected_at DESC LIMIT 200"""))

@bp.post("/admin/violations")
@admin_required
def add_violation():
    d = request.get_json(silent=True) or {}
    need(d, "session_id", "violation_type")
    if d["violation_type"] not in ("OVERSTAY", "WRONG_SLOT", "UNAUTHORIZED_BAY"):
        raise ApiError("Type must be OVERSTAY, WRONG_SLOT or UNAUTHORIZED_BAY.")
    fine = d.get("fine_amount") or 0
    db.call("sp_log_violation", (to_int(d["session_id"], "session_id"), d["violation_type"], fine,
                                 (d.get("notes") or None)))
    return jsonify(message="Violation recorded."), 201

@bp.get("/admin/audit")
@admin_required
def audit():
    return jsonify(db.rows("""SELECT a.log_id, a.created_at, a.action, a.entity, a.entity_id,
                                     a.old_value, a.new_value, u.full_name AS actor
                              FROM audit_logs a LEFT JOIN users u ON u.user_id = a.actor_user_id
                              ORDER BY a.log_id DESC LIMIT 100"""))

@bp.post("/admin/run-jobs")
@admin_required
def run_jobs():
    """Demo fallback when the event scheduler is off: run the three scheduled jobs by hand."""
    db.call("sp_release_no_shows")
    db.call("sp_flag_overstays")
    db.call("sp_take_snapshot", (None,))
    return jsonify(message="No-show, overstay and snapshot jobs executed.")
