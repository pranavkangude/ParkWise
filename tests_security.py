"""
ParkWise account, admin and security tests (Member 3). Real HTTP requests against the running Flask app.

Before running:   1) reload schema.sql + seed.sql (default tariffs and demo logins are assumed)
                  2) start the app:  cd backend ; python app.py     (default settings: 5 failed logins / 15 min)
Run (second terminal, project root):   pip install requests   then   python tests_security.py
Optional:  python tests_security.py --url http://127.0.0.1:5000

Sections:  T tariffs   V vehicles   U admin user list   W settle violations   S security (negative tests)
The tests use random plates and e-mails, so they can be re-run. They leave the demo data tidy at the end.
The login-limit tests use throw-away accounts, so the demo logins are never locked.
"""
import argparse, os, random, sys
from datetime import datetime, timedelta
from urllib.parse import urlparse
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:5000")
URL = ap.parse_args().url.rstrip("/")
BASE = URL + "/api"
HOST = urlparse(URL).netloc
results = []

def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"   -> {detail}"))

class Client:
    def __init__(self): self.s = requests.Session()
    def req(self, m, path, **kw): return self.s.request(m, BASE + path, timeout=20, **kw)
    def get(self, p, **kw): return self.req("GET", p, **kw)
    def post(self, p, body=None, **kw): return self.req("POST", p, json=body if body is not None else {}, **kw)
    def put(self, p, body=None, **kw): return self.req("PUT", p, json=body if body is not None else {}, **kw)
    def delete(self, p, **kw): return self.req("DELETE", p, **kw)
    def login(self, email, pw): return self.post("/auth/login", {"email": email, "password": pw})

def fmt(d): return d.strftime("%Y-%m-%dT%H:%M")
def window(hours=2):
    """A random far-future window (70 to 120 days ahead) so re-runs never collide with tests_api.py data."""
    s = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=random.randint(70, 120), hours=random.randint(1, 10))
    return fmt(s), fmt(s + timedelta(hours=hours))
def rnd(): return random.randint(10**6, 10**7)
def plate(): return f"MH{random.randint(10, 99)}ZZ{random.randint(1000, 9999)}"
def new_account(prefix="sec"):
    c = Client(); email = f"{prefix}{rnd()}@example.com"
    r = c.post("/auth/register", {"full_name": "Test Person", "email": email, "password": "secret1"})
    c.login(email, "secret1")
    return c, email, r

anon, user, admin = Client(), Client(), Client()
u = user.login("aarav@parkwise.test", "Student@123").json()
admin.login("admin@parkwise.test", "Admin@123")
stranger, stranger_email, _ = new_account("stranger")
vehicles = admin.get("/vehicles").json()
others_vehicle = next(v for v in vehicles if v["user_id"] != u["user_id"])
slots = admin.get("/slots").json()
car_slots = [s for s in slots if s["live_status"] == "AVAILABLE" and s["slot_type"] == "CAR" and not s["is_ev_charger"] and not s["is_accessible"]]
made_vehicles = []

def mkcar(client=user, **extra):
    r = client.post("/vehicles", {"reg_number": plate(), "vehicle_type": "CAR", **extra})
    vid = r.json().get("vehicle_id"); made_vehicles.append(vid)
    return vid, r

# =====================================================================================
print("=== T. Tariffs (task 2: saving unchanged values) ===")
tariffs = admin.get("/admin/tariffs").json()
tr = next(t for t in tariffs if t["vehicle_type"] == "TWO_WHEELER")
body = {k: tr[k] for k in ("tariff_id", "hourly_rate", "grace_minutes", "min_charge", "daily_cap", "overstay_fine_per_hour")}
r = admin.put("/admin/tariffs", body)
check("T1 saving the same values again gives 200 'No change' (was 404)", r.status_code == 200 and r.json().get("changed") is False, r.text)
changed = dict(body, hourly_rate=float(body["hourly_rate"]) + 1)
r = admin.put("/admin/tariffs", changed)
check("T2 a real change gives 200 and changed=true", r.status_code == 200 and r.json().get("changed") is True, r.text)
a0 = admin.get("/admin/audit").json()[0]
check("T3 the audit log names the admin who changed the tariff", a0["action"] == "TARIFF_UPDATE" and a0["actor"] == "Parking Admin", str(a0))
admin.put("/admin/tariffs", body)                                  # restore the original price
check("T4 unknown tariff id gives 404", admin.put("/admin/tariffs", dict(body, tariff_id=99999)).status_code == 404)
bad = [("text rate", dict(body, hourly_rate="abc")), ("negative rate", dict(body, hourly_rate=-5)), ("zero rate", dict(body, hourly_rate=0)),
       ("cap below minimum", dict(body, min_charge=100, daily_cap=50)), ("fractional grace", dict(body, grace_minutes=10.5)),
       ("huge grace", dict(body, grace_minutes=99999))]
check("T5 invalid tariff numbers are all refused with 400", all(admin.put("/admin/tariffs", b).status_code == 400 for _, b in bad),
      str([(n, admin.put("/admin/tariffs", b).status_code) for n, b in bad]))

# =====================================================================================
print("=== V. Vehicles (task 1: edit and delete) ===")
vid, r = mkcar()
check("V1 add a vehicle (201)", r.status_code == 201, r.text)
new_plate = plate()
r = user.put(f"/vehicles/{vid}", {"reg_number": new_plate.lower()})
check("V2 edit the plate (200, saved upper-case)", r.status_code == 200 and any(v["reg_number"] == new_plate for v in user.get("/vehicles").json()), r.text)
r = user.put(f"/vehicles/{vid}", {"reg_number": new_plate, "vehicle_type": "CAR"})
check("V3 saving identical values gives 200 'No change'", r.status_code == 200 and r.json().get("changed") is False, r.text)
r = user.put(f"/vehicles/{vid}", {"reg_number": others_vehicle["reg_number"]})
check("V4 a plate that already exists is refused (409)", r.status_code == 409, r.text)
check("V5 another user cannot edit my vehicle (403)", stranger.put(f"/vehicles/{vid}", {"is_ev": True}).status_code == 403)
check("V6 another user cannot delete my vehicle (403)", stranger.delete(f"/vehicles/{vid}").status_code == 403)
check("V7 editing an unknown vehicle gives 404", user.put("/vehicles/999999", {"is_ev": True}).status_code == 404)
check("V8 is_ev as the text \"false\" is refused (400), not treated as true", user.put(f"/vehicles/{vid}", {"is_ev": "false"}).status_code == 400)
check("V9 an edit with no fields is refused (400)", user.put(f"/vehicles/{vid}", {}).status_code == 400)

s1, e1 = window(); slot = car_slots[0]
r = user.post("/reservations", {"vehicle_id": vid, "slot_id": slot["slot_id"], "start": s1, "end": e1}); rid = r.json().get("reservation_id")
r = user.put(f"/vehicles/{vid}", {"vehicle_type": "TWO_WHEELER"})
check("V10 type cannot change while a reservation is open (409)", r.status_code == 409, r.text)
user.delete(f"/reservations/{rid}")
r = user.delete(f"/vehicles/{vid}")
check("V11 a vehicle with reservation history cannot be deleted: clear 409 message", r.status_code == 409 and "reservation" in r.json().get("error", ""), r.text)
r = user.put(f"/vehicles/{vid}", {"is_ev": True})
check("V12 after cancelling, EV flag can change (200)", r.status_code == 200, r.text)
fresh, _ = mkcar()
r = user.delete(f"/vehicles/{fresh}")
check("V13 a vehicle without history can be deleted (200)", r.status_code == 200 and not any(v["vehicle_id"] == fresh for v in user.get("/vehicles").json()), r.text)

# =====================================================================================
print("=== U. Admin user list ===")
r = admin.get("/admin/users"); users = r.json() if r.status_code == 200 else []
check("U1 admin sees all users, with vehicle counts, and no password hash",
      r.status_code == 200 and any(x["email"] == "aarav@parkwise.test" for x in users) and all("password_hash" not in x and "vehicles" in x for x in users), r.text[:200])
check("U2 a normal user cannot list users (403)", user.get("/admin/users").status_code == 403)
check("U3 anonymous cannot list users (401)", anon.get("/admin/users").status_code == 401)

# =====================================================================================
print("=== W. Settle violations (task 1: resolve or waive) ===")
wc, _ = mkcar()
slot_w = car_slots[1]
r = user.post("/sessions/entry", {"vehicle_id": wc, "slot_id": slot_w["slot_id"]}); wsid = r.json().get("session_id")
user.post(f"/sessions/{wsid}/exit")
admin.post("/admin/violations", {"session_id": wsid, "violation_type": "WRONG_SLOT", "fine_amount": 25, "notes": "test violation"})
def find_viol(sid): return next((x for x in admin.get("/admin/violations").json() if x["session_id"] == sid), None)
vio = find_viol(wsid)
check("W1 a logged violation starts OPEN", vio is not None and vio["status"] == "OPEN", str(vio))
vv = vio["violation_id"] if vio else 0
check("W2 a normal user cannot settle a violation (403)", user.put(f"/admin/violations/{vv}/status", {"status": "WAIVED"}).status_code == 403)
check("W3 a bad status is refused (400)", admin.put(f"/admin/violations/{vv}/status", {"status": "DELETED"}).status_code == 400)
check("W4 unknown violation gives 404", admin.put("/admin/violations/999999/status", {"status": "PAID"}).status_code == 404)
r = admin.put(f"/admin/violations/{vv}/status", {"status": "WAIVED"})
check("W5 admin waives an OPEN violation (200)", r.status_code == 200 and find_viol(wsid)["status"] == "WAIVED", r.text)
r = admin.put(f"/admin/violations/{vv}/status", {"status": "PAID"})
check("W6 a settled violation cannot be changed again (409)", r.status_code == 409, r.text)
a0 = admin.get("/admin/audit").json()[0]
check("W7 the audit log records who waived it", a0["action"] == "VIOLATION_RESOLVE" and a0["entity_id"] == vv and a0["actor"] == "Parking Admin", str(a0))

# =====================================================================================
print("=== S. Security (negative tests) ===")
admin_routes = [("GET", "/admin/tariffs"), ("PUT", "/admin/tariffs"), ("PUT", "/admin/slots/1/status"), ("GET", "/admin/users"),
                ("GET", "/admin/violations"), ("POST", "/admin/violations"), ("PUT", "/admin/violations/1/status"),
                ("GET", "/admin/audit"), ("POST", "/admin/run-jobs"), ("GET", "/analytics/summary"), ("GET", "/analytics/revenue"),
                ("GET", "/analytics/hourly-demand"), ("GET", "/analytics/forecast"), ("GET", "/analytics/carbon")]
codes_anon = [anon.req(m, p, json={} if m != "GET" else None).status_code for m, p in admin_routes]
codes_user = [user.req(m, p, json={} if m != "GET" else None).status_code for m, p in admin_routes]
check("S1 every admin and analytics route refuses anonymous visitors (401)", all(c == 401 for c in codes_anon), str(codes_anon))
check("S2 every admin and analytics route refuses a normal user (403)", all(c == 403 for c in codes_user), str(codes_user))
try:                                           # static check: the code itself, not only the answers
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
    from app import app as flask_app
    missing = [r.rule for r in flask_app.url_map.iter_rules()
               if r.rule.startswith(("/api/admin/", "/api/analytics/")) and not getattr(flask_app.view_functions[r.endpoint], "admin_guard", False)]
    check("S3 no /api/admin or /api/analytics route is missing the admin guard (code check)", not missing, str(missing))
except Exception as ex:
    check("S3 admin-guard code check (needs backend/ and its libraries)", False, repr(ex))

other_vid = others_vehicle["vehicle_id"]; s2, e2 = window()
check("S4 cannot reserve with someone else's vehicle (403)", user.post("/reservations", {"vehicle_id": other_vid, "slot_id": car_slots[2]["slot_id"], "start": s2, "end": e2}).status_code == 403)
check("S5 cannot enter a slot with someone else's vehicle (403)", user.post("/sessions/entry", {"vehicle_id": other_vid, "slot_id": car_slots[2]["slot_id"]}).status_code == 403)
check("S6 cannot ask for recommendations for someone else's vehicle (403)", user.get(f"/recommend?vehicle_id={other_vid}&start={s2}&end={e2}").status_code == 403)
check("S7 another user cannot read, exit or pay my session (403 each)",
      [stranger.get(f"/bills/{wsid}").status_code, stranger.post(f"/sessions/{wsid}/exit").status_code,
       stranger.post("/payments", {"session_id": wsid, "method": "UPI"}).status_code] == [403, 403, 403])

bad_regs = [("email is a number", {"full_name": "A", "email": 12345, "password": "secret1"}),
            ("name over 100 characters", {"full_name": "x" * 101, "email": f"a{rnd()}@example.com", "password": "secret1"}),
            ("password over 128 characters", {"full_name": "A", "email": f"a{rnd()}@example.com", "password": "p" * 129}),
            ("password too short", {"full_name": "A", "email": f"a{rnd()}@example.com", "password": "abc"}),
            ("phone with letters", {"full_name": "A", "email": f"a{rnd()}@example.com", "password": "secret1", "phone": "98ab543210"}),
            ("name is a list", {"full_name": ["A"], "email": f"a{rnd()}@example.com", "password": "secret1"})]
res = [(n, anon.post("/auth/register", b).status_code) for n, b in bad_regs]
check("S8 bad registration input gives 400 (never a 500 crash)", all(c == 400 for _, c in res), str(res))
check("S9 a JSON list instead of an object gives 400", anon.req("POST", "/auth/register", data="[1,2]", headers={"Content-Type": "application/json"}).status_code == 400)
check("S10 invalid JSON gives 400", anon.req("POST", "/auth/login", data="{not json", headers={"Content-Type": "application/json"}).status_code == 400)
check("S11 an oversized request body gives 413", anon.post("/auth/register", {"full_name": "x" * 70000, "email": "a@b.co", "password": "secret1"}).status_code == 413)
r = anon.login("' OR '1'='1", "' OR '1'='1")
check("S12 SQL injection in the login form is just a wrong login (401)", r.status_code == 401 and Client().login("aarav@parkwise.test", "Student@123").status_code == 200, r.text)
check("S13 registering an existing e-mail is refused (409)", anon.post("/auth/register", {"full_name": "A", "email": stranger_email, "password": "secret1"}).status_code == 409)
em = f"sneaky{rnd()}@example.com"
Client().post("/auth/register", {"full_name": "Sneaky", "email": em, "password": "secret1", "role": "ADMIN"})
check("S14 a new account cannot make itself ADMIN through the request body", Client().login(em, "secret1").json().get("role") == "USER")

# login limit: throw-away accounts only
lim, lim_email, _ = new_account("limit")
fails = [Client().login(lim_email, "wrong").status_code for _ in range(5)]
r6 = Client().login(lim_email, "secret1")
check("S15 five wrong passwords, then even the right password is refused (429 with Retry-After)",
      fails == [401] * 5 and r6.status_code == 429 and "Retry-After" in r6.headers, f"{fails} {r6.status_code} {r6.text}")
other_lim, other_email, _ = new_account("limitb")
check("S16 the limit is per e-mail: other accounts and the demo logins still work",
      Client().login(other_email, "secret1").status_code == 200 and Client().login("admin@parkwise.test", "Admin@123").status_code == 200)
clr, clr_email, _ = new_account("clear")
steps = [Client().login(clr_email, "wrong").status_code for _ in range(4)] + [Client().login(clr_email, "secret1").status_code] + \
        [Client().login(clr_email, "wrong").status_code for _ in range(4)] + [Client().login(clr_email, "secret1").status_code]
check("S17 a successful login resets the failure counter", steps == [401] * 4 + [200] + [401] * 4 + [200], str(steps))

r = Client().post("/auth/login", {"email": "aarav@parkwise.test", "password": "wrong"}, headers={"Origin": "http://evil.example"})
r_ok = Client().post("/auth/login", {"email": "aarav@parkwise.test", "password": "wrong"}, headers={"Origin": URL})
check("S18 a write from another site (foreign Origin header) is blocked (403); the same site passes through", r.status_code == 403 and r_ok.status_code == 401, f"{r.status_code} {r_ok.status_code}")
r = Client().login("aarav@parkwise.test", "Student@123"); cookie = r.headers.get("Set-Cookie", "")
check("S19 session cookie is HttpOnly and SameSite=Lax", "HttpOnly" in cookie and "SameSite=Lax" in cookie, cookie)
r = anon.get("/slots")
check("S20 security headers are set (nosniff, frame deny) and API answers are not cached",
      r.headers.get("X-Content-Type-Options") == "nosniff" and r.headers.get("X-Frame-Options") == "DENY" and r.headers.get("Cache-Control") == "no-store", str(dict(r.headers)))
lo, lo_email, _ = new_account("logout"); lo.post("/auth/logout")
check("S21 after logout the old session no longer works (401)", lo.get("/me").status_code == 401)
check("S22 login and profile never return the password hash", "password_hash" not in user.get("/me").text and "password_hash" not in Client().login("aarav@parkwise.test", "Student@123").text)

tv, _ = mkcar(); s3, e3 = window()
user.post("/reservations", {"vehicle_id": tv, "slot_id": car_slots[3]["slot_id"], "start": s3, "end": e3, "alloc_score": 99, "alloc_reason": "HACKED"})
mine = next((x for x in user.get("/reservations").json() if x["reg_number"] and x["slot_code"] == car_slots[3]["slot_code"] and x["start_time"].startswith(s3.replace("T", " "))), None)
check("S23 a faked alloc_score / alloc_reason from the browser is ignored (the database computes them)",
      mine is not None and (mine["alloc_score"] is None or float(mine["alloc_score"]) <= 1) and mine["alloc_reason"] != "HACKED", str(mine))
if mine: user.delete(f"/reservations/{mine['reservation_id']}")
ev, _ = mkcar()
r = user.post("/sessions/entry", {"vehicle_id": ev, "slot_id": car_slots[4]["slot_id"], "entry_time": "2020-01-01 00:00:00"}); esid = r.json().get("session_id")
r = user.post(f"/sessions/{esid}/exit")
check("S24 a client-supplied entry time is ignored (D-13): an instant exit still bills Rs 0", r.status_code == 200 and float(r.json()["amount_due"]) == 0, r.text)

# ---------- clean up ----------
for s in admin.get("/sessions/active").json():
    admin.post(f"/sessions/{s['session_id']}/exit")
for rr in admin.get("/reservations").json():
    if rr["status"] == "PENDING":
        admin.delete(f"/reservations/{rr['reservation_id']}")

print(f"\nRESULT: {sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
