"""ParkWise traffic simulator: cars and bikes enter, stay, exit and pay, so dashboards and the board show activity.

Run from the backend folder (same DB settings as the app, from .env):
    python simulate.py --count 40 --delay 0.5
Entries are back-dated by 20-240 minutes so bills are realistic. Only this script may pass a time
to the procedures (Decision D-13); the Flask app always passes NULL.
"""
import argparse, random, time, warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from datetime import datetime, timedelta
import mysql.connector
import config

ap = argparse.ArgumentParser()
ap.add_argument("--count", type=int, default=30, help="number of random actions")
ap.add_argument("--delay", type=float, default=0.5, help="seconds between actions")
ap.add_argument("--seed", type=int, default=None)
a = ap.parse_args()
random.seed(a.seed)

cn = mysql.connector.connect(autocommit=True, **config.DB)
cu = cn.cursor(dictionary=True)
plain = cn.cursor()

def q(sql, p=()):
    cu.execute(sql, p); return cu.fetchall()

def enter():
    free = q("""SELECT v.vehicle_id, v.reg_number FROM vehicles v
                WHERE NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.vehicle_id=v.vehicle_id AND s.status='ACTIVE')""")
    if not free:
        return "no free vehicle"
    v = random.choice(free)
    now = datetime.now()
    plain.callproc("sp_recommend_slots", [v["vehicle_id"], now, now + timedelta(hours=2)])
    recs = [dict(zip([d[0] for d in r.description], row)) for r in plain.stored_results() for row in r.fetchall()]
    top = recs[:3]
    random.shuffle(top)
    for r in top:
        try:
            at = now - timedelta(minutes=random.randint(20, 240))
            out = plain.callproc("sp_vehicle_entry", [v["vehicle_id"], r["slot_id"], at, 0])
            return f"ENTRY  {v['reg_number']} -> {r['slot_code']} (session {out[-1]}, back-dated {at:%H:%M})"
        except mysql.connector.Error as e:
            last = e.msg
    return f"entry skipped ({last if recs else 'no slot available'})"

def leave():
    act = q("SELECT session_id FROM v_active_sessions")
    if not act:
        return "nobody inside"
    sid = random.choice(act)["session_id"]
    out = plain.callproc("sp_vehicle_exit", [sid, None, 0])
    msg = f"EXIT   session {sid}, bill Rs {out[-1]}"
    if float(out[-1]) > 0:
        method = random.choice(["UPI", "CARD", "CASH"])
        if random.random() < 0.15:
            try:
                plain.callproc("sp_record_payment", [sid, method, 0]); msg += " | payment FAILED, retrying"
            except mysql.connector.Error:
                pass
        plain.callproc("sp_record_payment", [sid, method, 1]); msg += f" | paid via {method}"
    return msg

for i in range(1, a.count + 1):
    inside = q("SELECT COUNT(*) n FROM v_active_sessions")[0]["n"]
    do_enter = inside < 4 or (inside < 14 and random.random() < 0.55)
    try:
        print(f"[{i:02d}] " + (enter() if do_enter else leave()))
    except mysql.connector.Error as e:
        print(f"[{i:02d}] rule blocked: {e.msg}")
    time.sleep(a.delay)
print("Done. Open the live board / analytics page.")
