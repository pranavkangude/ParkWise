"""ParkWise Flask app. Run:  python app.py   then open http://127.0.0.1:5000"""
import os, datetime, decimal
from flask import Flask, send_from_directory
from flask.json.provider import DefaultJSONProvider
import config, db, errors

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
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    app.teardown_appcontext(db.close_conn)
    errors.register(app)

    import auth
    from routes import vehicles, slots, reservations, sessions, billing, admin, analytics
    for m in (auth, vehicles, slots, reservations, sessions, billing, admin, analytics):
        app.register_blueprint(m.bp, url_prefix="/api")

    @app.get("/")
    def home():
        return send_from_directory(static, "index.html")
    return app

app = create_app()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
