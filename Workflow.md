# ParkWise — Workflow

Part A covers how the system behaves. Part B covers how the team builds it. Part C is the demo script.

# Part A — System workflows

## A1. Actors
- **User** — registers vehicles, finds and reserves slots, parks, pays.
- **Admin** — manages slots, tariffs and violations; reads analytics.
- **Scheduler** — MySQL events (no-show, overstay, snapshots).
- **Simulator** — `simulate.py` stands in for gates and sensors.

## A2. Reserve a slot (F3, I1)

```
User            Browser             Flask                    MySQL
 |  pick vehicle,  |                   |                         |
 |  start, end --->|  GET /recommend   |                         |
 |                 |------------------>| CALL sp_recommend_slots |
 |                 |                   |------------------------>| filter + score
 |  top 5 slots    |<------------------|<------------------------| (score + reason)
 |  with reasons   |                   |                         |
 |  choose one --->| POST /reservations|                         |
 |                 |------------------>| CALL sp_create_reservation
 |                 |                   |------------------------>| lock slot row
 |                 |                   |                         | check owner, eligibility,
 |                 |                   |                         | overlaps, then INSERT, COMMIT
 |  "Booked" or    |<------------------|<------------------------| or SIGNAL "Slot already booked"
 |  409 message    |                   |                         |
```

Rules enforced in MySQL:
- End must be after start. The start cannot be in the past (1 minute of tolerance). The maximum length is 24 hours.
- The vehicle must belong to the user.
- The vehicle type must match the slot type. Accessible bays require a permit. EV charger bays require an EV.
- No overlap with another PENDING/ACTIVE reservation on that slot, or for that vehicle.
- If the booking starts within the walk-in buffer (60 min) the slot must not currently hold a parked vehicle.

## A3. Vehicle entry (F4)

```
Simulate "entry" -> POST /sessions/entry {vehicle_id, slot_id}
  -> sp_vehicle_entry
       1. lock slot row; refuse if OCCUPIED / MAINTENANCE / type mismatch / bay rules
       2. does this vehicle hold a PENDING reservation for THIS slot covering now
          (allowed from 15 min before start until the end)?
            YES -> link it to the new session
            NO  -> walk-in: refuse if another vehicle's booking starts within 60 min,
                   or if this vehicle has a booking for a different slot right now
       3. pick the tariff for (vehicle type, premium slot) effective today; freeze it in the session
       4. INSERT session (ACTIVE)   -> trigger sets slot OCCUPIED
       5. reservation (if any) PENDING -> ACTIVE
```

If the slot or the vehicle already has an open session, the UNIQUE keys reject the insert even if the app has a bug.

## A4. Vehicle exit, bill and payment (F5, F6)

```
Simulate "exit" -> POST /sessions/<id>/exit
  -> sp_vehicle_exit
       1. lock session row; must be ACTIVE; exit_time >= entry_time
       2. duration = whole minutes (TIMESTAMPDIFF MINUTE)
       3. amount  = fn_calc_amount(tariff, duration)
       4. UPDATE session -> CLOSED, store duration / billable minutes / amount   -> trigger frees the slot
       5. INSERT payment: PENDING (or PAID/WAIVED if amount = 0)
       6. if reserved: reservation -> COMPLETED
          overstay = minutes past booked end minus grace; if > 0 insert OVERSTAY violation with fine
       7. COMMIT (everything or nothing)

POST /payments -> sp_record_payment(session, method, success)
       success=1: PENDING -> PAID, paid_at = now
       success=0: PENDING -> FAILED, and a new PENDING row is created (retry)
```

**Billing rule (single source of truth: `fn_calc_amount`)**

```
if duration <= grace                        -> 0
else amount = max( CEIL((duration - grace)/60) * hourly_rate , min_charge )
     amount = min( amount , daily_cap * CEIL(duration/1440) )
```

Worked examples with the car standard tariff (Rs 30/h, grace 10, min 30, cap 200):

| Duration | Billable | Blocks | Amount |
|---|---|---|---|
| 10 min | 0 | 0 | Rs 0 (inside grace) |
| 11 min | 1 | 1 | Rs 30 |
| 71 min | 61 | 2 | Rs 60 |
| 145 min (10:00 → 12:25) | 135 | 3 | **Rs 90** |
| 2000 min | 1990 | 34 | capped: 200 × 2 days = Rs 400 |

## A5. No-show (I2)

```
every 1 min:  sp_release_no_shows
   PENDING reservations with  start_time + 15 min < NOW()   -> status NO_SHOW
   + one NO_SHOW violation row per reservation (fine from system_settings)
Slot is bookable by others again immediately (NO_SHOW does not block overlap checks).
```

## A6. Overstay (I2)

```
every 5 min:  sp_flag_overstays
   ACTIVE sessions linked to a reservation where  booked_end + tariff grace < NOW()
   -> one OVERSTAY violation (running fine)
at exit:      sp_vehicle_exit recomputes the final fine and overwrites it
```

## A7. State machines

```
RESERVATION                                             SESSION
                    +--> ACTIVE ----> COMPLETED            ACTIVE ----> CLOSED
PENDING ------------+                                        (exit)
   |                +--> NO_SHOW   (scheduler)
   +----------------+--> CANCELLED (user)
All other jumps are rejected by trigger trg_reservations_bu.

PAYMENT                                                 SLOT (physical status)
PENDING --> PAID                                        AVAILABLE <--> OCCUPIED   (set by session triggers only)
   |                                                    AVAILABLE <--> MAINTENANCE (admin; refused if a vehicle is inside)
   +--> FAILED  (a new PENDING row is created)          Board shows RESERVED when a PENDING booking starts within
PAID --> REFUNDED (admin, optional)                     30 min or is in progress (derived in v_slot_live_status)
```

## A8. Admin workflow
1. Slot maintenance: `PUT /admin/slots/<id>/status` → trigger refuses while a vehicle is inside, and writes an audit row.
2. Tariff change: `PUT /admin/tariffs` → old and new values go to `audit_logs`. Past bills do not change because sessions keep their own `tariff_id`.
3. Violations: scheduler rows appear automatically; the admin can log wrong-slot / unauthorized-bay cases (`sp_log_violation`) and mark fines PAID or WAIVED.
4. Analytics: revenue per day, entries per hour, forecast per weekday × hour, unpaid bills.

---

# Part B — Team workflow

## B1. Roles
See README §5. In short: **M1** data and analytics, **M2** transactions and backend, **M3** frontend and delivery.

## B2. Git rules
- Branches: `main` (always demo-able) and `feat/<m1|m2|m3>-<topic>`.
- Every merge into `main` needs a review from the next member (M1 → M2 → M3 → M1).
- Commit messages: `area: what changed`, e.g. `db: add index for active sessions`.
- Never commit passwords. Put DB credentials in `config.py` read from environment variables, and commit `config.example.py`.

## B3. Change control (prevents "frontend expects another schema")
1. `schema.sql` and the API table in Architecture.md §8 are the contract.
2. To change either: post the change in the group chat, update the file and Decision.md in the same commit, and ping the other two members.
3. After a schema change everyone reloads `schema.sql` + `seed.sql` (they re-create the DB) and reruns `tests.sql`.

## B4. Definition of done (per feature)
- Works on a freshly loaded DB (schema + seed).
- Has at least one automated or written test (SQL test, API test, or UI test case).
- The error path shows a clear message in the UI, not a stack trace.
- Reviewed by another member.

## B5. Schedule and checkpoints
| Week | M1 | M2 | M3 | Checkpoint (all three) |
|---|---|---|---|---|
| 1 | Load DB, run tests, own the EER diagram | Flask skeleton, auth, `/slots`, `/vehicles` | UI shell, live board | Everyone can log in and see the board |
| 2 | Analytics endpoints, index benchmark | Reserve / entry / exit / pay endpoints | Reservation, entry-exit, bill pages | One full cycle reserve → enter → exit → pay in the UI |
| 3 | More tests, forecast and carbon endpoints | Admin endpoints, simulator, error mapping | Recommendation page, admin pages, charts | Scheduler demo (no-show, overstay) works |
| 4 | Normalization + DB chapters | Bug fixes, viva prep | Report, PPT, screenshots | Two full demo rehearsals, then feature freeze |

Hold a 10-minute stand-up on each working day: what is done, what is blocked, what changes the contract.

---

# Part C — Demo script (about 10 minutes)

Prepare first: freshly loaded DB, event scheduler ON, Flask running, simulator ready, two Workbench query tabs open.

1. **Login** as a student. Register a car (EV flag off).
2. **Live board**: show zones and the colours.
3. **Find a slot** for 2 hours from now. Show the top slots with the score and the reason text. Then switch to an EV car and show that a charger bay now wins.
4. **Reserve** the top slot. Show the new row in `reservations` with `alloc_score`.
5. **Two-terminal concurrency demo** (in Workbench, within 50 seconds because of the lock wait timeout):
   - Tab A: `START TRANSACTION; SELECT slot_id FROM parking_slots WHERE slot_id = 5 FOR UPDATE;`
   - Tab B: `SET @s = NOW() + INTERVAL 3 HOUR; CALL sp_create_reservation(5, 7, 5, @s, @s + INTERVAL 1 HOUR, NULL, NULL, @r);` (it waits)
   - Tab A: `SET @s = NOW() + INTERVAL 3 HOUR; INSERT INTO reservations (user_id, vehicle_id, slot_id, start_time, end_time) VALUES (2, 1, 5, @s, @s + INTERVAL 1 HOUR); COMMIT;`
   - Tab B now fails with `Slot already booked for that period`. Explain the row lock.
   - Optional: run `python tests_concurrency.py` for the automated version (needs a fresh DB).
6. **Entry** of the reserved vehicle: session appears, the slot turns OCCUPIED (trigger).
7. **Exit**: show the itemized bill (duration, grace, blocks, rate, amount). Pay once with a simulated failure, then success.
8. **Admin**: let a reservation lapse (or `CALL sp_release_no_shows();`) and show NO_SHOW + violation. Show an overstay violation. Show the audit log after changing a tariff.
9. **Analytics**: revenue per day, hourly demand, forecast heat-map ("Tuesday 10:00 → VERY BUSY"). Say clearly that it is rule-based over synthetic history.
10. **Close** with the limitations list (README §6).

**Viva prep checklist:** ER diagram; 3NF reasoning and the deliberate denormalization; trigger vs procedure vs function (one example each from this project); why `FOR UPDATE` and not only a UNIQUE constraint; why a locking read is used for the overlap check; the billing rule with the 145-minute example; why the tariff is frozen in the session; what the indexes are for (`EXPLAIN` before/after); what the forecast is and is not.
