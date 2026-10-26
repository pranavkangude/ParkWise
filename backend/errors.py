"""Map database errors to the API error format {"error": "..."}."""
from flask import jsonify
import mysql.connector

class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

def register(app):
    @app.errorhandler(ApiError)
    def _api(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(mysql.connector.Error)
    def _db(e):
        state = getattr(e, "sqlstate", None)
        errno = getattr(e, "errno", None)
        msg = getattr(e, "msg", str(e))
        if state == "45000":                      # SIGNAL from our procedures/triggers = rule violated
            return jsonify(error=msg), 409
        if errno == 1062:
            return jsonify(error="That record already exists."), 409
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
