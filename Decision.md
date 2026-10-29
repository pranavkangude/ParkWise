# ParkWise — Decision Log

Format: **Decision → Why → Alternatives rejected → Consequence / limit.** Change a decision only by group agreement, and edit this file in the same commit.

## D-01 Single parking lot with multiple zones
- **Why:** the group chose it. It removes a `parking_lots` table and a foreign key from nearly every query. Zones (A–D) still give ER depth and zone analytics.
- **Rejected:** multi-lot support (more joins, little extra DBMS learning).
- **Consequence:** adding a lot later means adding `parking_lots` and `zones.lot_id`.

## D-02 Software-first; no hardware; ANPR is a stretch only
- **Why:** marks come from the database design. OCR on number plates is unreliable and a failed live read hurts the demo. Entry and exit are triggered by buttons and by `simulate.py`.
- **Rejected:** mandatory camera / ESP32 / RFID.
- **Consequence:** if time remains, add ANPR as "upload a plate photo → plate string → same `/sessions/entry` API". The DB does not change. Manual entry stays as the fallback.

## D-03 Business rules live in MySQL, Flask stays thin
- **Why:** this is a DBMS course, and rules in the database hold no matter which client calls them (including raw SQL in the viva).
- **Rejected:** billing and allocation in Python.
- **Consequence:** Flask routes are short. Changing a rule means changing SQL and rerunning `tests.sql`.

## D-04 Allocation = hard constraints + weighted sum
- **Why:** it is explainable. The user sees the score and the reason. Hard constraints (type, accessible, EV, free in window) go in `WHERE`, so an ineligible slot can never be recommended. The rest is scored.
- **Details:** each factor is min-max normalized to 0..1 so that metres do not outweigh the other factors. Weights sit in `system_settings`: distance 0.30, EV 0.35, accessible 0.25, cost 0.10 (sum = 1.00; `tests.sql` checks this).
- **Tuning note:** the EV weight is deliberately higher than the distance weight so an EV driver is offered a charger bay even if a plain bay is closer (tested: B-01 0.7807 vs A-03 0.6500). For non-EV drivers the EV factor is 1 for every candidate, so it changes nothing.
- **Rejected:** ML ranking (no data, hard to explain), first-free-slot (not innovative).
- **Limit:** the recommendation is advice; the booking procedure re-checks everything under a lock.

## D-05 Double-booking: lock the slot row + locking reads (not only constraints)
- **Why:** MySQL has no exclusion constraint for overlapping time ranges, so a UNIQUE key cannot stop two overlapping reservations. `sp_create_reservation` locks the slot row first, then checks overlaps with `SELECT ... FOR UPDATE`. Locking reads see the latest committed data even under REPEATABLE READ.
- **Plus:** UNIQUE keys on the generated columns `active_slot_key` / `active_vehicle_key` guarantee at most one open session per slot and per vehicle (MySQL allows many NULLs in a UNIQUE index, and the key is NULL once a session closes).
- **Evidence:** `tests_concurrency.py` (20 rounds × 5 simultaneous bookings gave exactly one winner per round and 0 overlapping pairs; 3 rounds × 5 simultaneous entries gave exactly one winner per slot).
- **Limit:** the lock wait timeout (default 50 s) applies; Flask should return a clear message if it is hit.

## D-06 Reservation state machine enforced by a trigger
- **States:** PENDING → ACTIVE | NO_SHOW | CANCELLED; ACTIVE → COMPLETED. Everything else is rejected by `trg_reservations_bu`.
- **Why:** an invalid jump (NO_SHOW → ACTIVE) must be impossible even from raw SQL.

## D-07 Slot status is physical; "RESERVED" is derived
- **Why:** a stored RESERVED flag would go stale (a booking for 6 pm should not block the board at noon) and would need a scheduler to clean up. `parking_slots.status` is only AVAILABLE / OCCUPIED / MAINTENANCE, maintained by session triggers. The view `v_slot_live_status` shows RESERVED when a PENDING booking starts within 30 min (`reserve_hold_minutes`) or is in progress.
- **Consequence:** the course doc's four slot states are all shown on the board, but only three are stored.

## D-08 Billing rule
- **Rule:** duration in whole minutes (floor); if duration ≤ grace the stay is free; otherwise `CEIL((duration − grace)/60) × rate`, raised to `min_charge`, limited to `daily_cap × CEIL(duration/1440)`. Example: 145 min → 135 billable → 3 blocks → Rs 90 (matches the course doc).
- **Frozen tariff:** `tariff_id` is chosen at entry and stored. Editing a tariff later never changes a running or past bill.
- **Fines are separate:** overstay / no-show fines are stored in `violations` (status OPEN / PAID / WAIVED set by the admin). They are shown beside the bill in `v_itemized_bill` but are not collected through `payments` in v1.
- **Stored results:** duration, billable minutes and amount are stored at exit (deliberate denormalization: a bill is a historical fact).
- **Rejected:** computing the amount in JavaScript or Flask.

## D-09 Overstay applies only to reserved sessions; walk-in policy
- **Why:** an overstay needs a booked end time, and walk-ins do not have one. Walk-ins are limited by the daily cap only.
- **Walk-in guard:** a walk-in is refused on a slot whose reservation starts within 60 min (`walkin_buffer_minutes`).
- **Known limit:** a walk-in who stays much longer than 60 min can still block the next booking. That entry will be refused with "Slot is occupied" and an admin has to resolve it. We document this instead of hiding it.

## D-10 Carbon widget is a small, labelled estimate
- **Method:** metres saved = (average distance of all slots of the same type) − (distance of the slot used), never below 0. CO₂ saved = km × `emission_g_per_km`.
- **Assumptions to state in the report:** the baseline is "a driver who takes a random slot of the same type"; distances are straight-line metres from the entrance as entered in `seed.sql`; one trip.
- **Open item:** `emission_g_per_km = 120` is a **placeholder**. Replace it with a figure you cite (name the source and year) before you submit.
- **Limit:** inside one lot the savings are tiny (grams). Present it as a minor widget, not a headline claim.

## D-11 Forecast is rule-based, not AI
- **Method:** `occupancy_snapshots` (per zone, every 15 min) → average occupancy by weekday and hour → label EASY (<60 %), BUSY (≥60 %), VERY BUSY (≥85 %).
- **Data:** `sp_seed_history(30)` creates 30 days of synthetic history with a morning peak. Say this in the demo. Remove or regenerate the history before a real deployment.
- **Rejected:** ML forecasting (not enough real data; hard to defend in a DBMS viva).

## D-12 Scheduler = MySQL EVENTs (not a Python scheduler)
- **Why:** the logic stays in the database, and there is no extra process to forget at demo time.
- **Requirement:** `event_scheduler` must be ON (README §4). `SET GLOBAL` lasts until the server restarts; `my.ini` makes it permanent.
- **Fallback:** all three jobs are plain procedures. If events are off, run `CALL sp_release_no_shows();` etc. by hand or from an admin "Run jobs now" button.
- **Safety:** jobs are idempotent (UNIQUE keys + `NOT EXISTS`).

## D-13 Time-injection parameters exist for tests only
- `sp_vehicle_entry(..., p_entry_time, ...)`, `sp_vehicle_exit(..., p_exit_time, ...)` accept a time so tests can create a 145-minute stay without waiting.
- **Rule:** Flask must always pass `NULL` (= `NOW()`). A user-supplied time would let a user choose their own bill.
- **Consequence:** code review checks this on every route.

## D-14 One time zone
- All timestamps are `DATETIME` in the DB server's local time (`NOW()`); no per-row zone conversion.
- **Rule:** DB server and Flask run on the same machine/zone for the demo. If they ever differ, set `time_zone = '+05:30'` in `my.ini`.

## D-15 Authentication and payments
- Passwords: werkzeug scrypt hashes. Roles: USER / ADMIN checked in Flask on every route.
- Payments are simulated (`sp_record_payment`, success or failure flag). No gateway, no card data.
- Demo logins are in `seed.sql` and must not be reused anywhere else.

## D-16 Audit trail
- Triggers write to `audit_logs` for tariff changes and slot maintenance toggles, with old and new values as JSON.
- The actor comes from the session variable `@app_user_id`, which Flask sets on admin requests. If it is unset the actor is NULL.

## D-17 Out of scope (v1)
Multi-lot, real payment gateway, sensors / gates / cameras, machine learning, mobile app, e-mail / SMS notifications, refunds workflow.

## D-18 Testing approach
- `tests.sql`: 71 checks. Billing edge cases, entry/exit cycle, eligibility, reservations and cancellations, state machine, scheduler jobs and idempotence, guards, constraints, audit, views.
- `tests_concurrency.py`: parallel double-booking and double-entry.
- The recommendation output is checked by eye (expected top slots are listed in `tests.sql`), because a procedure result set cannot be asserted in plain SQL.
- **Environment note:** all of the above passed on MariaDB 10.11 (the MySQL-compatible server available while writing this), also with binary logging ON, which is MySQL 8's default and enforces the function-characteristic and generated-column rules. It was not run on MySQL 8.0 itself, so run it there before relying on it.
- **Re-run rule:** `tests.sql` changes data. Reload `schema.sql` + `seed.sql` before each run.

## D-19 Security hardening (Member 3)
- **Failed logins:** 5 wrong passwords per e-mail within 15 minutes lock that e-mail for the rest of the window (HTTP 429 with `Retry-After`). A success clears the count. Unknown e-mails count too, so the answer never reveals who has an account. The limits are `PW_LOGIN_MAX_FAILS` and `PW_LOGIN_WINDOW_MIN` in `.env`.
- **Limit of the limiter:** the counter lives in the Flask process (restart clears it) and is per e-mail, not per IP. Someone who knows an e-mail can lock that account for 15 minutes. Accepted for a single-process course project. A production system would keep the counter in the database or Redis and add per-IP limits.
- **Input limits:** every text and number input is checked in `backend/validate.py` (types, lengths, ranges); body size is capped at 64 KB. Wrong types give 400 instead of a 500 crash.
- **Admin guard:** `@admin_required` marks the function. `app.py` refuses to start if any `/api/admin/*` or `/api/analytics/*` route lacks the mark, and `tests_security.py` repeats the check.
- **CSRF:** `SameSite=Lax` stays, and we add an `Origin` check on POST, PUT and DELETE. A browser always sends `Origin` on those methods, so a request from another site is refused (403). Why this is enough here: the cookie is `HttpOnly` and `Lax`, so browsers do not send it on cross-site POSTs, and the Origin check covers same-site cases such as another port on localhost. Why not a token: it would force a change to every client, including `tests_api.py`, `simulate.py` and the Postman collection. Limit: a client that sends no `Origin` (curl, Postman) is allowed, which is fine because those are not browsers carrying a victim's cookie.
- **Other:** `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, and `Cache-Control: no-store` on every `/api` answer (so the Back button after logout does not show private data). Deadlock and lock-timeout errors now give a readable message (409 and 503).

## D-20 Allocation score is computed by the server
- `POST /reservations` used to store the `alloc_score` and `alloc_reason` sent by the browser, so a user could write any score into the table.
- Now Flask ignores both fields, calls `sp_recommend_slots` for the same vehicle and window, and stores the score and reason of the chosen slot. If the slot is not among the top 5, both stay NULL. The request fields are still accepted so old clients do not break.

## D-21 Vehicle edit and delete rules
- **Edit:** type, EV flag and permit decide which slots a vehicle may use, so they cannot change while it has an ACTIVE session or a PENDING/ACTIVE reservation (409). The check is inside the UPDATE statement itself, which leaves no gap for a race. The plate can always be corrected.
- **Delete:** only a vehicle with no reservations (any status), sessions or violations. Bills and fines are history and must stay. The foreign-key error 1451 is also mapped to 409 as a safety net.

## D-22 Settling violations, and where this audit row comes from
- `PUT /admin/violations/<id>/status` moves OPEN to PAID or WAIVED, one way only. The `UPDATE ... WHERE status='OPEN'` makes a second attempt a clean 409.
- **Audit:** Flask writes the `VIOLATION_RESOLVE` row in the same transaction as the update (`db.transaction()`), because there is no audit trigger on `violations`. This is a small exception to D-16 (audit by triggers). **Proposal for the group:** add `trg_violations_au` to `schema.sql` so the audit also holds for raw SQL. We did not do it here because it changes the schema contract and needs the group to agree and reload the database.

## D-23 Saving a tariff with the same values
- MySQL reports 0 changed rows for an identical UPDATE, which used to look like "not found" (404). Flask now reads the tariff first: unknown id is 404, identical values are 200 with `"changed": false`, and nothing is written (so no empty audit row either).
- Tariff numbers are validated: rate 0.01 to 9999, grace 0 to 1440 whole minutes, charges 0 to 9999, cap 0 to 99999 and not below the minimum charge.

## Open items for the group
1. Pick and cite the CO₂ emission factor (D-10).
2. Confirm tariff values (`seed.sql`), or keep the demo values (car Rs 30/h, premium Rs 50/h, bike Rs 10/h).
3. Confirm the real lot layout and distances if you want the demo to mirror your college.
4. Decide whether ANPR stays a stretch goal (D-02).
5. Agree the final API field names (Architecture.md §8) before Week 1 ends.
