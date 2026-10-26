-- =====================================================================
-- ParkWise - Smart Parking Allocation and Predictive Management System
-- Single parking lot, multiple zones.  Target: MySQL 8.0+ (InnoDB)
-- Run order: 1) schema.sql  2) seed.sql  3) (optional) tests.sql
-- Re-runnable: drops and recreates the `parkwise` database.
-- Needs an account that can create triggers/functions/events (root is fine).
-- Events need:  SET GLOBAL event_scheduler = ON;   (see Decision.md D-12)
-- =====================================================================

DROP DATABASE IF EXISTS parkwise;
CREATE DATABASE parkwise CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE parkwise;

-- ---------------------------------------------------------------------
-- 1. TABLES (12)
-- ---------------------------------------------------------------------

CREATE TABLE users (
  user_id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
  full_name      VARCHAR(100) NOT NULL,
  email          VARCHAR(120) NOT NULL,
  phone          VARCHAR(15)  NULL,
  password_hash  VARCHAR(255) NOT NULL,
  role           ENUM('USER','ADMIN') NOT NULL DEFAULT 'USER',
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id),
  CONSTRAINT uq_users_email UNIQUE (email)
) ENGINE=InnoDB;

CREATE TABLE vehicles (
  vehicle_id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id                INT UNSIGNED NOT NULL,
  reg_number             VARCHAR(15)  NOT NULL,            -- backend stores UPPERCASE, no spaces
  vehicle_type           ENUM('TWO_WHEELER','CAR') NOT NULL,
  is_ev                  TINYINT(1) NOT NULL DEFAULT 0,
  has_accessible_permit  TINYINT(1) NOT NULL DEFAULT 0,
  created_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (vehicle_id),
  CONSTRAINT uq_vehicles_reg UNIQUE (reg_number),
  CONSTRAINT fk_vehicles_user FOREIGN KEY (user_id) REFERENCES users (user_id),
  INDEX idx_vehicles_user (user_id)
) ENGINE=InnoDB;

CREATE TABLE zones (
  zone_id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
  zone_code    CHAR(1)      NOT NULL,
  zone_name    VARCHAR(60)  NOT NULL,
  floor_level  TINYINT      NOT NULL DEFAULT 0,
  PRIMARY KEY (zone_id),
  CONSTRAINT uq_zones_code UNIQUE (zone_code)
) ENGINE=InnoDB;

CREATE TABLE parking_slots (
  slot_id                 INT UNSIGNED NOT NULL AUTO_INCREMENT,
  zone_id                 INT UNSIGNED NOT NULL,
  slot_code               VARCHAR(8)   NOT NULL,           -- A-01, B-03 ...
  slot_type               ENUM('TWO_WHEELER','CAR') NOT NULL,
  is_ev_charger           TINYINT(1) NOT NULL DEFAULT 0,
  is_accessible           TINYINT(1) NOT NULL DEFAULT 0,
  is_premium              TINYINT(1) NOT NULL DEFAULT 0,
  distance_to_entrance_m  SMALLINT UNSIGNED NOT NULL,
  status                  ENUM('AVAILABLE','OCCUPIED','MAINTENANCE') NOT NULL DEFAULT 'AVAILABLE',
  PRIMARY KEY (slot_id),
  CONSTRAINT uq_slots_code UNIQUE (slot_code),
  CONSTRAINT fk_slots_zone FOREIGN KEY (zone_id) REFERENCES zones (zone_id),
  CONSTRAINT chk_slots_ev_car CHECK (is_ev_charger = 0 OR slot_type = 'CAR'),
  INDEX idx_slots_lookup (zone_id, status, slot_type)
) ENGINE=InnoDB;

CREATE TABLE tariff_rules (
  tariff_id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
  vehicle_type            ENUM('TWO_WHEELER','CAR') NOT NULL,
  is_premium              TINYINT(1) NOT NULL DEFAULT 0,
  hourly_rate             DECIMAL(8,2) NOT NULL,
  grace_minutes           SMALLINT UNSIGNED NOT NULL DEFAULT 10,
  min_charge              DECIMAL(8,2) NOT NULL DEFAULT 0,
  daily_cap               DECIMAL(8,2) NULL,
  overstay_fine_per_hour  DECIMAL(8,2) NOT NULL DEFAULT 0,
  effective_from          DATE NOT NULL,
  PRIMARY KEY (tariff_id),
  CONSTRAINT uq_tariff UNIQUE (vehicle_type, is_premium, effective_from),
  CONSTRAINT chk_tariff_rate CHECK (hourly_rate > 0),
  CONSTRAINT chk_tariff_min CHECK (min_charge >= 0),
  CONSTRAINT chk_tariff_cap CHECK (daily_cap IS NULL OR daily_cap >= min_charge)
) ENGINE=InnoDB;

CREATE TABLE reservations (
  reservation_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id         INT UNSIGNED NOT NULL,
  vehicle_id      INT UNSIGNED NOT NULL,
  slot_id         INT UNSIGNED NOT NULL,
  start_time      DATETIME NOT NULL,
  end_time        DATETIME NOT NULL,
  status          ENUM('PENDING','ACTIVE','COMPLETED','NO_SHOW','CANCELLED') NOT NULL DEFAULT 'PENDING',
  alloc_score     DECIMAL(5,4) NULL,                       -- score at booking time (explainability)
  alloc_reason    VARCHAR(255) NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (reservation_id),
  CONSTRAINT fk_res_user    FOREIGN KEY (user_id)    REFERENCES users (user_id),
  CONSTRAINT fk_res_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles (vehicle_id),
  CONSTRAINT fk_res_slot    FOREIGN KEY (slot_id)    REFERENCES parking_slots (slot_id),
  CONSTRAINT chk_res_window CHECK (end_time > start_time),
  INDEX idx_res_slot_time (slot_id, start_time, end_time),
  INDEX idx_res_status_start (status, start_time),
  INDEX idx_res_vehicle (vehicle_id, status)
) ENGINE=InnoDB;

CREATE TABLE parking_sessions (
  session_id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
  vehicle_id        INT UNSIGNED NOT NULL,
  slot_id           INT UNSIGNED NOT NULL,
  reservation_id    INT UNSIGNED NULL,
  tariff_id         INT UNSIGNED NOT NULL,                 -- tariff frozen at entry
  entry_time        DATETIME NOT NULL,
  exit_time         DATETIME NULL,
  duration_minutes  INT UNSIGNED NULL,
  billable_minutes  INT UNSIGNED NULL,
  amount_due        DECIMAL(10,2) NULL,
  status            ENUM('ACTIVE','CLOSED') NOT NULL DEFAULT 'ACTIVE',
  -- Generated keys: non-NULL only while ACTIVE.  UNIQUE on them = "at most one
  -- open session per slot / per vehicle" (MySQL allows many NULLs in a UNIQUE index).
  active_slot_key     INT UNSIGNED GENERATED ALWAYS AS (IF(status = 'ACTIVE', slot_id, NULL)) STORED,
  active_vehicle_key  INT UNSIGNED GENERATED ALWAYS AS (IF(status = 'ACTIVE', vehicle_id, NULL)) STORED,
  PRIMARY KEY (session_id),
  CONSTRAINT uq_one_active_per_slot    UNIQUE (active_slot_key),
  CONSTRAINT uq_one_active_per_vehicle UNIQUE (active_vehicle_key),
  CONSTRAINT uq_session_reservation    UNIQUE (reservation_id),
  CONSTRAINT fk_sess_vehicle FOREIGN KEY (vehicle_id)     REFERENCES vehicles (vehicle_id),
  CONSTRAINT fk_sess_slot    FOREIGN KEY (slot_id)        REFERENCES parking_slots (slot_id),
  CONSTRAINT fk_sess_res     FOREIGN KEY (reservation_id) REFERENCES reservations (reservation_id),
  CONSTRAINT fk_sess_tariff  FOREIGN KEY (tariff_id)      REFERENCES tariff_rules (tariff_id),
  CONSTRAINT chk_sess_times  CHECK (exit_time IS NULL OR exit_time >= entry_time),
  CONSTRAINT chk_sess_state  CHECK ((status = 'ACTIVE' AND exit_time IS NULL)
                                 OR (status = 'CLOSED' AND exit_time IS NOT NULL)),
  INDEX idx_sess_entry (entry_time),
  INDEX idx_sess_vehicle_entry (vehicle_id, entry_time)
) ENGINE=InnoDB;

CREATE TABLE payments (
  payment_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id  INT UNSIGNED NOT NULL,
  amount      DECIMAL(10,2) NOT NULL,
  method      ENUM('CASH','UPI','CARD','WAIVED') NULL,
  status      ENUM('PENDING','PAID','FAILED','REFUNDED') NOT NULL DEFAULT 'PENDING',
  txn_ref     VARCHAR(40) NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paid_at     DATETIME NULL,
  PRIMARY KEY (payment_id),
  CONSTRAINT fk_pay_session FOREIGN KEY (session_id) REFERENCES parking_sessions (session_id),
  CONSTRAINT chk_pay_amount CHECK (amount >= 0),
  CONSTRAINT chk_pay_paid   CHECK (status <> 'PAID' OR paid_at IS NOT NULL),
  INDEX idx_pay_session (session_id, status),
  INDEX idx_pay_status_paid (status, paid_at)
) ENGINE=InnoDB;

CREATE TABLE violations (
  violation_id    INT UNSIGNED NOT NULL AUTO_INCREMENT,
  vehicle_id      INT UNSIGNED NOT NULL,
  session_id      INT UNSIGNED NULL,
  reservation_id  INT UNSIGNED NULL,
  violation_type  ENUM('OVERSTAY','NO_SHOW','WRONG_SLOT','UNAUTHORIZED_BAY') NOT NULL,
  fine_amount     DECIMAL(8,2) NOT NULL DEFAULT 0,
  status          ENUM('OPEN','PAID','WAIVED') NOT NULL DEFAULT 'OPEN',
  detected_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  notes           VARCHAR(255) NULL,
  PRIMARY KEY (violation_id),
  -- One violation of each type per session / per reservation => scheduler is idempotent.
  CONSTRAINT uq_viol_session     UNIQUE (session_id, violation_type),
  CONSTRAINT uq_viol_reservation UNIQUE (reservation_id, violation_type),
  CONSTRAINT fk_viol_vehicle FOREIGN KEY (vehicle_id)     REFERENCES vehicles (vehicle_id),
  CONSTRAINT fk_viol_session FOREIGN KEY (session_id)     REFERENCES parking_sessions (session_id),
  CONSTRAINT fk_viol_res     FOREIGN KEY (reservation_id) REFERENCES reservations (reservation_id),
  CONSTRAINT chk_viol_fine   CHECK (fine_amount >= 0),
  CONSTRAINT chk_viol_target CHECK (session_id IS NOT NULL OR reservation_id IS NOT NULL),
  INDEX idx_viol_status (status, detected_at)
) ENGINE=InnoDB;

CREATE TABLE occupancy_snapshots (
  snapshot_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  captured_at     DATETIME NOT NULL,
  zone_id         INT UNSIGNED NOT NULL,
  usable_slots    INT UNSIGNED NOT NULL,                   -- slots not under maintenance
  occupied_slots  INT UNSIGNED NOT NULL,
  PRIMARY KEY (snapshot_id),
  CONSTRAINT uq_snapshot UNIQUE (captured_at, zone_id),
  CONSTRAINT fk_snap_zone FOREIGN KEY (zone_id) REFERENCES zones (zone_id),
  CONSTRAINT chk_snap_counts CHECK (occupied_slots <= usable_slots)
) ENGINE=InnoDB;

CREATE TABLE audit_logs (
  log_id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  actor_user_id  INT UNSIGNED NULL,                        -- from @app_user_id set by Flask
  action         VARCHAR(40) NOT NULL,
  entity         VARCHAR(40) NOT NULL,
  entity_id      INT UNSIGNED NULL,
  old_value      JSON NULL,
  new_value      JSON NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (log_id),
  CONSTRAINT fk_audit_user FOREIGN KEY (actor_user_id) REFERENCES users (user_id) ON DELETE SET NULL,
  INDEX idx_audit_entity (entity, entity_id)
) ENGINE=InnoDB;

CREATE TABLE system_settings (
  setting_key    VARCHAR(40)  NOT NULL,
  setting_value  VARCHAR(40)  NOT NULL,
  description    VARCHAR(200) NOT NULL,
  PRIMARY KEY (setting_key)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 2. FUNCTIONS, TRIGGERS, PROCEDURES, EVENTS
-- ---------------------------------------------------------------------
DELIMITER $$

-- ===== Functions ====================================================

CREATE FUNCTION fn_setting_num(p_key VARCHAR(40)) RETURNS DECIMAL(12,4)
READS SQL DATA
BEGIN
  DECLARE v DECIMAL(12,4) DEFAULT NULL;
  SELECT CAST(setting_value AS DECIMAL(12,4)) INTO v
    FROM system_settings WHERE setting_key = p_key;
  IF v IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Missing system setting';
  END IF;
  RETURN v;
END$$

-- Minutes that are actually charged (duration minus grace, never negative)
CREATE FUNCTION fn_billable_minutes(p_tariff_id INT UNSIGNED, p_duration_minutes INT) RETURNS INT
READS SQL DATA
BEGIN
  DECLARE v_grace INT DEFAULT NULL;
  SELECT grace_minutes INTO v_grace FROM tariff_rules WHERE tariff_id = p_tariff_id;
  IF v_grace IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Tariff not found';
  END IF;
  RETURN GREATEST(p_duration_minutes - v_grace, 0);
END$$

-- THE billing rule:  started hourly blocks of (duration - grace) x rate,
-- raised to min_charge, limited to daily_cap per started 24h.
CREATE FUNCTION fn_calc_amount(p_tariff_id INT UNSIGNED, p_duration_minutes INT) RETURNS DECIMAL(10,2)
READS SQL DATA
BEGIN
  DECLARE v_rate DECIMAL(8,2) DEFAULT NULL;
  DECLARE v_min  DECIMAL(8,2);
  DECLARE v_cap  DECIMAL(8,2);
  DECLARE v_billable INT;
  DECLARE v_amt DECIMAL(10,2);

  SELECT hourly_rate, min_charge, daily_cap INTO v_rate, v_min, v_cap
    FROM tariff_rules WHERE tariff_id = p_tariff_id;
  IF v_rate IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Tariff not found';
  END IF;
  IF p_duration_minutes < 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Negative duration';
  END IF;

  SET v_billable = fn_billable_minutes(p_tariff_id, p_duration_minutes);
  IF v_billable = 0 THEN
    RETURN 0;                                              -- inside grace period => free
  END IF;

  SET v_amt = GREATEST(CEIL(v_billable / 60.0) * v_rate, v_min);
  IF v_cap IS NOT NULL THEN
    SET v_amt = LEAST(v_amt, v_cap * CEIL(p_duration_minutes / 1440.0));
  END IF;
  RETURN v_amt;
END$$

-- ===== Triggers =====================================================

-- Session safety net (even raw INSERTs cannot break these rules)
CREATE TRIGGER trg_sessions_bi BEFORE INSERT ON parking_sessions
FOR EACH ROW
BEGIN
  DECLARE v_stype VARCHAR(12);
  DECLARE v_status VARCHAR(12);
  DECLARE v_vtype VARCHAR(12);
  IF NEW.status = 'ACTIVE' THEN
    SELECT slot_type, status INTO v_stype, v_status FROM parking_slots WHERE slot_id = NEW.slot_id;
    SELECT vehicle_type INTO v_vtype FROM vehicles WHERE vehicle_id = NEW.vehicle_id;
    IF v_status = 'MAINTENANCE' THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is under maintenance';
    END IF;
    IF v_stype <> v_vtype THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle type does not match slot type';
    END IF;
  END IF;
END$$

CREATE TRIGGER trg_sessions_ai AFTER INSERT ON parking_sessions
FOR EACH ROW
BEGIN
  IF NEW.status = 'ACTIVE' THEN
    UPDATE parking_slots SET status = 'OCCUPIED' WHERE slot_id = NEW.slot_id;
  END IF;
END$$

CREATE TRIGGER trg_sessions_au AFTER UPDATE ON parking_sessions
FOR EACH ROW
BEGIN
  IF OLD.status = 'ACTIVE' AND NEW.status = 'CLOSED' THEN
    UPDATE parking_slots SET status = 'AVAILABLE'
     WHERE slot_id = NEW.slot_id AND status = 'OCCUPIED';
  END IF;
END$$

-- Reservation state machine
CREATE TRIGGER trg_reservations_bu BEFORE UPDATE ON reservations
FOR EACH ROW
BEGIN
  IF NEW.status <> OLD.status THEN
    IF NOT ( (OLD.status = 'PENDING' AND NEW.status IN ('ACTIVE','NO_SHOW','CANCELLED'))
          OR (OLD.status = 'ACTIVE'  AND NEW.status = 'COMPLETED') ) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid reservation status transition';
    END IF;
  END IF;
END$$

-- Slot status guard: cannot free / disable a slot that has a vehicle in it
CREATE TRIGGER trg_slots_bu BEFORE UPDATE ON parking_slots
FOR EACH ROW
BEGIN
  IF NEW.status <> OLD.status AND NEW.status IN ('AVAILABLE','MAINTENANCE') THEN
    IF EXISTS (SELECT 1 FROM parking_sessions WHERE slot_id = NEW.slot_id AND status = 'ACTIVE') THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot has an active parking session';
    END IF;
  END IF;
END$$

-- Audit: maintenance toggles
CREATE TRIGGER trg_slots_au AFTER UPDATE ON parking_slots
FOR EACH ROW
BEGIN
  IF (OLD.status = 'MAINTENANCE') <> (NEW.status = 'MAINTENANCE') THEN
    INSERT INTO audit_logs (actor_user_id, action, entity, entity_id, old_value, new_value)
    VALUES (@app_user_id, 'SLOT_MAINTENANCE', 'parking_slots', NEW.slot_id,
            JSON_OBJECT('status', OLD.status), JSON_OBJECT('status', NEW.status));
  END IF;
END$$

-- Audit: tariff changes
CREATE TRIGGER trg_tariff_au AFTER UPDATE ON tariff_rules
FOR EACH ROW
BEGIN
  INSERT INTO audit_logs (actor_user_id, action, entity, entity_id, old_value, new_value)
  VALUES (@app_user_id, 'TARIFF_UPDATE', 'tariff_rules', NEW.tariff_id,
          JSON_OBJECT('hourly_rate', OLD.hourly_rate, 'grace_minutes', OLD.grace_minutes,
                      'min_charge', OLD.min_charge, 'daily_cap', OLD.daily_cap,
                      'overstay_fine_per_hour', OLD.overstay_fine_per_hour),
          JSON_OBJECT('hourly_rate', NEW.hourly_rate, 'grace_minutes', NEW.grace_minutes,
                      'min_charge', NEW.min_charge, 'daily_cap', NEW.daily_cap,
                      'overstay_fine_per_hour', NEW.overstay_fine_per_hour));
END$$

-- ===== Procedures ===================================================

-- Eligibility rules shared by reservation and entry (signals on failure)
CREATE PROCEDURE sp_assert_eligible(IN p_vehicle_id INT UNSIGNED, IN p_slot_id INT UNSIGNED)
BEGIN
  DECLARE v_vtype  VARCHAR(12) DEFAULT NULL;
  DECLARE v_stype  VARCHAR(12) DEFAULT NULL;
  DECLARE v_status VARCHAR(12);
  DECLARE v_is_ev, v_perm, v_acc, v_chg TINYINT;

  SELECT vehicle_type, is_ev, has_accessible_permit INTO v_vtype, v_is_ev, v_perm
    FROM vehicles WHERE vehicle_id = p_vehicle_id;
  IF v_vtype IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle not found';
  END IF;

  SELECT slot_type, is_accessible, is_ev_charger, status INTO v_stype, v_acc, v_chg, v_status
    FROM parking_slots WHERE slot_id = p_slot_id;
  IF v_stype IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot not found';
  END IF;

  IF v_status = 'MAINTENANCE' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is under maintenance';
  END IF;
  IF v_stype <> v_vtype THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle type does not match slot type';
  END IF;
  IF v_acc = 1 AND v_perm = 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Accessible bay requires an accessibility permit';
  END IF;
  IF v_chg = 1 AND v_is_ev = 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'EV charging bay is reserved for EVs';
  END IF;
END$$

-- Best-fit slot recommendation: hard constraints in WHERE, then a weighted
-- sum of min-max normalised factors.  Weights live in system_settings.
CREATE PROCEDURE sp_recommend_slots(IN p_vehicle_id INT UNSIGNED, IN p_start DATETIME, IN p_end DATETIME)
BEGIN
  DECLARE v_vtype VARCHAR(12) DEFAULT NULL;
  DECLARE v_is_ev, v_perm TINYINT;
  DECLARE v_w_dist, v_w_ev, v_w_acc, v_w_cost DECIMAL(12,4);
  DECLARE v_buffer INT;

  IF p_end <= p_start THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'End time must be after start time';
  END IF;

  SELECT vehicle_type, is_ev, has_accessible_permit INTO v_vtype, v_is_ev, v_perm
    FROM vehicles WHERE vehicle_id = p_vehicle_id;
  IF v_vtype IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle not found';
  END IF;

  SET v_w_dist = fn_setting_num('w_distance');
  SET v_w_ev   = fn_setting_num('w_ev');
  SET v_w_acc  = fn_setting_num('w_accessible');
  SET v_w_cost = fn_setting_num('w_cost');
  SET v_buffer = fn_setting_num('walkin_buffer_minutes');

  SELECT c.slot_id, c.slot_code, c.zone_name, c.distance_to_entrance_m,
         c.is_ev_charger, c.is_accessible, c.is_premium,
         ROUND(v_w_dist * c.dist_score + v_w_ev * c.ev_score
             + v_w_acc * c.acc_score + v_w_cost * c.cost_score, 4) AS score,
         CONCAT_WS('; ',
           CONCAT(c.distance_to_entrance_m, ' m from entrance'),
           IF(v_is_ev = 1 AND c.is_ev_charger = 1, 'EV charger available', NULL),
           IF(v_perm = 1 AND c.is_accessible = 1, 'accessible bay', NULL),
           IF(c.is_premium = 1, 'premium rate', 'standard rate')) AS reason
  FROM (
    SELECT s.slot_id, s.slot_code, z.zone_name, s.distance_to_entrance_m,
           s.is_ev_charger, s.is_accessible, s.is_premium,
           COALESCE(1 - (s.distance_to_entrance_m - MIN(s.distance_to_entrance_m) OVER ())
                      / NULLIF(MAX(s.distance_to_entrance_m) OVER () - MIN(s.distance_to_entrance_m) OVER (), 0), 1) AS dist_score,
           IF(v_is_ev = 1, s.is_ev_charger, 1)  AS ev_score,
           IF(v_perm = 1,  s.is_accessible, 1)  AS acc_score,
           IF(s.is_premium = 1, 0, 1)           AS cost_score
    FROM parking_slots s
    JOIN zones z ON z.zone_id = s.zone_id
    WHERE s.status <> 'MAINTENANCE'
      AND s.slot_type = v_vtype
      AND (s.is_accessible = 0 OR v_perm = 1)              -- accessible bays: permit holders only
      AND (s.is_ev_charger = 0 OR v_is_ev = 1)             -- charger bays: EVs only
      AND NOT EXISTS (SELECT 1 FROM reservations r
                       WHERE r.slot_id = s.slot_id
                         AND r.status IN ('PENDING','ACTIVE')
                         AND r.start_time < p_end AND r.end_time > p_start)
      AND (p_start > NOW() + INTERVAL v_buffer MINUTE
           OR NOT EXISTS (SELECT 1 FROM parking_sessions ps
                           WHERE ps.slot_id = s.slot_id AND ps.status = 'ACTIVE'))
  ) c
  ORDER BY score DESC, c.distance_to_entrance_m ASC, c.slot_code ASC
  LIMIT 5;
END$$

-- Concurrency-safe booking.  Serialisation point = row lock on the slot.
CREATE PROCEDURE sp_create_reservation(
  IN p_user_id INT UNSIGNED, IN p_vehicle_id INT UNSIGNED, IN p_slot_id INT UNSIGNED,
  IN p_start DATETIME, IN p_end DATETIME,
  IN p_score DECIMAL(5,4), IN p_reason VARCHAR(255),
  OUT o_reservation_id INT UNSIGNED)
BEGIN
  DECLARE v_owner INT UNSIGNED DEFAULT NULL;
  DECLARE v_slot  INT UNSIGNED DEFAULT NULL;
  DECLARE v_conflicts INT DEFAULT 0;
  DECLARE v_buffer INT;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  SET o_reservation_id = NULL;
  SET v_buffer = fn_setting_num('walkin_buffer_minutes');
  IF p_end <= p_start THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'End time must be after start time';
  END IF;
  IF p_start < NOW() - INTERVAL 1 MINUTE THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Reservation cannot start in the past';
  END IF;
  IF TIMESTAMPDIFF(HOUR, p_start, p_end) > 24 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Reservation cannot exceed 24 hours';
  END IF;

  START TRANSACTION;

  -- 1) Lock the slot row FIRST. Concurrent bookings of this slot queue here.
  SELECT slot_id INTO v_slot FROM parking_slots WHERE slot_id = p_slot_id FOR UPDATE;
  IF v_slot IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot not found';
  END IF;

  SELECT user_id INTO v_owner FROM vehicles WHERE vehicle_id = p_vehicle_id;
  IF v_owner IS NULL OR v_owner <> p_user_id THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle does not belong to this user';
  END IF;

  CALL sp_assert_eligible(p_vehicle_id, p_slot_id);

  -- 2) Overlap checks use locking reads (FOR UPDATE) so they see the latest
  --    committed data even under REPEATABLE READ.
  SELECT COUNT(*) INTO v_conflicts FROM reservations
   WHERE slot_id = p_slot_id AND status IN ('PENDING','ACTIVE')
     AND start_time < p_end AND end_time > p_start
   FOR UPDATE;
  IF v_conflicts > 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot already booked for that period';
  END IF;

  SELECT COUNT(*) INTO v_conflicts FROM reservations
   WHERE vehicle_id = p_vehicle_id AND status IN ('PENDING','ACTIVE')
     AND start_time < p_end AND end_time > p_start
   FOR UPDATE;
  IF v_conflicts > 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle already has a reservation in that period';
  END IF;

  IF p_start <= NOW() + INTERVAL v_buffer MINUTE THEN
    SELECT COUNT(*) INTO v_conflicts FROM parking_sessions
     WHERE slot_id = p_slot_id AND status = 'ACTIVE' FOR UPDATE;
    IF v_conflicts > 0 THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is currently occupied';
    END IF;
  END IF;

  INSERT INTO reservations (user_id, vehicle_id, slot_id, start_time, end_time, alloc_score, alloc_reason)
  VALUES (p_user_id, p_vehicle_id, p_slot_id, p_start, p_end, p_score, p_reason);
  SET o_reservation_id = LAST_INSERT_ID();

  COMMIT;
END$$

CREATE PROCEDURE sp_cancel_reservation(IN p_reservation_id INT UNSIGNED, IN p_user_id INT UNSIGNED)
BEGIN
  DECLARE v_owner INT UNSIGNED DEFAULT NULL;
  DECLARE v_status VARCHAR(12) DEFAULT NULL;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  START TRANSACTION;
  SELECT user_id, status INTO v_owner, v_status FROM reservations
   WHERE reservation_id = p_reservation_id FOR UPDATE;
  IF v_owner IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Reservation not found';
  END IF;
  IF v_owner <> p_user_id THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Not your reservation';
  END IF;
  IF v_status <> 'PENDING' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only PENDING reservations can be cancelled';
  END IF;
  UPDATE reservations SET status = 'CANCELLED' WHERE reservation_id = p_reservation_id;
  COMMIT;
END$$

-- Vehicle enters a slot. p_entry_time NULL = now (non-NULL only for tests/simulation).
CREATE PROCEDURE sp_vehicle_entry(
  IN p_vehicle_id INT UNSIGNED, IN p_slot_id INT UNSIGNED, IN p_entry_time DATETIME,
  OUT o_session_id INT UNSIGNED)
BEGIN
  DECLARE v_now DATETIME;
  DECLARE v_slot INT UNSIGNED DEFAULT NULL;
  DECLARE v_status VARCHAR(12);
  DECLARE v_prem, v_dummy TINYINT;
  DECLARE v_vtype VARCHAR(12);
  DECLARE v_res_id INT UNSIGNED DEFAULT NULL;
  DECLARE v_tariff INT UNSIGNED DEFAULT NULL;
  DECLARE v_early, v_buffer INT;
  DECLARE EXIT HANDLER FOR 1062
  BEGIN
    ROLLBACK;
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot or vehicle already has an active session';
  END;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  SET o_session_id = NULL;
  SET v_now    = COALESCE(p_entry_time, NOW());
  SET v_early  = fn_setting_num('early_entry_minutes');
  SET v_buffer = fn_setting_num('walkin_buffer_minutes');

  START TRANSACTION;

  SELECT slot_id, status, is_premium INTO v_slot, v_status, v_prem
    FROM parking_slots WHERE slot_id = p_slot_id FOR UPDATE;
  IF v_slot IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot not found';
  END IF;
  IF v_status = 'OCCUPIED' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is occupied';
  END IF;

  CALL sp_assert_eligible(p_vehicle_id, p_slot_id);
  SELECT vehicle_type INTO v_vtype FROM vehicles WHERE vehicle_id = p_vehicle_id;

  -- Does this vehicle hold a reservation for THIS slot that covers "now"?
  SELECT reservation_id INTO v_res_id FROM reservations
   WHERE vehicle_id = p_vehicle_id AND slot_id = p_slot_id AND status = 'PENDING'
     AND v_now >= start_time - INTERVAL v_early MINUTE AND v_now < end_time
   ORDER BY start_time LIMIT 1 FOR UPDATE;

  IF v_res_id IS NULL THEN
    -- Walk-in. Must not use a slot reserved for someone else, nor ignore own booking elsewhere.
    IF EXISTS (SELECT 1 FROM reservations
                WHERE slot_id = p_slot_id AND status = 'PENDING'
                  AND start_time < v_now + INTERVAL v_buffer MINUTE AND end_time > v_now) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is reserved for another vehicle';
    END IF;
    IF EXISTS (SELECT 1 FROM reservations
                WHERE vehicle_id = p_vehicle_id AND status = 'PENDING'
                  AND v_now >= start_time - INTERVAL v_early MINUTE AND v_now < end_time) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle has a reservation for a different slot';
    END IF;
  END IF;

  SELECT tariff_id INTO v_tariff FROM tariff_rules
   WHERE vehicle_type = v_vtype AND is_premium = v_prem AND effective_from <= DATE(v_now)
   ORDER BY effective_from DESC LIMIT 1;
  IF v_tariff IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No tariff configured for this slot/vehicle';
  END IF;

  INSERT INTO parking_sessions (vehicle_id, slot_id, reservation_id, tariff_id, entry_time)
  VALUES (p_vehicle_id, p_slot_id, v_res_id, v_tariff, v_now);
  SET o_session_id = LAST_INSERT_ID();

  IF v_res_id IS NOT NULL THEN
    UPDATE reservations SET status = 'ACTIVE' WHERE reservation_id = v_res_id;
  END IF;

  COMMIT;
END$$

-- Vehicle exits: bill, payment row, close reservation, overstay fine, free slot (trigger).
-- p_exit_time NULL = now (non-NULL only for tests/simulation; Flask always passes NULL).
CREATE PROCEDURE sp_vehicle_exit(
  IN p_session_id INT UNSIGNED, IN p_exit_time DATETIME, OUT o_amount DECIMAL(10,2))
BEGIN
  DECLARE v_vehicle, v_res, v_tariff INT UNSIGNED DEFAULT NULL;
  DECLARE v_entry, v_exit, v_res_end DATETIME;
  DECLARE v_status VARCHAR(10) DEFAULT NULL;
  DECLARE v_dur, v_over, v_grace INT;
  DECLARE v_fine_rate DECIMAL(8,2);
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  SET o_amount = NULL;
  START TRANSACTION;

  SELECT vehicle_id, reservation_id, tariff_id, entry_time, status
    INTO v_vehicle, v_res, v_tariff, v_entry, v_status
    FROM parking_sessions WHERE session_id = p_session_id FOR UPDATE;
  IF v_status IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session not found';
  END IF;
  IF v_status <> 'ACTIVE' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session is already closed';
  END IF;

  SET v_exit = COALESCE(p_exit_time, NOW());
  IF v_exit < v_entry THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Exit time is before entry time';
  END IF;

  SET v_dur    = TIMESTAMPDIFF(MINUTE, v_entry, v_exit);
  SET o_amount = fn_calc_amount(v_tariff, v_dur);

  UPDATE parking_sessions
     SET exit_time = v_exit, duration_minutes = v_dur,
         billable_minutes = fn_billable_minutes(v_tariff, v_dur),
         amount_due = o_amount, status = 'CLOSED'
   WHERE session_id = p_session_id;                        -- trigger frees the slot

  INSERT INTO payments (session_id, amount, method, status, paid_at)
  VALUES (p_session_id, o_amount,
          IF(o_amount = 0, 'WAIVED', NULL),
          IF(o_amount = 0, 'PAID', 'PENDING'),
          IF(o_amount = 0, v_exit, NULL));

  IF v_res IS NOT NULL THEN
    SELECT end_time INTO v_res_end FROM reservations WHERE reservation_id = v_res FOR UPDATE;
    UPDATE reservations SET status = 'COMPLETED' WHERE reservation_id = v_res;

    SELECT grace_minutes, overstay_fine_per_hour INTO v_grace, v_fine_rate
      FROM tariff_rules WHERE tariff_id = v_tariff;
    SET v_over = TIMESTAMPDIFF(MINUTE, v_res_end, v_exit) - v_grace;
    IF v_over > 0 THEN
      INSERT INTO violations (vehicle_id, session_id, reservation_id, violation_type, fine_amount, notes)
      VALUES (v_vehicle, p_session_id, v_res, 'OVERSTAY',
              CEIL(v_over / 60.0) * v_fine_rate,
              CONCAT('Stayed ', v_over, ' min beyond booked end + grace'))
      ON DUPLICATE KEY UPDATE fine_amount = VALUES(fine_amount), notes = VALUES(notes);
    END IF;
  END IF;

  COMMIT;
END$$

-- Simulated payment. p_success = 0 simulates a failure; a fresh PENDING row allows retry.
CREATE PROCEDURE sp_record_payment(IN p_session_id INT UNSIGNED, IN p_method VARCHAR(10), IN p_success TINYINT)
BEGIN
  DECLARE v_pid INT UNSIGNED DEFAULT NULL;
  DECLARE v_amt DECIMAL(10,2);
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  START TRANSACTION;
  SELECT payment_id, amount INTO v_pid, v_amt FROM payments
   WHERE session_id = p_session_id AND status = 'PENDING'
   ORDER BY payment_id DESC LIMIT 1 FOR UPDATE;
  IF v_pid IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No pending payment for this session';
  END IF;

  IF p_success = 1 THEN
    UPDATE payments SET status = 'PAID', method = p_method, paid_at = NOW() WHERE payment_id = v_pid;
  ELSE
    UPDATE payments SET status = 'FAILED', method = p_method WHERE payment_id = v_pid;
    INSERT INTO payments (session_id, amount, status) VALUES (p_session_id, v_amt, 'PENDING');
  END IF;
  COMMIT;
END$$

-- Admin: record a manually observed violation (software-only demo => simulated)
CREATE PROCEDURE sp_log_violation(
  IN p_session_id INT UNSIGNED, IN p_type VARCHAR(20), IN p_fine DECIMAL(8,2), IN p_notes VARCHAR(255))
BEGIN
  DECLARE v_vehicle INT UNSIGNED DEFAULT NULL;
  DECLARE EXIT HANDLER FOR 1062
  BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This violation is already recorded for the session';
  END;

  SELECT vehicle_id INTO v_vehicle FROM parking_sessions WHERE session_id = p_session_id;
  IF v_vehicle IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session not found';
  END IF;
  INSERT INTO violations (vehicle_id, session_id, violation_type, fine_amount, notes)
  VALUES (v_vehicle, p_session_id, p_type, p_fine, p_notes);
END$$

-- Scheduler job 1: PENDING reservations past start + grace become NO_SHOW (+ violation row)
CREATE PROCEDURE sp_release_no_shows()
BEGIN
  DECLARE v_grace INT;
  DECLARE v_fine DECIMAL(8,2);
  SET v_grace = fn_setting_num('noshow_grace_minutes');
  SET v_fine  = fn_setting_num('noshow_fine');

  UPDATE reservations SET status = 'NO_SHOW'
   WHERE status = 'PENDING' AND start_time + INTERVAL v_grace MINUTE < NOW();

  INSERT INTO violations (vehicle_id, reservation_id, violation_type, fine_amount, notes)
  SELECT r.vehicle_id, r.reservation_id, 'NO_SHOW', v_fine, 'Did not arrive within grace period'
    FROM reservations r
   WHERE r.status = 'NO_SHOW'
     AND NOT EXISTS (SELECT 1 FROM violations v
                      WHERE v.reservation_id = r.reservation_id AND v.violation_type = 'NO_SHOW');
END$$

-- Scheduler job 2: flag ACTIVE reserved sessions that are past booked end + grace
CREATE PROCEDURE sp_flag_overstays()
BEGIN
  INSERT INTO violations (vehicle_id, session_id, reservation_id, violation_type, fine_amount, notes)
  SELECT ps.vehicle_id, ps.session_id, ps.reservation_id, 'OVERSTAY',
         GREATEST(CEIL((TIMESTAMPDIFF(MINUTE, r.end_time, NOW()) - t.grace_minutes) / 60.0), 0)
           * t.overstay_fine_per_hour,
         'Flagged by scheduler; final fine is recalculated at exit'
    FROM parking_sessions ps
    JOIN reservations r ON r.reservation_id = ps.reservation_id
    JOIN tariff_rules t ON t.tariff_id = ps.tariff_id
   WHERE ps.status = 'ACTIVE'
     AND r.end_time + INTERVAL t.grace_minutes MINUTE < NOW()
     AND NOT EXISTS (SELECT 1 FROM violations v
                      WHERE v.session_id = ps.session_id AND v.violation_type = 'OVERSTAY');
END$$

-- Scheduler job 3: occupancy snapshot per zone, aligned to 15 minutes
CREATE PROCEDURE sp_take_snapshot(IN p_time DATETIME)
BEGIN
  DECLARE v_ts DATETIME;
  SET v_ts = COALESCE(p_time, NOW());
  SET v_ts = v_ts - INTERVAL SECOND(v_ts) SECOND - INTERVAL (MINUTE(v_ts) % 15) MINUTE;

  INSERT INTO occupancy_snapshots (captured_at, zone_id, usable_slots, occupied_slots)
  SELECT v_ts, z.zone_id,
         SUM(s.status <> 'MAINTENANCE'),
         SUM(s.status = 'OCCUPIED')
    FROM zones z JOIN parking_slots s ON s.zone_id = z.zone_id
   GROUP BY z.zone_id
  ON DUPLICATE KEY UPDATE usable_slots = VALUES(usable_slots), occupied_slots = VALUES(occupied_slots);
END$$

-- Synthetic history for the analytics demo (closed sessions, payments, a few violations,
-- 30-minute snapshots).  Slot-by-slot sequential stays => no overlapping stays per slot.
CREATE PROCEDURE sp_seed_history(IN p_days INT)
BEGIN
  DECLARE d INT;
  DECLARE i, v_n INT;
  DECLARE v_day DATE;
  DECLARE v_weekend DECIMAL(3,1);
  DECLARE v_slot, v_veh, v_tariff, v_sid INT UNSIGNED;
  DECLARE v_stype VARCHAR(12);
  DECLARE v_chg, v_acc, v_prem TINYINT;
  DECLARE v_t, v_exit, v_eod, v_ts DATETIME;
  DECLARE v_hr, v_dur, m INT;
  DECLARE v_p DECIMAL(4,2);
  DECLARE v_amt DECIMAL(10,2);

  DROP TEMPORARY TABLE IF EXISTS tmp_seed_slots;
  CREATE TEMPORARY TABLE tmp_seed_slots AS
    SELECT slot_id, slot_type, is_ev_charger, is_accessible, is_premium
      FROM parking_slots WHERE status <> 'MAINTENANCE';
  SELECT COUNT(*) INTO v_n FROM tmp_seed_slots;

  SET d = p_days;
  WHILE d >= 1 DO
    SET v_day = DATE_SUB(CURDATE(), INTERVAL d DAY);
    SET v_weekend = IF(DAYOFWEEK(v_day) IN (1, 7), 0.5, 1.0);
    SET i = 0;
    WHILE i < v_n DO
      SELECT slot_id, slot_type, is_ev_charger, is_accessible, is_premium
        INTO v_slot, v_stype, v_chg, v_acc, v_prem
        FROM tmp_seed_slots ORDER BY slot_id LIMIT i, 1;
      SET v_tariff = NULL;
      SELECT tariff_id INTO v_tariff FROM tariff_rules
       WHERE vehicle_type = v_stype AND is_premium = v_prem AND effective_from <= v_day
       ORDER BY effective_from DESC LIMIT 1;

      SET v_t   = TIMESTAMP(v_day, '07:00:00') + INTERVAL FLOOR(RAND() * 120) MINUTE;
      SET v_eod = TIMESTAMP(v_day, '20:00:00');
      WHILE v_t < v_eod DO
        SET v_hr = HOUR(v_t);
        SET v_p = v_weekend * CASE WHEN v_hr BETWEEN 9 AND 11 THEN 0.90
                                   WHEN v_hr BETWEEN 12 AND 16 THEN 0.60
                                   ELSE 0.30 END;
        IF v_tariff IS NOT NULL AND RAND() < v_p THEN
          SET v_dur = 30 + FLOOR(RAND() * 211);              -- 30..240 minutes
          SET v_veh = NULL;
          SELECT vehicle_id INTO v_veh FROM vehicles
           WHERE vehicle_type = v_stype
             AND (v_chg = 0 OR is_ev = 1)
             AND (v_acc = 0 OR has_accessible_permit = 1)
           ORDER BY RAND() LIMIT 1;
          IF v_veh IS NOT NULL THEN
            SET v_exit = v_t + INTERVAL v_dur MINUTE;
            SET v_amt  = fn_calc_amount(v_tariff, v_dur);
            INSERT INTO parking_sessions
              (vehicle_id, slot_id, tariff_id, entry_time, exit_time,
               duration_minutes, billable_minutes, amount_due, status)
            VALUES (v_veh, v_slot, v_tariff, v_t, v_exit,
                    v_dur, fn_billable_minutes(v_tariff, v_dur), v_amt, 'CLOSED');
            SET v_sid = LAST_INSERT_ID();
            INSERT INTO payments (session_id, amount, method, status, paid_at)
            VALUES (v_sid, v_amt,
                    IF(v_amt = 0, 'WAIVED', ELT(1 + FLOOR(RAND() * 3), 'UPI', 'CASH', 'CARD')),
                    'PAID', v_exit);
            IF RAND() < 0.03 THEN
              INSERT INTO violations (vehicle_id, session_id, violation_type, fine_amount, status, detected_at, notes)
              VALUES (v_veh, v_sid, 'WRONG_SLOT', 50.00, 'PAID', v_exit, 'Synthetic history');
            END IF;
          END IF;
          SET v_t = v_t + INTERVAL (v_dur + 5 + FLOOR(RAND() * 25)) MINUTE;
        ELSE
          SET v_t = v_t + INTERVAL 30 MINUTE;
        END IF;
      END WHILE;
      SET i = i + 1;
    END WHILE;

    -- 30-minute snapshots 06:00 .. 22:00 for the day, derived from the sessions just created
    SET m = 360;
    WHILE m <= 1320 DO
      SET v_ts = TIMESTAMP(v_day) + INTERVAL m MINUTE;
      INSERT INTO occupancy_snapshots (captured_at, zone_id, usable_slots, occupied_slots)
      SELECT v_ts, z.zone_id,
             (SELECT COUNT(*) FROM parking_slots s2
               WHERE s2.zone_id = z.zone_id AND s2.status <> 'MAINTENANCE'),
             (SELECT COUNT(*) FROM parking_sessions ps
                JOIN parking_slots s3 ON s3.slot_id = ps.slot_id
               WHERE s3.zone_id = z.zone_id AND ps.entry_time <= v_ts AND ps.exit_time > v_ts)
        FROM zones z
      ON DUPLICATE KEY UPDATE usable_slots = VALUES(usable_slots), occupied_slots = VALUES(occupied_slots);
      SET m = m + 30;
    END WHILE;

    SET d = d - 1;
  END WHILE;
  DROP TEMPORARY TABLE IF EXISTS tmp_seed_slots;
END$$

DELIMITER ;

-- ---------------------------------------------------------------------
-- 3. VIEWS
-- ---------------------------------------------------------------------

-- Live board: derives RESERVED (a PENDING booking starting soon / in progress)
CREATE VIEW v_slot_live_status AS
SELECT s.slot_id, s.slot_code, z.zone_id, z.zone_code, z.zone_name, s.slot_type,
       s.is_ev_charger, s.is_accessible, s.is_premium, s.distance_to_entrance_m,
       s.status AS physical_status,
       CASE
         WHEN s.status = 'MAINTENANCE' THEN 'MAINTENANCE'
         WHEN s.status = 'OCCUPIED'    THEN 'OCCUPIED'
         WHEN EXISTS (SELECT 1 FROM reservations r
                       WHERE r.slot_id = s.slot_id AND r.status = 'PENDING'
                         AND r.start_time <= NOW() + INTERVAL fn_setting_num('reserve_hold_minutes') MINUTE
                         AND r.end_time > NOW()) THEN 'RESERVED'
         ELSE 'AVAILABLE'
       END AS live_status
FROM parking_slots s JOIN zones z ON z.zone_id = s.zone_id;

CREATE VIEW v_zone_occupancy AS
SELECT zone_id, zone_code, zone_name,
       COUNT(*) AS total_slots,
       SUM(live_status = 'AVAILABLE')   AS available,
       SUM(live_status = 'OCCUPIED')    AS occupied,
       SUM(live_status = 'RESERVED')    AS reserved,
       SUM(live_status = 'MAINTENANCE') AS maintenance
FROM v_slot_live_status GROUP BY zone_id, zone_code, zone_name;

CREATE VIEW v_active_sessions AS
SELECT ps.session_id, v.reg_number, v.vehicle_type, s.slot_code, ps.entry_time,
       TIMESTAMPDIFF(MINUTE, ps.entry_time, NOW()) AS elapsed_minutes,
       fn_calc_amount(ps.tariff_id, TIMESTAMPDIFF(MINUTE, ps.entry_time, NOW())) AS running_amount,
       ps.reservation_id
FROM parking_sessions ps
JOIN vehicles v ON v.vehicle_id = ps.vehicle_id
JOIN parking_slots s ON s.slot_id = ps.slot_id
WHERE ps.status = 'ACTIVE';

CREATE VIEW v_itemized_bill AS
SELECT ps.session_id, v.reg_number, s.slot_code, ps.entry_time, ps.exit_time,
       ps.duration_minutes, t.grace_minutes, ps.billable_minutes,
       CEIL(ps.billable_minutes / 60.0) AS hourly_blocks,
       t.hourly_rate, t.min_charge, t.daily_cap,
       ps.amount_due AS parking_fee,
       COALESCE(f.fines, 0) AS fines,
       p.status AS payment_status, p.method AS payment_method, p.paid_at
FROM parking_sessions ps
JOIN vehicles v      ON v.vehicle_id = ps.vehicle_id
JOIN parking_slots s ON s.slot_id = ps.slot_id
JOIN tariff_rules t  ON t.tariff_id = ps.tariff_id
LEFT JOIN (SELECT session_id, SUM(fine_amount) AS fines FROM violations
            WHERE session_id IS NOT NULL GROUP BY session_id) f ON f.session_id = ps.session_id
LEFT JOIN payments p ON p.payment_id = (SELECT MAX(p2.payment_id) FROM payments p2
                                         WHERE p2.session_id = ps.session_id)
WHERE ps.status = 'CLOSED';

CREATE VIEW v_unpaid_bills AS
SELECT session_id, reg_number, slot_code, exit_time, parking_fee, payment_status
FROM v_itemized_bill WHERE payment_status IN ('PENDING','FAILED');

CREATE VIEW v_daily_revenue AS
SELECT DATE(paid_at) AS revenue_date, COUNT(*) AS payments_count, SUM(amount) AS revenue
FROM payments WHERE status = 'PAID' GROUP BY DATE(paid_at);

CREATE VIEW v_hourly_demand AS
SELECT HOUR(entry_time) AS hour_of_day, COUNT(*) AS entries,
       ROUND(AVG(duration_minutes), 1) AS avg_duration_min
FROM parking_sessions WHERE status = 'CLOSED' GROUP BY HOUR(entry_time);

-- Rule-based forecast: average historical occupancy per weekday + hour (1 = Sunday)
CREATE VIEW v_occupancy_forecast AS
SELECT DAYOFWEEK(captured_at) AS day_of_week, HOUR(captured_at) AS hour_of_day,
       ROUND(100 * SUM(occupied_slots) / SUM(usable_slots), 1) AS avg_occupancy_pct,
       COUNT(DISTINCT DATE(captured_at)) AS days_observed,
       CASE WHEN 100 * SUM(occupied_slots) / SUM(usable_slots) >= 85 THEN 'VERY BUSY'
            WHEN 100 * SUM(occupied_slots) / SUM(usable_slots) >= 60 THEN 'BUSY'
            ELSE 'EASY' END AS expectation
FROM occupancy_snapshots GROUP BY DAYOFWEEK(captured_at), HOUR(captured_at);

-- Carbon widget: metres saved vs. a random slot of the same type, x emission factor.
-- ESTIMATE ONLY - assumptions are documented in Decision.md (D-10).
CREATE VIEW v_carbon_estimate AS
SELECT ps.session_id, s.slot_code, s.distance_to_entrance_m AS chosen_m,
       ROUND(b.avg_m, 1) AS baseline_m,
       GREATEST(b.avg_m - s.distance_to_entrance_m, 0) AS saved_m,
       ROUND(GREATEST(b.avg_m - s.distance_to_entrance_m, 0) / 1000
             * fn_setting_num('emission_g_per_km'), 2) AS co2_saved_g
FROM parking_sessions ps
JOIN parking_slots s ON s.slot_id = ps.slot_id
JOIN (SELECT slot_type, AVG(distance_to_entrance_m) AS avg_m
        FROM parking_slots WHERE status <> 'MAINTENANCE' GROUP BY slot_type) b
  ON b.slot_type = s.slot_type;

-- ---------------------------------------------------------------------
-- 4. SCHEDULED EVENTS  (need event_scheduler = ON)
-- ---------------------------------------------------------------------
CREATE EVENT ev_release_no_shows   ON SCHEDULE EVERY 1 MINUTE  DO CALL sp_release_no_shows();
CREATE EVENT ev_flag_overstays     ON SCHEDULE EVERY 5 MINUTE  DO CALL sp_flag_overstays();
CREATE EVENT ev_occupancy_snapshot ON SCHEDULE EVERY 15 MINUTE DO CALL sp_take_snapshot(NULL);
