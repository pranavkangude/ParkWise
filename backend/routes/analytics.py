from flask import Blueprint, jsonify
import db
from auth import admin_required

bp = Blueprint("analytics", __name__)

@bp.get("/analytics/summary")
@admin_required
def summary():
    return jsonify(db.one("""SELECT
      (SELECT COUNT(*) FROM parking_sessions WHERE status='ACTIVE') AS active_sessions,
      (SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='PAID' AND DATE(paid_at)=CURDATE()) AS revenue_today,
      (SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='PAID') AS revenue_total,
      (SELECT COUNT(*) FROM v_unpaid_bills) AS unpaid_bills,
      (SELECT COUNT(*) FROM violations WHERE status='OPEN') AS open_violations,
      (SELECT COUNT(*) FROM reservations WHERE status='PENDING') AS pending_reservations,
      (SELECT ROUND(100*SUM(live_status='OCCUPIED')/NULLIF(SUM(live_status<>'MAINTENANCE'),0),1)
         FROM v_slot_live_status) AS occupancy_pct"""))

@bp.get("/analytics/revenue")
@admin_required
def revenue():
    r = db.rows("SELECT revenue_date, payments_count, revenue FROM v_daily_revenue ORDER BY revenue_date DESC LIMIT 30")
    return jsonify(list(reversed(r)))

@bp.get("/analytics/hourly-demand")
@admin_required
def hourly():
    return jsonify(db.rows("SELECT * FROM v_hourly_demand ORDER BY hour_of_day"))

@bp.get("/analytics/forecast")
@admin_required
def forecast():
    return jsonify(db.rows("SELECT * FROM v_occupancy_forecast ORDER BY day_of_week, hour_of_day"))

@bp.get("/analytics/carbon")
@admin_required
def carbon():
    s = db.one("""SELECT COUNT(*) AS sessions, ROUND(COALESCE(SUM(saved_m),0),0) AS metres_saved,
                  ROUND(COALESCE(SUM(co2_saved_g),0),1) AS co2_saved_g FROM v_carbon_estimate""")
    s["note"] = "Estimate only: distance saved vs an average slot of the same type x an emission factor (Decision D-10)."
    return jsonify(s)
