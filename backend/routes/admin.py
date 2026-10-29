from flask import Blueprint, jsonify, session
import db
from auth import admin_required, need
from errors import ApiError
from validate import json_body, number, integer, opt_text
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
    d = json_body()
    need(d, "tariff_id", "hourly_rate", "grace_minutes", "min_charge", "overstay_fine_per_hour")
    tid = to_int(d["tariff_id"], "tariff_id")
    rate = number(d["hourly_rate"], "hourly_rate", "0.01", 9999)
    grace = integer(d["grace_minutes"], "grace_minutes", 0, 1440)
    min_charge = number(d["min_charge"], "min_charge", 0, 9999)
    fine = number(d["overstay_fine_per_hour"], "overstay_fine_per_hour", 0, 9999)
    cap = None if d.get("daily_cap") in (None, "") else number(d["daily_cap"], "daily_cap", 0, 99999)
    if cap is not None and cap < min_charge:
        raise ApiError("daily_cap must not be lower than min_charge.")

    old = db.one("SELECT * FROM tariff_rules WHERE tariff_id = %s", (tid,))
    if not old:
        raise ApiError("Tariff not found.", 404)
    same = (old["hourly_rate"] == rate and old["grace_minutes"] == grace and old["min_charge"] == min_charge
            and old["daily_cap"] == cap and old["overstay_fine_per_hour"] == fine)
    if same:                       # MySQL reports 0 changed rows for identical values; that is not an error
        return jsonify(message="No change: these values are already saved.", changed=False)
    audited(lambda: db.execute("""UPDATE tariff_rules SET hourly_rate=%s, grace_minutes=%s, min_charge=%s,
                                  daily_cap=%s, overstay_fine_per_hour=%s WHERE tariff_id=%s""",
                               (rate, grace, min_charge, cap, fine, tid)))
    return jsonify(message="Tariff updated.", changed=True)

@bp.put("/admin/slots/<int:sid>/status")
@admin_required
def slot_status(sid):
    d = json_body()
    if d.get("status") not in ("AVAILABLE", "MAINTENANCE"):
        raise ApiError("status must be AVAILABLE or MAINTENANCE.")
    if not db.one("SELECT 1 AS x FROM parking_slots WHERE slot_id = %s", (sid,)):
        raise ApiError("Slot not found.", 404)
    audited(lambda: db.execute("UPDATE parking_slots SET status=%s WHERE slot_id=%s", (d["status"], sid)))
    return jsonify(message=f"Slot set to {d['status']}.")

@bp.get("/admin/users")
@admin_required
def users():
    """All accounts (never the password hash), with how many vehicles each owns."""
    return jsonify(db.rows("""SELECT u.user_id, u.full_name, u.email, u.phone, u.role, u.created_at,
                                     (SELECT COUNT(*) FROM vehicles v WHERE v.user_id = u.user_id) AS vehicles
                              FROM users u ORDER BY u.user_id LIMIT 500"""))

@bp.get("/admin/violations")
@admin_required
def violations():
    return jsonify(db.rows("""SELECT x.*, v.reg_number FROM violations x
                              JOIN vehicles v ON v.vehicle_id = x.vehicle_id
                              ORDER BY x.detected_at DESC LIMIT 200"""))

@bp.post("/admin/violations")
@admin_required
def add_violation():
    d = json_body()
    need(d, "session_id", "violation_type")
    if d["violation_type"] not in ("OVERSTAY", "WRONG_SLOT", "UNAUTHORIZED_BAY"):
        raise ApiError("Type must be OVERSTAY, WRONG_SLOT or UNAUTHORIZED_BAY.")
    fine = number(d.get("fine_amount") or 0, "fine_amount", 0, 99999)
    notes = opt_text(d.get("notes"), "notes", 255)
    db.call("sp_log_violation", (to_int(d["session_id"], "session_id"), d["violation_type"], fine, notes))
    return jsonify(message="Violation recorded."), 201

@bp.put("/admin/violations/<int:vid>/status")
@admin_required
def resolve_violation(vid):
    """Settle an OPEN violation: PAID (fine collected) or WAIVED (admin forgives it). One-way, and audited."""
    d = json_body()
    new = d.get("status")
    if new not in ("PAID", "WAIVED"):
        raise ApiError("status must be PAID or WAIVED.")
    with db.transaction() as cur:                          # the update and its audit row are saved together
        cur.execute("UPDATE violations SET status=%s WHERE violation_id=%s AND status='OPEN'", (new, vid))
        changed = cur.rowcount
        if changed:
            cur.execute("""INSERT INTO audit_logs (actor_user_id, action, entity, entity_id, old_value, new_value)
                           VALUES (%s, 'VIOLATION_RESOLVE', 'violations', %s, JSON_OBJECT('status', 'OPEN'),
                                   JSON_OBJECT('status', %s, 'fine_amount',
                                               (SELECT fine_amount FROM violations WHERE violation_id = %s)))""",
                        (session["uid"], vid, new, vid))
    if not changed:
        row = db.one("SELECT status FROM violations WHERE violation_id = %s", (vid,))
        if not row:
            raise ApiError("Violation not found.", 404)
        raise ApiError(f"Violation is already {row['status']}; only OPEN violations can be settled.", 409)
    return jsonify(message=f"Violation marked {new}.")

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
