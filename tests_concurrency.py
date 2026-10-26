"""
ParkWise concurrency test - proves the DB prevents double-booking / double-entry.

Run on a FRESH database (schema.sql + seed.sql), then:
    pip install mysql-connector-python
    python tests_concurrency.py --user root --password YOUR_PASSWORD
Windows/VS Code: same command in the terminal.  Expected: "RESULT: PASS".
"""
import argparse, threading, sys
import mysql.connector

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=3306)
ap.add_argument("--user", default="root")
ap.add_argument("--password", default="")
ap.add_argument("--socket", default=None, help="unix socket (Linux only)")
ap.add_argument("--rounds", type=int, default=20)
args = ap.parse_args()

def connect():
    kw = dict(user=args.user, password=args.password, database="parkwise", autocommit=True)
    if args.socket:
        kw["unix_socket"] = args.socket
    else:
        kw.update(host=args.host, port=args.port)
    return mysql.connector.connect(**kw)

# (user_id, vehicle_id) pairs - plain cars (no EV / permit), different owners
CONTENDERS = [(2, 1), (5, 7), (7, 11), (2, 13), (3, 14)]
# plain car slots: A-03..A-08 (ids 3-8), B-03..B-06 (ids 11-14), D-01..D-04 (ids 21-24)
SLOTS = [3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 21, 22, 23, 24]

def race(worker, rounds_slots):
    """Run `worker(conn, idx, round)` for every contender at the same instant, per round."""
    results = {}
    for rnd, slot in enumerate(rounds_slots):
        barrier = threading.Barrier(len(CONTENDERS))
        out = [None] * len(CONTENDERS)
        def run(i):
            conn = connect()
            cur = conn.cursor()
            barrier.wait()
            try:
                worker(cur, i, rnd, slot)
                out[i] = "OK"
            except mysql.connector.Error as e:
                out[i] = "ERR:" + (e.msg or str(e))
            finally:
                cur.close(); conn.close()
        ts = [threading.Thread(target=run, args=(i,)) for i in range(len(CONTENDERS))]
        [t.start() for t in ts]; [t.join() for t in ts]
        results[rnd] = out
    return results

ok = True

# ---- Test 1: five users book the SAME slot for the SAME time at the same instant ----
def book(cur, i, rnd, slot):
    u, v = CONTENDERS[i]
    start_min = 120 + rnd * 120            # each round uses its own 1-hour window, +2h apart
    cur.execute("CALL sp_create_reservation(%s,%s,%s, NOW() + INTERVAL %s MINUTE, "
                "NOW() + INTERVAL %s MINUTE, NULL, NULL, @r)", (u, v, slot, start_min, start_min + 60))
    cur.fetchall() if cur.with_rows else None

rounds = [SLOTS[r % len(SLOTS)] for r in range(args.rounds)]
res = race(book, rounds)
wins = sum(1 for r in res.values() for x in r if x == "OK")
bad_rounds = [r for r, out in res.items() if sum(1 for x in out if x == "OK") != 1]
print(f"[double-booking] rounds={args.rounds} contenders/round={len(CONTENDERS)} successes={wins}")
if wins != args.rounds or bad_rounds:
    ok = False
    print("  FAIL: expected exactly 1 success per round; bad rounds:", bad_rounds)
conn = connect(); cur = conn.cursor()
cur.execute("""SELECT COUNT(*) FROM reservations a JOIN reservations b
                 ON a.slot_id = b.slot_id AND a.reservation_id < b.reservation_id
                AND a.status IN ('PENDING','ACTIVE') AND b.status IN ('PENDING','ACTIVE')
                AND a.start_time < b.end_time AND a.end_time > b.start_time""")
overlaps = cur.fetchone()[0]
print(f"[double-booking] overlapping reservation pairs in DB = {overlaps}")
if overlaps != 0:
    ok = False

# ---- Test 2: five vehicles try to ENTER the same free slot at the same instant ----
def enter(cur, i, rnd, slot):
    _, v = CONTENDERS[i]
    cur.execute("CALL sp_vehicle_entry(%s,%s,NULL,@s)", (v, slot))
    cur.fetchall() if cur.with_rows else None

entry_slots = [21, 22, 23]       # D-01..D-03: no reservations were made on them in Test 1 within 2h
res2 = race(enter, entry_slots)
for rnd, out in res2.items():
    n = sum(1 for x in out if x == "OK")
    print(f"[double-entry] slot {entry_slots[rnd]}: successes={n}")
    if n != 1:
        ok = False
cur.execute("SELECT slot_id, COUNT(*) FROM parking_sessions WHERE status='ACTIVE' GROUP BY slot_id HAVING COUNT(*) > 1")
dups = cur.fetchall()
print(f"[double-entry] slots with >1 active session = {len(dups)}")
if dups:
    ok = False
cur.close(); conn.close()

print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
