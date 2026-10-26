from flask import Blueprint, request, jsonify, session
import db
from auth import login_required, is_admin, need, owns_session
from errors import ApiError
from .util import to_int

bp = Blueprint("billing", __name__)

@bp.get("/bills/unpaid")
@login_required
def unpaid():
    sql = "SELECT * FROM v_unpaid_bills"
    if is_admin():
        return jsonify(db.rows(sql + " ORDER BY exit_time"))
    return jsonify(db.rows(sql + " WHERE reg_number IN (SELECT reg_number FROM vehicles WHERE user_id = %s) ORDER BY exit_time",
                           (session["uid"],)))

@bp.get("/bills/<int:sid>")
@login_required
def bill(sid):
    owns_session(sid)
    b = db.one("SELECT * FROM v_itemized_bill WHERE session_id = %s", (sid,))
    if not b:
        raise ApiError("No bill yet. The vehicle has not exited.", 404)
    return jsonify(b)

@bp.post("/payments")
@login_required
def pay():
    d = request.get_json(silent=True) or {}
    need(d, "session_id", "method")
    sid = to_int(d["session_id"], "session_id")
    if d["method"] not in ("CASH", "UPI", "CARD"):
        raise ApiError("method must be CASH, UPI or CARD.")
    owns_session(sid)
    success = 0 if d.get("simulate_failure") else 1      # payments are simulated (no real gateway)
    _, sets = db.call("sp_record_payment", (sid, d["method"], success))
    b = db.one("SELECT * FROM v_itemized_bill WHERE session_id = %s", (sid,))
    return jsonify(bill=b, result=(sets[0][0] if sets and sets[0] else None),
                   message="Payment successful." if success else "Payment failed. You can retry.")
