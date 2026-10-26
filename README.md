# ParkWise — Smart Parking Allocation & Predictive Management System

DBMS course project · MySQL 8 · Flask · HTML/CSS/JS · Single parking lot, multiple zones · Team of 3

## 1. What is in this package

| File | Purpose |
|---|---|
| `schema.sql` | Final schema: 12 tables, 3 functions, 12 procedures, 7 triggers, 9 views, 3 scheduled events |
| `seed.sql` | Reference data (4 zones, 24 slots, 3 tariffs, settings), 7 users, 14 vehicles, 30 days of synthetic history |
| `tests.sql` | 71 automated SQL checks (billing, entry/exit, reservations, scheduler jobs, constraints, audit) |
| `tests_concurrency.py` | Parallel double-booking / double-entry test |
| `Architecture.md` | Layers, ER diagram, data dictionary, API contract, folder structure |
| `Workflow.md` | Business flows, state machines, team workflow, demo script |
| `Decision.md` | Every design decision with reasons, limitations and open items |

**Test status.** Verified on MariaDB 10.11, the MySQL-compatible server available while this package was prepared, including a run with binary logging ON (MySQL 8's default). Results: `schema.sql` and `seed.sql` load with no errors, all 71 checks in `tests.sql` pass, `tests_concurrency.py` ends with `RESULT: PASS`, the `ev_release_no_shows` event fired by itself with the scheduler ON, the two-terminal demo in Workflow.md Part C behaves as described, and every demo login in §4 matches its password. It was **not** run on MySQL 8.0. The syntax is MySQL 8 syntax, but run `schema.sql`, `seed.sql`, `tests.sql` and `tests_concurrency.py` on your own MySQL 8 first. If anything fails, copy the exact error text into the group chat.

## 2. Final feature list

**Core (must be 100% working)**

| # | Feature | Where it lives |
|---|---|---|
| F1 | Registration, login, roles (USER / ADMIN), vehicle registration (type, EV flag, accessibility permit) | Flask + `users`, `vehicles` |
| F2 | Live parking board by zone (Available / Occupied / Reserved / Maintenance) | `v_slot_live_status`, `v_zone_occupancy` |
| F3 | Reservations with overlap protection and cancellation | `sp_create_reservation`, `sp_cancel_reservation` |
| F4 | Vehicle entry / exit sessions (simulated by buttons) | `sp_vehicle_entry`, `sp_vehicle_exit` + triggers |
| F5 | Automatic billing (grace, hourly blocks, minimum charge, daily cap) | `fn_calc_amount`, `fn_billable_minutes` |
| F6 | Payments with simulated failure and retry | `sp_record_payment` |
| F7 | Admin: slots, maintenance, tariffs, users | Flask + `trg_slots_*`, `trg_tariff_au` |
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

## 3. Final schema at a glance

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

## 4. Setup on Windows (MySQL 8 + VS Code)

1. Install MySQL Server 8.0 and MySQL Workbench. Install Python 3.11+ and VS Code.
2. Turn on the event scheduler. Workbench → `SET GLOBAL event_scheduler = ON;` (lasts until restart). For a permanent setting, add `event_scheduler=ON` under `[mysqld]` in `C:\ProgramData\MySQL\MySQL Server 8.0\my.ini` and restart the `MySQL80` service from an Administrator prompt.
3. Load the database. In Workbench use File → Open SQL Script, run `schema.sql`, then `seed.sql`. Or in a terminal: `mysql -u root -p`, then `source C:/path/to/schema.sql;` and `source C:/path/to/seed.sql;`. PowerShell does not support `<` redirection.
4. Run the tests: `source tests.sql;` should show `PASS | 71` and an empty "non-PASS" list. The tests change data, so reload `schema.sql` + `seed.sql` before every re-run (a second run on dirty data reports false FAILs). Then reload schema and seed again, and run `python tests_concurrency.py --user root --password <pwd>` (after `pip install mysql-connector-python`). It should end with `RESULT: PASS`.
5. Demo logins: `admin@parkwise.test` / `Admin@123`, and students such as `aarav@parkwise.test` / `Student@123`. These are demo credentials only.

## 5. Work split — 3 members

The split is by ownership of a vertical slice, so nobody waits on one person. The contract between slices is the **API table in Architecture.md §8** and the **schema**. Agree on both on day 1 and change them only by group decision.

| | **Member 1 — Data & Analytics** | **Member 2 — Transactions & Backend** | **Member 3 — Frontend & Delivery** |
|---|---|---|---|
| **Owns** | Schema, constraints, indexes, triggers, views, events, seed + history generator. All read-only analytics endpoints. | Stored procedures and functions (review, extend, own). Flask app skeleton, auth, all write-side endpoints, error mapping, traffic simulator. | All UI pages, Chart.js dashboards, UX, project report, PPT, demo rehearsal. |
| **Builds** | • Load, review and extend `schema.sql`/`seed.sql`<br>• Index benchmark with `EXPLAIN` (before/after)<br>• Analytics endpoints: revenue, hourly demand, forecast, carbon, summary<br>• Maintain `tests.sql` and `tests_concurrency.py`; add 10 more tests<br>• MySQL Workbench EER diagram + normalization proof (1NF → 3NF) | • Flask project (config, DB pool, blueprints)<br>• Register/login/logout, password hashing, role guard<br>• Endpoints: vehicles, slots, recommend, reserve, cancel, entry, exit, pay, admin CRUD, violations<br>• Map SQLSTATE 45000 messages to HTTP 409/400 JSON<br>• `SET @app_user_id` on every admin request<br>• `simulate.py`: random cars and bikes entering and leaving | • Pages: login/register, live board (zones, colours, auto-refresh), find-a-slot (shows score and reason), my reservations, entry/exit panel, bill and pay, admin (slots, tariffs, violations, audit), analytics<br>• Chart.js: revenue, hourly demand, forecast heat-map, zone occupancy<br>• 25 manual UI test cases + screenshots<br>• Report (structure in the course doc) and PPT<br>• Run two full demo rehearsals |
| **Viva topics** | ER diagram, normalization, constraints, triggers, indexes, views, events, forecast query | Procedures vs triggers vs functions, transactions, `FOR UPDATE`, isolation level, billing rule, scoring algorithm, double-booking proof | End-to-end flow, why the DB is the "brain", dashboards and their SQL source, limitations |
| **Effort (est.)** | ~30 h | ~32 h | ~32 h |

**Rules that keep the load equal**
- Each member reviews one other member's work (1 → 2 → 3 → 1) before every merge to `main`.
- Each member must be able to demo any flow and explain one procedure, one trigger, one view and one chart. Examiners ask each person different questions.
- The core SQL is already written and tested here, so Members 1 and 2 spend their time on understanding, extending, integrating and breaking it. Member 3 has the largest amount of new code, which is why Member 1 also takes the report's database chapters and Member 2 builds the simulator that powers the live demo.

**Suggested schedule (adjust to your deadline)**

| Week | Milestone |
|---|---|
| 1 | Everyone loads the DB and runs the tests. API contract frozen. Flask skeleton + auth. UI shell and live board using `/api/slots`. |
| 2 | Reserve, entry, exit, pay working end to end (API + UI). Analytics endpoints. Charts. |
| 3 | Innovations (recommendation UI, no-show / overstay demo, forecast page). Admin pages. Simulator. Fix bugs found by the tests. |
| 4 | Freeze features. Report, PPT, rehearsals. Only bug fixes after this point. |

## 6. Known limitations (say them before the examiner does)
- Payments are simulated; there is no real gateway.
- Entry and exit are triggered by buttons or the simulator; there are no sensors or cameras.
- The forecast is a historical average over synthetic demo data; it is not AI.
- The carbon figure is an estimate with documented assumptions (Decision.md D-10).
- Overstay detection only applies to reserved sessions, because a walk-in has no booked end time (Decision.md D-09).

## 7. Running the web app (backend + frontend)

From the `parkwise` folder, after `schema.sql` and `seed.sql` are loaded (section 4):

```
cd backend
copy .env.example .env          (then edit .env: set PW_DB_PASSWORD to your MySQL root password)
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 in the browser. Logins: `admin@parkwise.test` / `Admin@123`, `aarav@parkwise.test` / `Student@123`.
Dashboards use Chart.js from a CDN, so the analytics page needs internet.

Demo traffic: in a second terminal, `cd backend` then `python simulate.py --count 40 --delay 0.5`.
If the event scheduler is off, the admin page has a button that runs the no-show / overstay / snapshot jobs by hand.

| Folder / file | What it does |
|---|---|
| `backend/app.py`, `config.py`, `db.py`, `errors.py`, `auth.py` | Flask app, settings, DB pool, error mapping (SQLSTATE 45000 -> HTTP 409), login and roles |
| `backend/routes/` | One file per API group, as in Architecture.md section 8 (`analytics.py` is Member 1's) |
| `backend/simulate.py` | Traffic simulator for the demo |
| `frontend/static/` | `index.html`, `style.css`, `app.js` (plain JavaScript, no build step) |
