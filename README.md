# ParkWise: Smart Parking Allocation & Predictive Management System

DBMS course project · MySQL 8 · Flask · HTML/CSS/JS · One parking lot, four zones (A to D), 24 slots

**The database is the brain.** Every rule that must never be broken (no double booking, who may use which bay, billing, audit) lives in MySQL. Flask is a thin layer that checks who you are and calls the database. The browser only shows and sends.

## 1. Quick start (from a clean clone)

You need: Windows, **MySQL Server 8.0**, **Python 3.10 or newer** (the pinned libraries were tested on 3.10.11), Git, and VS Code.

**1. Get the code**
```
git clone <repo-url>
cd ParkWise
```
If the path has a space, put it in quotes: `cd "C:\Users\...\ParkWise"`.

**2. Create a virtual environment and install the libraries**
```
python -m venv venv
venv\Scripts\activate
pip install -r backend\requirements.txt
pip check
```
`pip check` must say `No broken requirements found`. If PowerShell blocks `activate`, run `Set-ExecutionPolicy -Scope Process Bypass` once and try again.

**3. Load the database.** If `mysql` is not recognised, run the first line (it lasts for that terminal only).
```
$env:Path += ";C:\Program Files\MySQL\MySQL Server 8.0\bin"
mysql -u root -p
```
At the `mysql>` prompt (the `source` command only works there, not in PowerShell):
```
SET GLOBAL event_scheduler = ON;
source schema.sql;
source seed.sql;
exit
```
`SET GLOBAL event_scheduler = ON;` lasts until MySQL restarts. For a permanent setting, add `event_scheduler=ON` under `[mysqld]` in `C:\ProgramData\MySQL\MySQL Server 8.0\my.ini` and restart the `MySQL80` service from an Administrator prompt.

**4. Configure and start the app**
```
cd backend
copy .env.example .env
notepad .env
python app.py
```
In `.env` set `PW_DB_PASSWORD` to your MySQL root password and `PW_SECRET_KEY` to any long random text. Never commit `.env`. Open http://127.0.0.1:5000.

**5. Log in.** `admin@parkwise.test` / `Admin@123` (admin) and `aarav@parkwise.test` / `Student@123` (student; the other demo students use the same password). These are demo credentials only.

**6. Optional demo traffic** (second terminal, venv active): `cd backend` then `python simulate.py --count 40 --delay 0.5`. If the event scheduler is off, the admin page has a button that runs the no-show, overstay and snapshot jobs by hand.

### Run the tests

The tests change data. **Reload `schema.sql` and `seed.sql` before each group** (a second run on dirty data reports false FAILs).

| Order | Command | Needs | Expected result |
|---|---|---|---|
| 1 | `source tests.sql;` at the `mysql>` prompt | database only | `PASS | 74` and an empty non-PASS list |
| 2 | `python tests_api.py` (project root) | app running | `RESULT: 37/37 passed` |
| 3 | `python tests_security.py` (right after 2, same database) | app running | `RESULT: 52/52 passed` |
| 4 | `python tests_concurrency.py --user root --password <pwd>` | database only | `RESULT: PASS` |

**Test status.** On 12 November 2026 `tests.sql` (74), `tests_api.py` (37) and `tests_security.py` (52) all passed on MariaDB 10.11, which is MySQL-compatible. Before the audit trigger for violations was added, `tests_api.py` and `tests_security.py` also passed in full on MySQL 8.0 on a Windows laptop. Run all four suites on your own MySQL 8.0 before the demo. If anything fails, copy the exact error text into the group chat.

### Common problems

| Problem | Fix |
|---|---|
| `mysql` is not recognised | Run the `$env:Path` line above, or add the MySQL `bin` folder to Windows PATH |
| `source` is not recognised | You are at the PowerShell prompt. Run `mysql -u root -p` first, then `source` at `mysql>` |
| `Unknown database 'parkwise'` | `schema.sql` did not load. Start `mysql` from the folder that contains it |
| `Access denied` when the app starts | Wrong `PW_DB_PASSWORD` in `backend/.env` |
| `Database error` in the app | MySQL is not running, or the schema is not loaded |
| Login says "Too many failed logins. Try again in N minute(s)." | Five wrong passwords lock that e-mail for 15 minutes. Restart the app to clear it |
| A page looks old after an update | Press Ctrl + F5 to reload without the browser cache |
| Charts are empty | Check that `frontend/static/chart.umd.js` exists (Chart.js is served from the project, no internet needed) |

## 2. What is in this repository

| Path | Purpose |
|---|---|
| `schema.sql` | Final schema: 12 tables, 3 functions, 12 procedures, 8 triggers, 9 views, 3 scheduled events |
| `seed.sql` | Reference data (4 zones, 24 slots, 3 tariffs, settings), 7 users, 14 vehicles, 30 days of synthetic history |
| `tests.sql` | 74 automated SQL checks (billing, entry/exit, reservations, scheduler jobs, constraints, audit) |
| `tests_api.py`, `tests_security.py` | 37 API checks and 52 security checks over real HTTP |
| `tests_concurrency.py` | Parallel double-booking and double-entry test |
| `backend/` | Flask app: `app.py`, `config.py`, `db.py`, `errors.py`, `auth.py`, `validate.py`, `ratelimit.py`, `routes/` (one file per API group), `simulate.py` (traffic simulator), `requirements.txt` |
| `frontend/static/` | `index.html`, `style.css`, `app.js` (plain JavaScript, no build step), `chart.umd.js` (Chart.js 4.4.1, MIT licence in `chart.LICENSE.txt`), `favicon.svg` |
| `docs/API.md` | Every endpoint with real requests and responses |
| `Architecture.md` | Layers, ER diagram, data dictionary, API contract, folder structure |
| `Workflow.md` | Business flows, state machines, team workflow, demo script (Part C) |
| `Decision.md` | Every design decision with reasons, limitations and open items |

## 3. Final feature list

**Core (must be 100% working)**

| # | Feature | Where it lives |
|---|---|---|
| F1 | Registration, login, roles (USER / ADMIN), vehicle registration (type, EV flag, accessibility permit) | Flask + `users`, `vehicles` |
| F2 | Live parking board by zone (Available / Occupied / Reserved / Maintenance) | `v_slot_live_status`, `v_zone_occupancy` |
| F3 | Reservations with overlap protection and cancellation | `sp_create_reservation`, `sp_cancel_reservation` |
| F4 | Vehicle entry / exit sessions (simulated by buttons) | `sp_vehicle_entry`, `sp_vehicle_exit` + triggers |
| F5 | Automatic billing (grace, hourly blocks, minimum charge, daily cap) | `fn_calc_amount`, `fn_billable_minutes` |
| F6 | Payments with simulated failure and retry | `sp_record_payment` |
| F7 | Admin: slots, maintenance, tariffs, users | Flask + `trg_slots_*`, `trg_tariff_au`, `trg_violations_au` |
| F8 | Violations log (overstay, no-show, wrong slot, unauthorized bay) | `violations`, `sp_log_violation` |
| F9 | Audit log of admin changes (who changed what, old and new values) | `audit_logs`, `@app_user_id` |
| F10 | Reports: daily revenue, hourly demand, unpaid bills, itemized bill | `v_daily_revenue`, `v_hourly_demand`, `v_unpaid_bills`, `v_itemized_bill` |

**Innovation (what makes it stand out)**

| # | Feature | Method |
|---|---|---|
| I1 | **Best-fit slot allocation with explanation.** Each recommended slot shows why it was chosen | Hard constraints in `WHERE`, then a weighted sum of min-max normalized factors (`sp_recommend_slots`). Weights live in `system_settings` and can be tuned. |
| I2 | **No-show and overstay automation** | Reservation state machine enforced by a trigger. MySQL `EVENT`s run `sp_release_no_shows` every minute and `sp_flag_overstays` every 5 minutes. |
| I3 | **Occupancy forecast** (expected busyness by weekday and hour) | `EVENT` snapshots every 15 min into `occupancy_snapshots`, then `v_occupancy_forecast`. This is a rule-based average, not machine learning. |
| I4 | **Concurrency-proof booking**, demoed live with two terminals | Row lock on the slot, locking reads, and UNIQUE keys on generated columns. See `tests_concurrency.py`. |
| I5 | Inclusive and green bays: accessible bays only for permit holders, EV charger bays only for EVs | Rules in `sp_assert_eligible` and the allocation `WHERE` clause |
| I6 | Transparent itemized bill (duration, grace, blocks, rate, cap, fines) | `v_itemized_bill` |
| I7 | Carbon-savings widget (small, clearly labelled estimate) | `v_carbon_estimate`. Assumptions are in Decision.md D-10. |

**Stretch (only after everything above is demo-ready):** ANPR from an uploaded plate photo (OpenCV + OCR, manual entry stays as fallback), QR code on the reservation, e-mail notifications.

## 4. Final schema at a glance

```
users ──< vehicles ──< reservations >── parking_slots >── zones
  │            │              │              │
  │            └──< parking_sessions >───────┘        tariff_rules ──< parking_sessions
  │                    │   (reservation_id, tariff_id)
  │                    ├──< payments
  │                    └──< violations (also linked to reservations)
  └──< audit_logs      occupancy_snapshots >── zones      system_settings (weights, grace, factors)
```

Full ER diagram and data dictionary: `Architecture.md` §4.

## 5. Team roles

`schema.sql` and `docs/API.md` are the contract between the roles. Change them only by group agreement and write the change in `Decision.md` in the same commit. Each person must be able to demo any flow and explain their own part.

| Role | Owns |
|---|---|
| Member 1: Database & Analytics | Schema, constraints, indexes, views, events, seed data, analytics endpoints, `tests.sql` |
| Member 2: Transactions & Backend | Stored procedures and functions, Flask skeleton, booking, entry, exit and payment endpoints, simulator |
| Member 3: Accounts, Admin & Rules | Login, roles, vehicles, admin pages, tariffs, violations, audit log, security hardening, `tests_security.py` |
| Member 4: User Interface & Delivery | `frontend/static/`, offline charts, UI polish, UI tests UI-09 to UI-25, report chapters, slides, demo rehearsals |

Names go in the report and slides (open decision in `Decision.md`).

## 6. Known limitations (say them before the examiner does)
- Payments are simulated; there is no real gateway.
- Entry and exit are triggered by buttons or the simulator; there are no sensors or cameras.
- The forecast is a historical average over synthetic demo data; it is not AI.
- The carbon figure is an estimate with documented assumptions (Decision.md D-10).
- Overstay detection only applies to reserved sessions, because a walk-in has no booked end time (Decision.md D-09).
- Login limit counts failures in memory per e-mail, so a restart clears it. There is no password reset, no HTTPS and no CSRF token (the Origin check and `SameSite=Lax` are used instead). See `Decision.md` D-19.

## 7. Demo

Follow `Workflow.md` Part C (about 10 minutes). Reload `schema.sql` and `seed.sql` before every rehearsal so the board starts clean.
