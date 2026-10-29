"""
ParkWise API tests (Member 2).  Runs real HTTP requests against the running Flask app.

Before running:   1) reload schema.sql + seed.sql (default tariffs are assumed)
                  2) start the app:  cd backend ; python app.py
Run (second terminal, project root):   pip install requests   then   python tests_api.py
Optional:  python tests_api.py --url http://127.0.0.1:5000

The tests are independent of fixed ids: they look up vehicles and slots by their properties.
Concurrency tests (section F) send several requests at the same moment from threads.
One test (D5) back-dates an entry directly in the database through backend/config.py settings.
"""
import argparse, os, random, sys, threading
from datetime import datetime, timedelta
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:5000")
BASE = ap.parse_args().url.rstrip("/") + "/api"
results = []

def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"   -> {detail}"))

class Client:
    def __init__(self): self.s = requests.Session()
    def req(self, m, path, **kw): return self.s.request(m, BASE + path, timeout=20, **kw)
    def get(self, p, **kw): return self.req("GET", p, **kw)
    def post(self, p, body=None, **kw): return self.req("POST", p, json=body or {}, **kw)
    def put(self, p, body): return self.req("PUT", p, json=body)
    def delete(self, p): return self.req("DELETE", p)
    def login(self, email, pw):
        r = self.post("/auth/login", {"email": email, "password": pw}); return r

def fmt(d): return d.strftime("%Y-%m-%dT%H:%M")
def window(hours=2):
    """A random future time window so that re-running the tests never collides with old data."""
    s = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=random.randint(3, 60), hours=random.randint(1, 10))
    return fmt(s), fmt(s + timedelta(hours=hours))

anon, user, other, admin = Client(), Client(), Client(), Client()
made_res, made_sess = [], []

# ---------- setup: log in, then find vehicles and slots by their properties ----------
u = user.login("aarav@parkwise.test", "Student@123").json()
admin.login("admin@parkwise.test", "Admin@123")
other.login("admin@parkwise.test", "Admin@123")           # a second admin connection for threads
vehicles = admin.get("/vehicles").json()
slots = admin.get("/slots").json()
active_regs = {s["reg_number"] for s in admin.get("/sessions/active").json()}
plain = lambda v: v["vehicle_type"] == "CAR" and not v["is_ev"] and not v["has_accessible_permit"] and v["reg_number"] not in active_regs
my_cars = [v for v in vehicles if v["user_id"] == u["user_id"] and plain(v)]
my_bike = next((v for v in vehicles if v["user_id"] == u["user_id"] and v["vehicle_type"] == "TWO_WHEELER"), None)
others_cars = [v for v in vehicles if v["user_id"] != u["user_id"] and plain(v)]
others_any = next(v for v in vehicles if v["user_id"] != u["user_id"])
free = lambda s: s["live_status"] == "AVAILABLE"
car_slots = [s for s in slots if free(s) and s["slot_type"] == "CAR" and not s["is_ev_charger"] and not s["is_accessible"]]
ev_slot = next(s for s in slots if s["is_ev_charger"] and free(s))
acc_slot = next(s for s in slots if s["is_accessible"] and free(s))
bike_slot = next(s for s in slots if s["slot_type"] == "TWO_WHEELER" and free(s))
car = my_cars[0]
stranger = Client(); _em = f"tester{random.randint(10**6, 10**7)}@example.com"
stranger.post("/auth/register", {"full_name": "Test Stranger", "email": _em, "password": "secret1"}); stranger.login(_em, "secret1")

print("=== A. Access control ===")
check("A1 anonymous cannot reserve (401)", anon.post("/reservations", {}).status_code == 401)
check("A2 wrong password rejected (401)", Client().login("aarav@parkwise.test", "nope").status_code == 401)
check("A3 normal user cannot open admin audit (403)", user.get("/admin/audit").status_code == 403)
check("A4 normal user cannot open analytics (403)", user.get("/analytics/summary").status_code == 403)
check("A5 public live board works without login (200)", anon.get("/slots").status_code == 200)

print("=== B. Input validation ===")
s0, e0 = window()
check("B1 missing fields rejected (400)", user.post("/reservations", {"vehicle_id": car["vehicle_id"]}).status_code == 400)
check("B2 end before start rejected (400)", user.post("/reservations", {"vehicle_id": car["vehicle_id"], "slot_id": car_slots[0]["slot_id"], "start": e0, "end": s0}).status_code == 400)
check("B3 bad date format rejected (400)", user.post("/reservations", {"vehicle_id": car["vehicle_id"], "slot_id": car_slots[0]["slot_id"], "start": "tomorrow", "end": e0}).status_code == 400)
check("B4 unknown payment method rejected (400)", user.post("/payments", {"session_id": 1, "method": "BITCOIN"}).status_code == 400)

print("=== C. Reservation rules ===")
s1, e1 = window(); sl = car_slots[0]
r = user.post("/reservations", {"vehicle_id": car["vehicle_id"], "slot_id": sl["slot_id"], "start": s1, "end": e1})
check("C1 valid reservation created (201)", r.status_code == 201, r.text)
rid = r.json().get("reservation_id"); made_res.append(rid)
r = admin.post("/reservations", {"vehicle_id": others_cars[0]["vehicle_id"], "slot_id": sl["slot_id"], "start": s1, "end": e1})
check("C2 same slot, overlapping time refused (409)", r.status_code == 409, r.text)
r = user.post("/reservations", {"vehicle_id": others_any["vehicle_id"], "slot_id": car_slots[1]["slot_id"], "start": s1, "end": e1})
check("C3 cannot book with someone else's vehicle (403)", r.status_code == 403, r.text)
r = user.post("/reservations", {"vehicle_id": car["vehicle_id"], "slot_id": ev_slot["slot_id"], "start": s1, "end": e1})
check("C4 non-EV car refused an EV charger slot (409)", r.status_code == 409, r.text)
r = user.post("/reservations", {"vehicle_id": car["vehicle_id"], "slot_id": acc_slot["slot_id"], "start": s1, "end": e1})
check("C5 car without permit refused accessible bay (409)", r.status_code == 409, r.text)
if my_bike:
    r = user.post("/reservations", {"vehicle_id": my_bike["vehicle_id"], "slot_id": car_slots[1]["slot_id"], "start": s1, "end": e1})
    check("C6 two-wheeler refused a car slot (409)", r.status_code == 409, r.text)
check("C6b another user cannot cancel my reservation (not 200)", stranger.delete(f"/reservations/{rid}").status_code in (403, 409))
r = user.delete(f"/reservations/{rid}")
check("C7 owner can cancel a pending reservation (200)", r.status_code == 200, r.text)
r = user.delete(f"/reservations/{rid}")
check("C8 cancelling twice is refused (not 200)", r.status_code in (400, 409), r.text)
r = user.get("/reservations")
check("C9 reservation list returns only my rows", r.status_code == 200 and all(x["user_id"] == u["user_id"] for x in r.json()))

print("=== D. Entry, exit and billing ===")
v2 = my_cars[1] if len(my_cars) > 1 else my_cars[0]
sl_in = car_slots[2]
r = user.post("/sessions/entry", {"vehicle_id": car["vehicle_id"], "slot_id": sl_in["slot_id"]})
check("D1 entry recorded (201)", r.status_code == 201, r.text)
sid = r.json().get("session_id"); made_sess.append(sid)
r = user.post("/sessions/entry", {"vehicle_id": car["vehicle_id"], "slot_id": car_slots[3]["slot_id"]})
check("D2 same vehicle cannot enter twice (409)", r.status_code == 409, r.text)
r = admin.post("/sessions/entry", {"vehicle_id": others_cars[0]["vehicle_id"], "slot_id": sl_in["slot_id"]})
check("D3 occupied slot refuses a second vehicle (409)", r.status_code == 409, r.text)
r = admin.get(f"/bills/{sid}")
check("D4a no bill before exit (404)", r.status_code == 404, r.text)
r = user.post(f"/sessions/{sid}/exit")
check("D4 immediate exit is free (inside the grace period)", r.status_code == 200 and float(r.json()["amount_due"]) == 0, r.text)
r = user.post(f"/sessions/{sid}/exit")
check("D4b exit twice refused (409)", r.status_code == 409, r.text)
# D5: a 145-minute stay. Only the test may back-date the entry, directly in the DB (Decision D-13).
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
    import config, mysql.connector
    cn = mysql.connector.connect(autocommit=True, **config.DB); cu = cn.cursor()
    cu.callproc("sp_vehicle_entry", [car["vehicle_id"], car_slots[4]["slot_id"], datetime.now() - timedelta(minutes=145), 0])
    cu.execute("SELECT MAX(session_id) FROM parking_sessions WHERE vehicle_id=%s AND status='ACTIVE'", (car["vehicle_id"],))
    sid2 = cu.fetchone()[0]; made_sess.append(sid2)
    r = user.post(f"/sessions/{sid2}/exit")
    check("D5 145 minutes bills Rs 90 (default tariff)", r.status_code == 200 and float(r.json()["amount_due"]) == 90, r.text)
    check("D6 another user cannot read this bill (403)", stranger.get(f"/bills/{sid2}").status_code == 403)
    r = user.post("/payments", {"session_id": sid2, "method": "UPI", "simulate_failure": True})
    check("D7 failed payment leaves the bill unpaid", r.status_code == 200 and r.json()["bill"]["payment_status"] in ("FAILED", "PENDING"), r.text)
    r = user.post("/payments", {"session_id": sid2, "method": "UPI"})
    check("D8 retry succeeds and bill becomes PAID", r.status_code == 200 and r.json()["bill"]["payment_status"] == "PAID", r.text)
    r = user.post("/payments", {"session_id": sid2, "method": "UPI"})
    check("D9 paying an already paid bill is refused (409)", r.status_code == 409, r.text)
except Exception as ex:
    check("D5-D9 billing tests (needs backend/.env DB settings)", False, repr(ex))

print("=== E. Recommendation ===")
s2, e2 = window()
r = user.get(f"/recommend?vehicle_id={car['vehicle_id']}&start={s2}&end={e2}")
rec = r.json() if r.status_code == 200 else []
check("E1 recommendation returns ranked slots with reasons", r.status_code == 200 and rec and all("score" in x and "reason" in x for x in rec), r.text[:200])
check("E2 scores are sorted best-first", [x["score"] for x in rec] == sorted([x["score"] for x in rec], reverse=True))
check("E3 a non-EV car is never offered an EV charger or accessible bay",
      all(x["slot_id"] not in (ev_slot["slot_id"], acc_slot["slot_id"]) for x in rec))

print("=== F. Concurrency (several requests at the same moment) ===")
def race(n, make_call, clients):
    codes, gate = [None] * n, threading.Barrier(n)
    def run(i):
        gate.wait(); codes[i] = make_call(i, clients[i]).status_code
    ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    [t.start() for t in ts]; [t.join() for t in ts]
    return codes

pool = my_cars + others_cars
n = min(5, len(pool)); cl = [Client() for _ in range(n)]
[c.login("admin@parkwise.test", "Admin@123") for c in cl]
fresh = [s for s in car_slots if s["slot_id"] not in (sl["slot_id"], sl_in["slot_id"], car_slots[3]["slot_id"], car_slots[4]["slot_id"])]
for rnd in range(3):
    s3, e3 = window(); target = fresh[rnd]["slot_id"]
    codes = race(n, lambda i, c: c.post("/reservations", {"vehicle_id": pool[i]["vehicle_id"], "slot_id": target, "start": s3, "end": e3}), cl)
    check(f"F{rnd+1} {n} simultaneous bookings of one slot: exactly one wins", codes.count(201) == 1 and codes.count(409) == n - 1, str(codes))
codes = race(n, lambda i, c: c.post("/sessions/entry", {"vehicle_id": pool[i]["vehicle_id"], "slot_id": fresh[3]["slot_id"]}), cl)
check(f"F4 {n} simultaneous entries into one slot: exactly one wins", codes.count(201) == 1 and codes.count(409) == n - 1, str(codes))

# ---------- clean up so the demo data stays tidy ----------
for s in admin.get("/sessions/active").json():
    admin.post(f"/sessions/{s['session_id']}/exit")
for rr in admin.get("/reservations").json():
    if rr["status"] == "PENDING":
        admin.delete(f"/reservations/{rr['reservation_id']}")

print(f"\nRESULT: {sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
