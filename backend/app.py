"""ParkWise Flask app. Run:  python app.py   then open http://127.0.0.1:5000"""
import os, datetime, decimal
from urllib.parse import urlparse
from flask import Flask, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
import config, db, errors
from errors import ApiError

class Json(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, datetime.datetime):
            return o.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(o, (datetime.date, datetime.time, datetime.timedelta)):
            return str(o)
        return DefaultJSONProvider.default(o)

def create_app():
    static = os.path.join(os.path.dirname(__file__), "..", "frontend", "static")
    app = Flask(__name__, static_folder=static, static_url_path="/static")
    app.json = Json(app)
    app.secret_key = config.SECRET_KEY
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      MAX_CONTENT_LENGTH=config.MAX_BODY_BYTES)
    app.teardown_appcontext(db.close_conn)
    errors.register(app)

    import auth
    from routes import vehicles, slots, reservations, sessions, billing, admin, analytics
    for m in (auth, vehicles, slots, reservations, sessions, billing, admin, analytics):
        app.register_blueprint(m.bp, url_prefix="/api")

    # Safety net (Decision D-19): every /api/admin/* and /api/analytics/* route must carry @admin_required.
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith(("/api/admin/", "/api/analytics/")):
            if not getattr(app.view_functions[rule.endpoint], "admin_guard", False):
                raise RuntimeError(f"Route {rule.rule} is missing @admin_required")

    @app.before_request
    def block_cross_site_writes():
        """CSRF defence in addition to SameSite=Lax: a browser always sends Origin on POST/PUT/DELETE.
        If it names another site, refuse. Scripts and tests send no Origin and are not affected."""
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin is not None and urlparse(origin).netloc != request.host:
                raise ApiError("Cross-site request blocked.", 403)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"      # private data must not be re-shown from the browser cache
        return resp

    @app.get("/")
    def home():
        return send_from_directory(static, "index.html")
    return app

app = create_app()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
