from flask import Blueprint, request, jsonify
import db
from auth import login_required, owns_vehicle
from .util import parse_dt, to_int
from errors import ApiError

bp = Blueprint("slots", __name__)

@bp.get("/slots")
def slots():
    return jsonify(db.rows("SELECT * FROM v_slot_live_status ORDER BY zone_code, slot_code"))

@bp.get("/zones/occupancy")
def zones():
    return jsonify(db.rows("SELECT * FROM v_zone_occupancy ORDER BY zone_code"))

@bp.get("/recommend")
@login_required
def recommend():
    vid = to_int(request.args.get("vehicle_id"), "vehicle_id")
    start, end = parse_dt(request.args.get("start"), "start"), parse_dt(request.args.get("end"), "end")
    if end <= start:
        raise ApiError("End time must be after start time.")
    owns_vehicle(vid)
    _, sets = db.call("sp_recommend_slots", (vid, start, end))
    return jsonify(sets[0] if sets else [])
