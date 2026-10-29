# ParkWise API Reference

All endpoints live under `/api` on the Flask app (default `http://127.0.0.1:5000`). Every example below is a **real request and response** captured from the running app against the seeded database.

## Conventions

- **Format:** JSON in, JSON out. Send `Content-Type: application/json` for bodies.
- **Login:** `POST /api/auth/login` sets a session cookie. Send it back on later requests (browsers and Postman do this automatically).
- **Roles:** `USER` and `ADMIN`. Users can only touch their own vehicles, reservations, sessions and bills.
- **Times:** send `YYYY-MM-DDTHH:MM` (for example `2026-10-30T14:30`). Responses use `YYYY-MM-DD HH:MM:SS`. One time zone is used everywhere (Decision D-14).
- **Money:** plain numbers in rupees (`90.0`).
- **Where the rules live:** in MySQL (procedures, triggers, constraints). Flask validates input, checks who you are, calls the database and maps errors.
- **Input limits:** `full_name` 100 characters, `email` 120, `phone` 10 to 15 digits, `password` 6 to 128, `reg_number` 4 to 15 letters or digits, `notes` 255. A request body larger than 64 KB gets 413. Wrong types (for example a number where text is expected) give 400, never a crash.
- **Cross-site writes:** a browser always sends an `Origin` header on POST, PUT and DELETE. If it names a different site the request is refused with 403 (Decision D-19). Scripts such as Postman and `requests` send no `Origin` and are not affected.
- **Time parameters:** the entry and exit procedures can accept a time, but Flask always passes `NULL`, so the database clock is used (Decision D-13).

## Error format and status codes

Every error looks like this:
```json
{
  "error": "Slot already booked for that period"
}
```

| Code | Meaning | Typical cause |
|---|---|---|
| 400 | Bad request | Missing or invalid input, or a CHECK / NOT NULL / foreign-key failure |
| 401 | Not logged in | No session, or wrong password |
| 403 | Forbidden | Not an admin, or not your vehicle / session |
| 404 | Not found | Unknown id, or no bill yet |
| 413 | Body too large | Request body over 64 KB |
| 409 | Conflict | A **database rule** refused the action (SQLSTATE 45000 from a procedure or trigger), or a duplicate (MySQL error 1062) |
| 429 | Too many failed logins | 5 wrong passwords for one e-mail within 15 minutes; the `Retry-After` header gives the seconds to wait |
| 500 | Server error | Unexpected database error; details are in the server log only |
| 503 | Busy | The database lock wait timed out (Decision D-05); try again |

The mapping is done in `backend/errors.py`. The message in a 409 is the text of the `SIGNAL` in the stored procedure, so it is the same text you see in the mysql client.

## Endpoint index

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | Anyone (no login) | Register |
| POST | `/api/auth/login` | Anyone (no login) | Log in |
| POST | `/api/auth/logout` | Anyone (no login) | Log out |
| GET | `/api/me` | Logged-in user | Current user |
| GET | `/api/slots` | Anyone (no login) | All slots with live status |
| GET | `/api/zones/occupancy` | Anyone (no login) | Occupancy per zone |
| GET | `/api/vehicles` | Logged-in user | List vehicles |
| POST | `/api/vehicles` | Logged-in user | Add a vehicle |
| PUT | `/api/vehicles/{id}` | Logged-in user | Edit a vehicle (own; admin: any) |
| DELETE | `/api/vehicles/{id}` | Logged-in user | Delete a vehicle with no history |
| GET | `/api/recommend` | Logged-in user | Recommend slots |
| POST | `/api/reservations` | Logged-in user | Create a reservation |
| GET | `/api/reservations` | Logged-in user | List reservations |
| DELETE | `/api/reservations/{id}` | Logged-in user | Cancel a reservation |
| POST | `/api/sessions/entry` | Logged-in user | Vehicle entry |
| POST | `/api/sessions/{id}/exit` | Logged-in user | Vehicle exit |
| GET | `/api/sessions/active` | Logged-in user | Vehicles inside now |
| GET | `/api/bills/unpaid` | Logged-in user | Unpaid bills |
| GET | `/api/bills/{id}` | Logged-in user | Itemized bill |
| POST | `/api/payments` | Logged-in user | Pay a bill (simulated) |
| GET | `/api/admin/tariffs` | Admin only | List tariffs |
| PUT | `/api/admin/tariffs` | Admin only | Update a tariff |
| PUT | `/api/admin/slots/{id}/status` | Admin only | Set slot maintenance or available |
| GET | `/api/admin/users` | Admin only | List user accounts |
| GET | `/api/admin/violations` | Admin only | List violations |
| POST | `/api/admin/violations` | Admin only | Log a violation |
| PUT | `/api/admin/violations/{id}/status` | Admin only | Mark a violation PAID or WAIVED |
| GET | `/api/admin/audit` | Admin only | Audit log |
| POST | `/api/admin/run-jobs` | Admin only | Run the scheduled jobs now |
| GET | `/api/analytics/summary` | Admin only | Summary tiles |
| GET | `/api/analytics/revenue` | Admin only | Daily revenue |
| GET | `/api/analytics/hourly-demand` | Admin only | Entries by hour of day |
| GET | `/api/analytics/forecast` | Admin only | Occupancy forecast |
| GET | `/api/analytics/carbon` | Admin only | Carbon-savings estimate |

## 1. Accounts

### Register: `POST /api/auth/register`

- **Who:** Anyone (no login)
- **Uses:** INSERT into `users`

Creates a normal user account. The password is stored hashed (never in plain text).

| Input | Rules |
|---|---|
| `full_name` | required, at most 100 characters |
| `email` | required, must look like an email, at most 120 characters, unique |
| `password` | required, 6 to 128 characters |
| `phone` | optional, 10 to 15 digits |

**Success example**

`POST /api/auth/register`

Request body:
```json
{
  "full_name": "Demo Student",
  "email": "demo2618@example.com",
  "phone": "9876543210",
  "password": "secret1"
}
```

Response `201`:
```json
{
  "message": "Registered. You can log in now.",
  "user_id": 8
}
```

**Error example**

`POST /api/auth/register`

Request body:
```json
{
  "full_name": "Demo Student",
  "email": "demo2618@example.com",
  "password": "secret1"
}
```

Response `409`:
```json
{
  "error": "This email is already registered."
}
```

| Status | Meaning |
|---|---|
| 400 | Missing or invalid field |
| 409 | Email already registered |

### Log in: `POST /api/auth/login`

- **Who:** Anyone (no login)
- **Uses:** SELECT on `users`

Checks the password and starts a session. The browser keeps the session cookie automatically. After 5 wrong passwords for the same e-mail within 15 minutes, further logins for that e-mail get 429 (even with the right password) until the oldest failure is 15 minutes old. A successful login clears the count.

| Input | Rules |
|---|---|
| `email` | required |
| `password` | required |

**Success example**

`POST /api/auth/login`

Request body:
```json
{
  "email": "aarav@parkwise.test",
  "password": "Student@123"
}
```

Response `200`:
```json
{
  "email": "aarav@parkwise.test",
  "full_name": "Aarav Patil",
  "role": "USER",
  "user_id": 2
}
```

**Error example**

`POST /api/auth/login`

Request body:
```json
{
  "email": "aarav@parkwise.test",
  "password": "wrong"
}
```

Response `401`:
```json
{
  "error": "Wrong email or password."
}
```

| Status | Meaning |
|---|---|
| 401 | Wrong email or password |
| 429 | Too many failed logins (see `Retry-After`) |

### Log out: `POST /api/auth/logout`

- **Who:** Anyone (no login)
- **Uses:** none

Clears the session.

| Status | Meaning |
|---|---|
| 200 | Always succeeds |

### Current user: `GET /api/me`

- **Who:** Logged-in user
- **Uses:** SELECT on `users`

Returns the logged-in user's profile.

**Success example**

`GET /api/me`

Response `200`:
```json
{
  "email": "aarav@parkwise.test",
  "full_name": "Aarav Patil",
  "phone": "9000000001",
  "role": "USER",
  "user_id": 2
}
```

**Error example**

`GET /api/me`

Response `401`:
```json
{
  "error": "Not logged in."
}
```

| Status | Meaning |
|---|---|
| 401 | Not logged in |


## 2. Live board (public)

### All slots with live status: `GET /api/slots`

- **Who:** Anyone (no login)
- **Uses:** view `v_slot_live_status`

One row per slot. `live_status` is AVAILABLE, OCCUPIED, RESERVED or MAINTENANCE. RESERVED is **derived** in the view, not stored.

**Success example**

`GET /api/slots`

Response `200`:
```json
[
  {
    "distance_to_entrance_m": 5,
    "is_accessible": 1,
    "is_ev_charger": 0,
    "is_premium": 0,
    "live_status": "AVAILABLE",
    "physical_status": "AVAILABLE",
    "slot_code": "A-01",
    "slot_id": 1,
    "slot_type": "CAR",
    "zone_code": "A",
    "zone_id": 1,
    "zone_name": "Ground - Entrance Row"
  },
  {
    "distance_to_entrance_m": 8,
    "is_accessible": 1,
    "is_ev_charger": 0,
    "is_premium": 0,
    "live_status": "AVAILABLE",
    "physical_status": "AVAILABLE",
    "slot_code": "A-02",
    "slot_id": 2,
    "slot_type": "CAR",
    "zone_code": "A",
    "zone_id": 1,
    "zone_name": "Ground - Entrance Row"
  }
]
```
*(list shortened: first 2 of 24 items shown)*

### Occupancy per zone: `GET /api/zones/occupancy`

- **Who:** Anyone (no login)
- **Uses:** view `v_zone_occupancy`

Counts of free, occupied, reserved and maintenance slots in each zone.

**Success example**

`GET /api/zones/occupancy`

Response `200`:
```json
[
  {
    "available": 8.0,
    "maintenance": 0.0,
    "occupied": 0.0,
    "reserved": 0.0,
    "total_slots": 8,
    "zone_code": "A",
    "zone_id": 1,
    "zone_name": "Ground - Entrance Row"
  },
  {
    "available": 6.0,
    "maintenance": 0.0,
    "occupied": 0.0,
    "reserved": 0.0,
    "total_slots": 6,
    "zone_code": "B",
    "zone_id": 2,
    "zone_name": "Ground - Rear Row"
  }
]
```
*(list shortened: first 2 of 4 items shown)*


## 3. Vehicles

### List vehicles: `GET /api/vehicles`

- **Who:** Logged-in user
- **Uses:** SELECT on `vehicles`

A user sees only their own vehicles. An admin sees all.

**Success example**

`GET /api/vehicles`

Response `200`:
```json
[
  {
    "created_at": "2026-10-27 06:42:57",
    "has_accessible_permit": 0,
    "is_ev": 0,
    "owner": "Aarav Patil",
    "reg_number": "MH12AB1001",
    "user_id": 2,
    "vehicle_id": 1,
    "vehicle_type": "CAR"
  },
  {
    "created_at": "2026-10-27 06:42:57",
    "has_accessible_permit": 0,
    "is_ev": 0,
    "owner": "Aarav Patil",
    "reg_number": "MH12AB2001",
    "user_id": 2,
    "vehicle_id": 2,
    "vehicle_type": "TWO_WHEELER"
  }
]
```
*(list shortened: first 2 of 3 items shown)*

| Status | Meaning |
|---|---|
| 401 | Not logged in |

### Add a vehicle: `POST /api/vehicles`

- **Who:** Logged-in user
- **Uses:** INSERT into `vehicles`

Registers a vehicle for the logged-in user. Spaces are removed and letters are upper-cased.

| Input | Rules |
|---|---|
| `reg_number` | required, 4 to 15 letters or digits, unique |
| `vehicle_type` | required: `CAR` or `TWO_WHEELER` |
| `is_ev` | optional boolean |
| `has_accessible_permit` | optional boolean |

**Success example**

`POST /api/vehicles`

Request body:
```json
{
  "reg_number": "MH12XY2815",
  "vehicle_type": "CAR",
  "is_ev": false,
  "has_accessible_permit": false
}
```

Response `201`:
```json
{
  "reg_number": "MH12XY2815",
  "vehicle_id": 15
}
```

**Error example**

`POST /api/vehicles`

Request body:
```json
{
  "reg_number": "AB",
  "vehicle_type": "CAR"
}
```

Response `400`:
```json
{
  "error": "Registration number must be 4-15 letters/digits."
}
```

| Status | Meaning |
|---|---|
| 400 | Invalid registration number or type |
| 409 | Registration number already exists |


### Edit a vehicle: `PUT /api/vehicles/{id}`

- **Who:** Logged-in user (own vehicles; an admin may edit any)
- **Uses:** UPDATE on `vehicles`

Send only the fields you want to change. Saving identical values gives 200 with `"changed": false`. The type, EV flag and permit decide which slots a vehicle may use, so they cannot change while the vehicle is parked or has a PENDING or ACTIVE reservation (409). The plate can always be corrected.

| Input | Rules |
|---|---|
| `id` | path, vehicle number |
| `reg_number` | optional, 4 to 15 letters or digits, unique |
| `vehicle_type` | optional: `CAR` or `TWO_WHEELER` |
| `is_ev` | optional, `true` or `false` (the text `"false"` is refused) |
| `has_accessible_permit` | optional, `true` or `false` |

**Success example**

`PUT /api/vehicles/15`

Request body:
```json
{
  "reg_number": "MH12XY9999",
  "is_ev": true
}
```

Response `200`:
```json
{
  "changed": true,
  "message": "Vehicle updated."
}
```

**Error example**

`PUT /api/vehicles/15`

Request body:
```json
{
  "reg_number": "MH12AB1001"
}
```

Response `409`:
```json
{
  "error": "This registration number is already registered."
}
```

| Status | Meaning |
|---|---|
| 400 | Nothing to change, bad plate, type or flag |
| 403 | Not your vehicle |
| 404 | Vehicle not found |
| 409 | Plate already used, or type/EV/permit change while parked or reserved |

### Delete a vehicle: `DELETE /api/vehicles/{id}`

- **Who:** Logged-in user (own vehicles; an admin may delete any)
- **Uses:** DELETE on `vehicles`

Only a vehicle with no history can be deleted. If it has any reservations (even cancelled ones), parking sessions or violations, the answer is 409 with the counts, because bills and fines must stay in the database.

**Success example**

`DELETE /api/vehicles/15`

Response `200`:
```json
{
  "message": "Vehicle MH12XY9999 deleted."
}
```

**Error example**

`DELETE /api/vehicles/1`

Response `409`:
```json
{
  "error": "Cannot delete MH12AB1001: it has 230 sessions, 5 violations. Vehicles with history are kept for billing and audit."
}
```

| Status | Meaning |
|---|---|
| 403 | Not your vehicle |
| 404 | Vehicle not found |
| 409 | The vehicle has reservations, sessions or violations |


## 4. Finding and reserving a slot

### Recommend slots: `GET /api/recommend`

- **Who:** Logged-in user
- **Uses:** procedure `sp_recommend_slots`

Hard rules first (slot type, EV and accessible eligibility, free for the whole period), then a weighted score. Best first. `reason` explains the score in words.

| Input | Rules |
|---|---|
| `vehicle_id` | query, required, must be your own |
| `start` | query, required, `YYYY-MM-DDTHH:MM` |
| `end` | query, required, after start |

**Success example**

`GET /api/recommend`  query: `vehicle_id=1&start=2026-10-29T08:00&end=2026-10-29T10:00`

Response `200`:
```json
[
  {
    "distance_to_entrance_m": 12,
    "is_accessible": 0,
    "is_ev_charger": 0,
    "is_premium": 0,
    "reason": "12 m from entrance; standard rate",
    "score": 1.0,
    "slot_code": "A-03",
    "slot_id": 3,
    "zone_name": "Ground - Entrance Row"
  },
  {
    "distance_to_entrance_m": 16,
    "is_accessible": 0,
    "is_ev_charger": 0,
    "is_premium": 0,
    "reason": "16 m from entrance; standard rate",
    "score": 0.9855,
    "slot_code": "A-04",
    "slot_id": 4,
    "zone_name": "Ground - Entrance Row"
  }
]
```
*(list shortened: first 2 of 5 items shown)*

**Error example**

`GET /api/recommend`  query: `vehicle_id=1&start=2026-10-29T10:00&end=2026-10-29T08:00`

Response `400`:
```json
{
  "error": "End time must be after start time."
}
```

| Status | Meaning |
|---|---|
| 400 | Bad date or end not after start |
| 403 | Not your vehicle |
| 404 | Vehicle not found |

### Create a reservation: `POST /api/reservations`

- **Who:** Logged-in user
- **Uses:** procedure `sp_create_reservation`

The core transaction. The procedure locks the slot row (`FOR UPDATE`), checks eligibility and overlaps, and inserts. Two people booking the same slot at the same time: exactly one wins.

| Input | Rules |
|---|---|
| `vehicle_id` | required, your own vehicle |
| `slot_id` | required |
| `start` | required, not in the past |
| `end` | required, after start, at most 24 hours |
| `alloc_score` | **ignored.** The database computes the score itself (Decision D-20) |
| `alloc_reason` | **ignored.** Filled in by the server, together with `alloc_score`. Both stay empty if the slot is not among the top 5 recommendations |

**Success example**

`POST /api/reservations`

Request body:
```json
{
  "vehicle_id": 1,
  "slot_id": 3,
  "start": "2026-10-29T08:00",
  "end": "2026-10-29T10:00",
  "alloc_score": 1.0,
  "alloc_reason": "12 m from entrance; standard rate"
}
```

Response `201`:
```json
{
  "message": "Reservation created.",
  "reservation_id": 1
}
```

**Error example**

`POST /api/reservations`

Request body:
```json
{
  "vehicle_id": 7,
  "slot_id": 3,
  "start": "2026-10-29T08:00",
  "end": "2026-10-29T10:00",
  "alloc_score": null,
  "alloc_reason": null
}
```

Response `409`:
```json
{
  "error": "Slot already booked for that period"
}
```

**Error example**

`POST /api/reservations`

Request body:
```json
{
  "vehicle_id": 7,
  "slot_id": 3,
  "start": "2026-10-29T08:00",
  "end": "2026-10-29T10:00",
  "alloc_score": 1.0,
  "alloc_reason": "12 m from entrance; standard rate"
}
```

Response `403`:
```json
{
  "error": "This is not your vehicle."
}
```

| Status | Meaning |
|---|---|
| 400 | Missing field or bad date |
| 403 | Not your vehicle |
| 409 | A database rule was broken (overlap, eligibility, past time, over 24 h, vehicle already booked) |

### List reservations: `GET /api/reservations`

- **Who:** Logged-in user
- **Uses:** SELECT with joins

Own reservations (admin: all), newest first, at most 200.

**Success example**

`GET /api/reservations`

Response `200`:
```json
[
  {
    "alloc_reason": "12 m from entrance; standard rate",
    "alloc_score": 1.0,
    "end_time": "2026-10-29 10:00:00",
    "reg_number": "MH12AB1001",
    "reservation_id": 1,
    "slot_code": "A-03",
    "start_time": "2026-10-29 08:00:00",
    "status": "PENDING",
    "user_id": 2
  }
]
```

### Cancel a reservation: `DELETE /api/reservations/{id}`

- **Who:** Logged-in user
- **Uses:** procedure `sp_cancel_reservation`

Only PENDING reservations can be cancelled, by their owner (or an admin).

| Input | Rules |
|---|---|
| `id` | path, reservation number |

**Success example**

`DELETE /api/reservations/1`

Response `200`:
```json
{
  "message": "Reservation cancelled."
}
```

**Error example**

`DELETE /api/reservations/1`

Response `409`:
```json
{
  "error": "Only PENDING reservations can be cancelled"
}
```

| Status | Meaning |
|---|---|
| 404 | Reservation not found |
| 409 | Not cancellable (not PENDING, or not yours) |


## 5. Entry, exit and billing

### Vehicle entry: `POST /api/sessions/entry`

- **Who:** Logged-in user
- **Uses:** procedure `sp_vehicle_entry`

Simulates the gate. Flask always passes `NULL` as the time, so the database uses its own clock (Decision D-13). The trigger turns the slot OCCUPIED. A walk-in is refused if the slot is reserved by someone else soon.

| Input | Rules |
|---|---|
| `vehicle_id` | required, your own vehicle |
| `slot_id` | required |

**Success example**

`POST /api/sessions/entry`

Request body:
```json
{
  "vehicle_id": 1,
  "slot_id": 8
}
```

Response `201`:
```json
{
  "message": "Entry recorded.",
  "session_id": 2898
}
```

**Error example**

`POST /api/sessions/entry`

Request body:
```json
{
  "vehicle_id": 1,
  "slot_id": 11
}
```

Response `409`:
```json
{
  "error": "Slot or vehicle already has an active session"
}
```

| Status | Meaning |
|---|---|
| 403 | Not your vehicle |
| 409 | Slot or vehicle already has an active session, slot reserved, or eligibility rule |

### Vehicle exit: `POST /api/sessions/{id}/exit`

- **Who:** Logged-in user
- **Uses:** procedure `sp_vehicle_exit`

Closes the session and computes the bill in the database (`fn_calc_amount`): grace period, hourly blocks, minimum charge, daily cap. No request body.

| Input | Rules |
|---|---|
| `id` | path, session number |

**Success example**

`POST /api/sessions/2900/exit`

Response `200`:
```json
{
  "amount_due": 90.0,
  "bill": {
    "billable_minutes": 135,
    "daily_cap": 200.0,
    "duration_minutes": 145,
    "entry_time": "2026-10-27 04:18:21",
    "exit_time": "2026-10-27 06:43:21",
    "fines": 0.0,
    "grace_minutes": 10,
    "hourly_blocks": 3,
    "hourly_rate": 30.0,
    "min_charge": 30.0,
    "paid_at": null,
    "parking_fee": 90.0,
    "payment_method": null,
    "payment_status": "PENDING",
    "reg_number": "MH12AB1001",
    "session_id": 2900,
    "slot_code": "B-04"
  },
  "message": "Exit recorded. Bill generated.",
  "session_id": 2900
}
```

**Error example**

`POST /api/sessions/2898/exit`

Response `409`:
```json
{
  "error": "Session is already closed"
}
```

| Status | Meaning |
|---|---|
| 403 | Not your session |
| 404 | Session not found |
| 409 | Session already closed |

### Vehicles inside now: `GET /api/sessions/active`

- **Who:** Logged-in user
- **Uses:** view `v_active_sessions`

Own active sessions (admin: all) with elapsed minutes and the amount so far.

**Success example**

`GET /api/sessions/active`

Response `200`:
```json
[
  {
    "elapsed_minutes": 0,
    "entry_time": "2026-10-27 06:43:21",
    "reg_number": "MH12AB1001",
    "reservation_id": null,
    "running_amount": 0.0,
    "session_id": 2898,
    "slot_code": "A-08",
    "vehicle_type": "CAR"
  }
]
```

### Unpaid bills: `GET /api/bills/unpaid`

- **Who:** Logged-in user
- **Uses:** view `v_unpaid_bills`

Own closed sessions with an unpaid fee (admin: all).

**Success example**

`GET /api/bills/unpaid`

Response `200`:
```json
[
  {
    "exit_time": "2026-10-27 06:43:21",
    "parking_fee": 90.0,
    "payment_status": "PENDING",
    "reg_number": "MH12AB1001",
    "session_id": 2900,
    "slot_code": "B-04"
  }
]
```

### Itemized bill: `GET /api/bills/{id}`

- **Who:** Logged-in user
- **Uses:** view `v_itemized_bill`

Shows how the fee was computed, step by step.

| Input | Rules |
|---|---|
| `id` | path, session number |

**Success example**

`GET /api/bills/2900`

Response `200`:
```json
{
  "billable_minutes": 135,
  "daily_cap": 200.0,
  "duration_minutes": 145,
  "entry_time": "2026-10-27 04:18:21",
  "exit_time": "2026-10-27 06:43:21",
  "fines": 0.0,
  "grace_minutes": 10,
  "hourly_blocks": 3,
  "hourly_rate": 30.0,
  "min_charge": 30.0,
  "paid_at": null,
  "parking_fee": 90.0,
  "payment_method": null,
  "payment_status": "PENDING",
  "reg_number": "MH12AB1001",
  "session_id": 2900,
  "slot_code": "B-04"
}
```

**Error example**

`GET /api/bills/2898`

Response `404`:
```json
{
  "error": "No bill yet. The vehicle has not exited."
}
```

**Error example**

`GET /api/bills/2900`

Response `403`:
```json
{
  "error": "This is not your session."
}
```

| Status | Meaning |
|---|---|
| 403 | Not your session |
| 404 | No bill yet (vehicle has not exited) |

### Pay a bill (simulated): `POST /api/payments`

- **Who:** Logged-in user
- **Uses:** procedure `sp_record_payment`

There is no real payment gateway. `simulate_failure` makes the attempt fail so you can show a retry.

| Input | Rules |
|---|---|
| `session_id` | required, your own session |
| `method` | required: `CASH`, `UPI` or `CARD` |
| `simulate_failure` | optional boolean |

**Success example**

`POST /api/payments`

Request body:
```json
{
  "session_id": 2900,
  "method": "UPI"
}
```

Response `200`:
```json
{
  "bill": {
    "billable_minutes": 135,
    "daily_cap": 200.0,
    "duration_minutes": 145,
    "entry_time": "2026-10-27 04:18:21",
    "exit_time": "2026-10-27 06:43:21",
    "fines": 0.0,
    "grace_minutes": 10,
    "hourly_blocks": 3,
    "hourly_rate": 30.0,
    "min_charge": 30.0,
    "paid_at": "2026-10-27 06:43:21",
    "parking_fee": 90.0,
    "payment_method": "UPI",
    "payment_status": "PAID",
    "reg_number": "MH12AB1001",
    "session_id": 2900,
    "slot_code": "B-04"
  },
  "message": "Payment successful.",
  "result": null
}
```

**Error example**

`POST /api/payments`

Request body:
```json
{
  "session_id": 2900,
  "method": "UPI",
  "simulate_failure": true
}
```

Response `200`:
```json
{
  "bill": {
    "billable_minutes": 135,
    "daily_cap": 200.0,
    "duration_minutes": 145,
    "entry_time": "2026-10-27 04:18:21",
    "exit_time": "2026-10-27 06:43:21",
    "fines": 0.0,
    "grace_minutes": 10,
    "hourly_blocks": 3,
    "hourly_rate": 30.0,
    "min_charge": 30.0,
    "paid_at": null,
    "parking_fee": 90.0,
    "payment_method": null,
    "payment_status": "PENDING",
    "reg_number": "MH12AB1001",
    "session_id": 2900,
    "slot_code": "B-04"
  },
  "message": "Payment failed. You can retry.",
  "result": null
}
```

**Error example**

`POST /api/payments`

Request body:
```json
{
  "session_id": 2900,
  "method": "BITCOIN"
}
```

Response `400`:
```json
{
  "error": "method must be CASH, UPI or CARD."
}
```

**Error example**

`POST /api/payments`

Request body:
```json
{
  "session_id": 2900,
  "method": "UPI"
}
```

Response `409`:
```json
{
  "error": "No pending payment for this session"
}
```

| Status | Meaning |
|---|---|
| 400 | Unknown method |
| 403 | Not your session |
| 409 | No pending payment for this session |


## 6. Admin

### List tariffs: `GET /api/admin/tariffs`

- **Who:** Admin only
- **Uses:** SELECT on `tariff_rules`

The pricing rules used by billing.

**Success example**

`GET /api/admin/tariffs`

Response `200`:
```json
[
  {
    "daily_cap": 60.0,
    "effective_from": "2026-01-01",
    "grace_minutes": 10,
    "hourly_rate": 10.0,
    "is_premium": 0,
    "min_charge": 10.0,
    "overstay_fine_per_hour": 20.0,
    "tariff_id": 3,
    "vehicle_type": "TWO_WHEELER"
  },
  {
    "daily_cap": 200.0,
    "effective_from": "2026-01-01",
    "grace_minutes": 10,
    "hourly_rate": 30.0,
    "is_premium": 0,
    "min_charge": 30.0,
    "overstay_fine_per_hour": 50.0,
    "tariff_id": 1,
    "vehicle_type": "CAR"
  }
]
```
*(list shortened: first 2 of 3 items shown)*

**Error example**

`GET /api/admin/audit`

Response `403`:
```json
{
  "error": "Admin only."
}
```

| Status | Meaning |
|---|---|
| 401 | Not logged in |
| 403 | Not an admin |

### Update a tariff: `PUT /api/admin/tariffs`

- **Who:** Admin only
- **Uses:** UPDATE on `tariff_rules` (trigger writes `audit_logs`)

Changes the price rules. `@app_user_id` is set so the audit trigger records who changed what. Old sessions keep their frozen `tariff_id`.

| Input | Rules |
|---|---|
| `tariff_id` | required |
| `hourly_rate` | required |
| `grace_minutes` | required |
| `min_charge` | required |
| `daily_cap` | optional, empty means no cap |
| `overstay_fine_per_hour` | required |

**Success example**

`PUT /api/admin/tariffs`

Request body:
```json
{
  "tariff_id": 3,
  "hourly_rate": 11.0,
  "grace_minutes": 10,
  "min_charge": 10.0,
  "daily_cap": 60.0,
  "overstay_fine_per_hour": 20.0
}
```

Response `200`:
```json
{
  "changed": true,
  "message": "Tariff updated."
}
```

| Status | Meaning |
|---|---|
Saving the same values again is not an error: the answer is 200 with `"changed": false`.

**No-change example**

`PUT /api/admin/tariffs` with the values already stored.

Response `200`:
```json
{
  "changed": false,
  "message": "No change: these values are already saved."
}
```

**Error example**

`PUT /api/admin/tariffs` with `"hourly_rate": -5`.

Response `400`:
```json
{
  "error": "'hourly_rate' must be between 0.01 and 9999."
}
```

| Status | Meaning |
|---|---|
| 400 | A number is missing, not a number, out of range (rate 0.01 to 9999, grace 0 to 1440 whole minutes, charges 0 to 9999, cap 0 to 99999) or the cap is below the minimum charge |
| 404 | Tariff not found |

### Set slot maintenance or available: `PUT /api/admin/slots/{id}/status`

- **Who:** Admin only
- **Uses:** UPDATE on `parking_slots` (audited)

Only these two stored statuses can be set by hand.

| Input | Rules |
|---|---|
| `id` | path, slot number |
| `status` | required: `AVAILABLE` or `MAINTENANCE` |

**Success example**

`PUT /api/admin/slots/10/status`

Request body:
```json
{
  "status": "MAINTENANCE"
}
```

Response `200`:
```json
{
  "message": "Slot set to MAINTENANCE."
}
```

**Error example**

`PUT /api/admin/slots/10/status`

Request body:
```json
{
  "status": "BROKEN"
}
```

Response `400`:
```json
{
  "error": "status must be AVAILABLE or MAINTENANCE."
}
```

| Status | Meaning |
|---|---|
| 400 | Bad status |
| 404 | Slot not found |

### List users: `GET /api/admin/users`

- **Who:** Admin only
- **Uses:** SELECT on `users` and `vehicles`

All accounts (at most 500) with how many vehicles each owns. The password hash is never returned.

**Success example**

`GET /api/admin/users`

Response `200`:
```json
[
  {
    "created_at": "2026-10-28 08:58:39",
    "email": "admin@parkwise.test",
    "full_name": "Parking Admin",
    "phone": "9000000000",
    "role": "ADMIN",
    "user_id": 1,
    "vehicles": 0
  },
  {
    "created_at": "2026-10-28 08:58:39",
    "email": "aarav@parkwise.test",
    "full_name": "Aarav Patil",
    "phone": "9000000001",
    "role": "USER",
    "user_id": 2,
    "vehicles": 3
  }
]
```
*(list shortened: first 2 of 8 items shown)*

| Status | Meaning |
|---|---|
| 401 | Not logged in |
| 403 | Not an admin |

### List violations: `GET /api/admin/violations`

- **Who:** Admin only
- **Uses:** SELECT with join

Latest 200, with the vehicle plate.

**Success example**

`GET /api/admin/violations`

Response `200`:
```json
[
  {
    "detected_at": "2026-10-27 06:43:21",
    "fine_amount": 50.0,
    "notes": "Stayed past booked time",
    "reg_number": "MH12AB1001",
    "reservation_id": null,
    "session_id": 2900,
    "status": "OPEN",
    "vehicle_id": 1,
    "violation_id": 109,
    "violation_type": "OVERSTAY"
  },
  {
    "detected_at": "2026-10-26 20:30:00",
    "fine_amount": 50.0,
    "notes": "Synthetic history",
    "reg_number": "MH14JK1005",
    "reservation_id": null,
    "session_id": 2844,
    "status": "PAID",
    "vehicle_id": 9,
    "violation_id": 105,
    "violation_type": "WRONG_SLOT"
  }
]
```
*(list shortened: first 2 of 109 items shown)*

### Log a violation: `POST /api/admin/violations`

- **Who:** Admin only
- **Uses:** procedure `sp_log_violation`

Records a fine manually (overstays and no-shows are also created automatically by the scheduled events).

| Input | Rules |
|---|---|
| `session_id` | required |
| `violation_type` | `OVERSTAY`, `WRONG_SLOT` or `UNAUTHORIZED_BAY` |
| `fine_amount` | optional number from 0 to 99999 |
| `notes` | optional text, at most 255 characters |

**Success example**

`POST /api/admin/violations`

Request body:
```json
{
  "session_id": 2900,
  "violation_type": "OVERSTAY",
  "fine_amount": 50,
  "notes": "Stayed past booked time"
}
```

Response `201`:
```json
{
  "message": "Violation recorded."
}
```

| Status | Meaning |
|---|---|
| 400 | Bad type or field |
| 409 | A database rule was broken |

### Settle a violation: `PUT /api/admin/violations/{id}/status`

- **Who:** Admin only
- **Uses:** UPDATE on `violations`, plus an `audit_logs` row (action `VIOLATION_RESOLVE`) saved in the same transaction

Moves an OPEN violation to PAID (fine collected) or WAIVED (forgiven). It is one-way: a violation that is already PAID or WAIVED cannot be changed again.

| Input | Rules |
|---|---|
| `id` | path, violation number |
| `status` | required: `PAID` or `WAIVED` |

**Success example**

`PUT /api/admin/violations/83/status`

Request body:
```json
{
  "status": "WAIVED"
}
```

Response `200`:
```json
{
  "message": "Violation marked WAIVED."
}
```

**Error example**

`PUT /api/admin/violations/83/status` (again)

Response `409`:
```json
{
  "error": "Violation is already WAIVED; only OPEN violations can be settled."
}
```

| Status | Meaning |
|---|---|
| 400 | Status is not PAID or WAIVED |
| 404 | Violation not found |
| 409 | The violation is not OPEN |

### Audit log: `GET /api/admin/audit`

- **Who:** Admin only
- **Uses:** SELECT on `audit_logs`

Latest 100 changes with who made them.

**Success example**

`GET /api/admin/audit`

Response `200`:
```json
[
  {
    "action": "SLOT_MAINTENANCE",
    "actor": "Parking Admin",
    "created_at": "2026-10-27 06:43:21",
    "entity": "parking_slots",
    "entity_id": 10,
    "log_id": 4,
    "new_value": "{\"status\": \"AVAILABLE\"}",
    "old_value": "{\"status\": \"MAINTENANCE\"}"
  },
  {
    "action": "SLOT_MAINTENANCE",
    "actor": "Parking Admin",
    "created_at": "2026-10-27 06:43:21",
    "entity": "parking_slots",
    "entity_id": 10,
    "log_id": 3,
    "new_value": "{\"status\": \"MAINTENANCE\"}",
    "old_value": "{\"status\": \"AVAILABLE\"}"
  }
]
```
*(list shortened: first 2 of 4 items shown)*

### Run the scheduled jobs now: `POST /api/admin/run-jobs`

- **Who:** Admin only
- **Uses:** procedures `sp_release_no_shows`, `sp_flag_overstays`, `sp_take_snapshot`

Demo fallback when the event scheduler is off: runs the no-show, overstay and snapshot jobs once.

**Success example**

`POST /api/admin/run-jobs`

Response `200`:
```json
{
  "message": "No-show, overstay and snapshot jobs executed."
}
```


## 7. Analytics (admin)

### Summary tiles: `GET /api/analytics/summary`

- **Who:** Admin only
- **Uses:** several tables and views

Headline numbers for the dashboard.

**Success example**

`GET /api/analytics/summary`

Response `200`:
```json
{
  "active_sessions": 0,
  "occupancy_pct": 0.0,
  "open_violations": 1,
  "pending_reservations": 0,
  "revenue_today": 90.0,
  "revenue_total": 198310.0,
  "unpaid_bills": 0
}
```

### Daily revenue: `GET /api/analytics/revenue`

- **Who:** Admin only
- **Uses:** view `v_daily_revenue`

Last 30 days, oldest first.

**Success example**

`GET /api/analytics/revenue`

Response `200`:
```json
[
  {
    "payments_count": 104,
    "revenue": 7280.0,
    "revenue_date": "2026-09-28"
  },
  {
    "payments_count": 109,
    "revenue": 7240.0,
    "revenue_date": "2026-09-29"
  }
]
```
*(list shortened: first 2 of 30 items shown)*

### Entries by hour of day: `GET /api/analytics/hourly-demand`

- **Who:** Admin only
- **Uses:** view `v_hourly_demand`

Counts of entries per hour.

**Success example**

`GET /api/analytics/hourly-demand`

Response `200`:
```json
[
  {
    "avg_duration_min": 145.0,
    "entries": 1,
    "hour_of_day": 4
  },
  {
    "avg_duration_min": 0.0,
    "entries": 1,
    "hour_of_day": 6
  }
]
```
*(list shortened: first 2 of 15 items shown)*

### Occupancy forecast: `GET /api/analytics/forecast`

- **Who:** Admin only
- **Uses:** view `v_occupancy_forecast`

Average occupancy by weekday and hour over the stored history. A rule-based estimate, not AI.

**Success example**

`GET /api/analytics/forecast`

Response `200`:
```json
[
  {
    "avg_occupancy_pct": 0.0,
    "day_of_week": 1,
    "days_observed": 5,
    "expectation": "EASY",
    "hour_of_day": 6
  },
  {
    "avg_occupancy_pct": 1.7,
    "day_of_week": 1,
    "days_observed": 5,
    "expectation": "EASY",
    "hour_of_day": 7
  }
]
```
*(list shortened: first 2 of 119 items shown)*

### Carbon-savings estimate: `GET /api/analytics/carbon`

- **Who:** Admin only
- **Uses:** view `v_carbon_estimate`

A small, labelled estimate (emission factor is still a placeholder, see Decision.md).

**Success example**

`GET /api/analytics/carbon`

Response `200`:
```json
{
  "co2_saved_g": 3473.6,
  "metres_saved": 28947.0,
  "note": "Estimate only: distance saved vs an average slot of the same type x an emission factor (Decision D-10).",
  "sessions": 2899
}
```

## Business rules behind the 409 errors

These are real messages produced by the database during the capture or the tests:

| Message | Rule |
|---|---|
| Slot already booked for that period | No overlapping PENDING or ACTIVE reservation on one slot |
| Vehicle already has a reservation in that period | A vehicle cannot hold two overlapping reservations |
| Only PENDING reservations can be cancelled | State machine PENDING → ACTIVE / NO_SHOW / CANCELLED |
| Slot or vehicle already has an active session | One open session per slot and per vehicle (UNIQUE keys on generated columns) |
| Session is already closed | A session can exit only once |
| No pending payment for this session | A paid or waived bill cannot be paid again |
| Accessible bay requires an accessibility permit | Eligibility rule (`sp_assert_eligible`) |
| Slot is reserved for another vehicle | A walk-in cannot take a slot reserved for someone else soon |

## Known quirks and limits (be honest about these in the viva)

- Saving the same tariff values again returns 200 "No change" (it used to be a 404, because MySQL counts only changed rows).
- A bill that costs 0 (leaving inside the grace period) is created already PAID with method WAIVED, so it does not appear in the unpaid list.
- Lists are capped and not paginated: reservations 200, violations 200, audit 100, revenue 30 days.
- Payments are simulated. There is no payment gateway, refund or receipt.
- Authentication is a session cookie (`HttpOnly`, `SameSite=Lax`). Cross-site writes are also refused by an `Origin` check (Decision D-19); there is no separate CSRF token.
- The failed-login counter lives in the Flask process and is per e-mail, so restarting the app clears it. A person who knows an e-mail address can lock that account for 15 minutes by failing five times (the usual trade-off of this rule).
- There is no password reset, and no way to change a password yet.
- A violation settled as PAID or WAIVED cannot be re-opened.
- A vehicle with any reservation, session or violation can never be deleted, only edited.
- The analytics endpoints return JSON only. The charts are drawn by the frontend (Chart.js).
