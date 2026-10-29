"""Map errors to the API error format {"error": "..."}."""
from flask import jsonify
import mysql.connector

class ApiError(Exception):
    def __init__(self, message, status=400, headers=None):
        self.message, self.status, self.headers = message, status, headers or {}

def register(app):
    @app.errorhandler(ApiError)
    def _api(e):
        return jsonify(error=e.message), e.status, e.headers

    @app.errorhandler(mysql.connector.Error)
    def _db(e):
        state = getattr(e, "sqlstate", None)
        errno = getattr(e, "errno", None)
        msg = getattr(e, "msg", str(e))
        if state == "45000":                      # SIGNAL from our procedures/triggers = rule violated
            return jsonify(error=msg), 409
        if errno == 1062:
            return jsonify(error="That record already exists."), 409
        if errno == 1451:                         # DELETE/UPDATE blocked by a foreign key
            return jsonify(error="This record is still used by other records, so it cannot be removed."), 409
        if errno == 1213:                         # deadlock: InnoDB rolled this request back
            return jsonify(error="Another request was changing the same data. Please try again."), 409
        if errno == 1205:                         # lock wait timeout (Decision D-05)
            return jsonify(error="The system is busy. Please try again in a moment."), 503
        if errno in (3819, 4025, 1048, 1452, 1264, 1265):   # CHECK / NOT NULL / FK / range
            return jsonify(error="Invalid data: " + msg), 400
        app.logger.exception("database error")
        return jsonify(error="Database error. See server log."), 500

    @app.errorhandler(404)
    def _404(_e):
        return jsonify(error="Not found"), 404

    @app.errorhandler(405)
    def _405(_e):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(413)
    def _413(_e):
        return jsonify(error="Request is too large."), 413

    @app.errorhandler(500)
    def _500(_e):
        return jsonify(error="Unexpected server error. See server log."), 500
