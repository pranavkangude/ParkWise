-- =====================================================================
-- ParkWise seed data (reference data + demo users/vehicles)
-- Demo logins:  admin@parkwise.test / Admin@123   |   students: Student@123
-- Run AFTER schema.sql.  Hashes are werkzeug scrypt (Flask-compatible).
-- =====================================================================
USE parkwise;

-- Settings -------------------------------------------------------------
INSERT INTO system_settings (setting_key, setting_value, description) VALUES
 ('noshow_grace_minutes','15','Minutes after reservation start before a PENDING booking becomes NO_SHOW'),
 ('noshow_fine','0','Fine (INR) recorded for a no-show'),
 ('early_entry_minutes','15','How many minutes before start a reserved vehicle may enter'),
 ('walkin_buffer_minutes','60','Walk-ins are refused on a slot reserved to start within this many minutes'),
 ('reserve_hold_minutes','30','Live board shows RESERVED this many minutes before a booking starts'),
 ('w_distance','0.30','Allocation weight: closeness to entrance'),
 ('w_ev','0.35','Allocation weight: EV vehicle on charger bay'),
 ('w_accessible','0.25','Allocation weight: permit holder on accessible bay'),
 ('w_cost','0.10','Allocation weight: prefer standard-rate slot'),
 ('emission_g_per_km','120','ASSUMPTION (g CO2/km, passenger car) - replace with a cited figure before submission');

-- Zones (single lot, 4 zones, 24 slots) -----------------------------------
INSERT INTO zones (zone_code, zone_name, floor_level) VALUES
 ('A','Ground - Entrance Row',0),
 ('B','Ground - Rear Row',0),
 ('C','Two-Wheeler Bay',0),
 ('D','First Floor',1);

-- Slots ------------------------------------------------------------------
-- cols: zone, code, type, ev_charger, accessible, premium, distance_m
INSERT INTO parking_slots (zone_id, slot_code, slot_type, is_ev_charger, is_accessible, is_premium, distance_to_entrance_m) VALUES
 (1,'A-01','CAR',0,1,0, 5),(1,'A-02','CAR',0,1,0, 8),(1,'A-03','CAR',0,0,0,12),(1,'A-04','CAR',0,0,0,16),
 (1,'A-05','CAR',0,0,0,20),(1,'A-06','CAR',0,0,0,25),(1,'A-07','CAR',0,0,0,30),(1,'A-08','CAR',0,0,0,35),
 (2,'B-01','CAR',1,0,1,45),(2,'B-02','CAR',1,0,1,50),(2,'B-03','CAR',0,0,0,55),(2,'B-04','CAR',0,0,0,60),
 (2,'B-05','CAR',0,0,0,65),(2,'B-06','CAR',0,0,0,70),
 (3,'C-01','TWO_WHEELER',0,0,0,10),(3,'C-02','TWO_WHEELER',0,0,0,13),(3,'C-03','TWO_WHEELER',0,0,0,16),
 (3,'C-04','TWO_WHEELER',0,0,0,19),(3,'C-05','TWO_WHEELER',0,0,0,22),(3,'C-06','TWO_WHEELER',0,0,0,25),
 (4,'D-01','CAR',0,0,0,80),(4,'D-02','CAR',0,0,0,85),(4,'D-03','CAR',0,0,0,90),(4,'D-04','CAR',0,0,0,95);

-- Tariffs (INR) --------------------------------------------------------------
-- cols: type, premium, rate/h, grace_min, min_charge, daily_cap, overstay_fine/h, effective_from
INSERT INTO tariff_rules (vehicle_type, is_premium, hourly_rate, grace_minutes, min_charge, daily_cap, overstay_fine_per_hour, effective_from) VALUES
 ('CAR',         0, 30.00, 10, 30.00, 200.00, 50.00, '2026-01-01'),
 ('CAR',         1, 50.00, 10, 50.00, 300.00, 80.00, '2026-01-01'),
 ('TWO_WHEELER', 0, 10.00, 10, 10.00,  60.00, 20.00, '2026-01-01');

-- Users ----------------------------------------------------------------------
INSERT INTO users (full_name, email, phone, password_hash, role) VALUES
 ('Parking Admin','admin@parkwise.test','9000000000','scrypt:32768:8:1$ATn1OSMUYQS0MN7X$3b4e413a2a23c9333b91fc6f64c2b861e22454c1116c7d5cf268ac7f61ce60a59ecd0dab056eaba358bb4b8a10c9ca9d7c94915478189aa3fe64f94d37c8cd2c','ADMIN'),
 ('Aarav Patil','aarav@parkwise.test','9000000001','scrypt:32768:8:1$QbTNebGoyFQdDvnn$793a9669d6ca9a0e9eceff26757b5ff80bd52f7d31bf954d13453c055f7ec26a5e7b68d38d0617976ea2f62b7a9eb0a9592e5b5303130f4f4e01a0a5d1346357','USER'),
 ('Diya Kulkarni','diya@parkwise.test','9000000002','scrypt:32768:8:1$QbTNebGoyFQdDvnn$793a9669d6ca9a0e9eceff26757b5ff80bd52f7d31bf954d13453c055f7ec26a5e7b68d38d0617976ea2f62b7a9eb0a9592e5b5303130f4f4e01a0a5d1346357','USER'),
 ('Rohan Deshmukh','rohan@parkwise.test','9000000003','scrypt:32768:8:1$QbTNebGoyFQdDvnn$793a9669d6ca9a0e9eceff26757b5ff80bd52f7d31bf954d13453c055f7ec26a5e7b68d38d0617976ea2f62b7a9eb0a9592e5b5303130f4f4e01a0a5d1346357','USER'),
 ('Sneha Joshi','sneha@parkwise.test','9000000004','scrypt:32768:8:1$QbTNebGoyFQdDvnn$793a9669d6ca9a0e9eceff26757b5ff80bd52f7d31bf954d13453c055f7ec26a5e7b68d38d0617976ea2f62b7a9eb0a9592e5b5303130f4f4e01a0a5d1346357','USER'),
 ('Kabir Shah','kabir@parkwise.test','9000000005','scrypt:32768:8:1$QbTNebGoyFQdDvnn$793a9669d6ca9a0e9eceff26757b5ff80bd52f7d31bf954d13453c055f7ec26a5e7b68d38d0617976ea2f62b7a9eb0a9592e5b5303130f4f4e01a0a5d1346357','USER'),
 ('Meera Nair','meera@parkwise.test','9000000006','scrypt:32768:8:1$QbTNebGoyFQdDvnn$793a9669d6ca9a0e9eceff26757b5ff80bd52f7d31bf954d13453c055f7ec26a5e7b68d38d0617976ea2f62b7a9eb0a9592e5b5303130f4f4e01a0a5d1346357','USER');

-- Vehicles (2 EVs, 1 accessibility-permit holder, 6 bikes) -----------------------
-- cols: owner, reg, type, is_ev, permit
INSERT INTO vehicles (user_id, reg_number, vehicle_type, is_ev, has_accessible_permit) VALUES
 (2,'MH12AB1001','CAR',0,0),
 (2,'MH12AB2001','TWO_WHEELER',0,0),
 (3,'MH12CD1002','CAR',1,0),
 (3,'MH12CD2002','TWO_WHEELER',0,0),
 (4,'MH14EF1003','CAR',0,1),
 (4,'MH14EF2003','TWO_WHEELER',0,0),
 (5,'MH12GH1004','CAR',0,0),
 (5,'MH12GH2004','TWO_WHEELER',0,0),
 (6,'MH14JK1005','CAR',1,0),
 (6,'MH14JK2005','TWO_WHEELER',0,0),
 (7,'MH12LM1006','CAR',0,0),
 (7,'MH12LM2006','TWO_WHEELER',0,0),
 (2,'MH12AB1011','CAR',0,0),
 (3,'MH12CD1012','CAR',0,0);

-- Optional: 30 days of synthetic history so analytics/forecast have data (takes a few seconds).
CALL sp_seed_history(30);
