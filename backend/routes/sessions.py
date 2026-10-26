from flask import Blueprint, request, jsonify, session
import db
from auth import login_required, is_admin, need, owns_vehicle, owns_session
from .util import to_int

bp = Blueprint("sessions", __name__)

@bp.post("/sessions/entry")
@login_required
def entry():
    d = request.get_json(silent=True) or {}
    need(d, "vehicle_id", "slot_id")
    vid, sid = to_int(d["vehicle_id"], "vehicle_id"), to_int(d["slot_id"], "slot_id")
    owns_vehicle(vid)
    # Time is ALWAYS NULL from Flask (Decision D-13): the database uses its own clock.
    out, _ = db.call("sp_vehicle_entry", (vid, sid, None, 0))
    return jsonify(session_id=out[-1], message="Entry recorded."), 201

@bp.post("/sessions/<int:sid>/exit")
@login_required
def exit_(sid):
    owns_session(sid)
    out, _ = db.call("sp_vehicle_exit", (sid, None, 0))
    bill = db.one("SELECT * FROM v_itemized_bill WHERE session_id = %s", (sid,))
    return jsonify(session_id=sid, amount_due=out[-1], bill=bill, message="Exit recorded. Bill generated.")

@bp.get("/sessions/active")
@login_required
def active():
    sql = "SELECT * FROM v_active_sessions"
    if is_admin():
        return jsonify(db.rows(sql + " ORDER BY entry_time"))
    return jsonify(db.rows(sql + " WHERE reg_number IN (SELECT reg_number FROM vehicles WHERE user_id = %s) ORDER BY entry_time",
                           (session["uid"],)))
