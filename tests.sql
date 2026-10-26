-- =====================================================================
-- ParkWise test suite.  Run AFTER schema.sql + seed.sql.
-- It MODIFIES data (creates sessions/reservations); re-run schema.sql + seed.sql to reset.
-- Final query prints PASS/FAIL for every test.  Concurrency test: tests_concurrency.py.
-- =====================================================================
USE parkwise;
DROP TEMPORARY TABLE IF EXISTS t_results;
CREATE TEMPORARY TABLE t_results (test_name VARCHAR(90), result VARCHAR(200));

DROP PROCEDURE IF EXISTS t_assert;
DROP PROCEDURE IF EXISTS t_run;
DELIMITER $$
CREATE PROCEDURE t_assert(IN p_name VARCHAR(90), IN p_ok TINYINT)
BEGIN
  INSERT INTO t_results VALUES (p_name, IF(p_ok = 1, 'PASS', 'FAIL'));
END$$

-- Runs a statement; p_expect_err NULL => must succeed, else error text must CONTAIN p_expect_err
CREATE PROCEDURE t_run(IN p_name VARCHAR(90), IN p_sql TEXT, IN p_expect_err VARCHAR(120))
BEGIN
  DECLARE v_msg TEXT DEFAULT NULL;
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
  BEGIN
    GET DIAGNOSTICS CONDITION 1 v_msg = MESSAGE_TEXT;
  END;
  SET @t_sql = p_sql;
  PREPARE st FROM @t_sql;
  EXECUTE st;
  DEALLOCATE PREPARE st;
  IF p_expect_err IS NULL THEN
    INSERT INTO t_results VALUES (p_name, IF(v_msg IS NULL, 'PASS', CONCAT('FAIL: unexpected error: ', v_msg)));
  ELSE
    INSERT INTO t_results VALUES (p_name,
      IF(v_msg IS NOT NULL AND v_msg LIKE CONCAT('%', p_expect_err, '%'), 'PASS',
         CONCAT('FAIL: expected [', p_expect_err, '] got [', COALESCE(v_msg, 'no error'), ']')));
  END IF;
END$$
DELIMITER ;

-- Slot ids: A-01=1 A-02=2 A-03=3 A-04=4 A-05=5 A-06=6 A-07=7 A-08=8 B-01=9 B-02=10 B-03=11 ...
-- Vehicle ids: 1 car(u2) 2 bike(u2) 3 EV car(u3) 4 bike(u3) 5 permit car(u4) 6 bike(u4)
--              7 car(u5) 8 bike(u5) 9 EV car(u6) 10 bike(u6) 11 car(u7) 12 bike(u7) 13 car(u2) 14 car(u3)

-- T01 billing rule (pure function) ---------------------------------------
CALL t_assert('T01a billing: 145 min @30/h, grace 10 => 90', fn_calc_amount(1,145) = 90);
CALL t_assert('T01b billing: 10 min (inside grace) => 0',     fn_calc_amount(1,10) = 0);
CALL t_assert('T01c billing: 11 min => min charge 30',        fn_calc_amount(1,11) = 30);
CALL t_assert('T01d billing: 70 min => 1 block = 30',         fn_calc_amount(1,70) = 30);
CALL t_assert('T01e billing: 71 min => 2 blocks = 60',        fn_calc_amount(1,71) = 60);
CALL t_assert('T01f billing: 2000 min hits cap 200 x 2 days = 400', fn_calc_amount(1,2000) = 400);
CALL t_assert('T01g billing: bike 100 min @10/h => 20',       fn_calc_amount(3,100) = 20);
CALL t_run('T01h billing: negative duration rejected', 'SELECT fn_calc_amount(1,-5)', 'Negative duration');

-- T02 full walk-in cycle ---------------------------------------------------
CALL t_run('T02a entry (walk-in) vehicle 1 -> A-03', 'CALL sp_vehicle_entry(1,3,NOW() - INTERVAL 145 MINUTE,@sid1)', NULL);
CALL t_assert('T02b trigger marked slot OCCUPIED', (SELECT status = 'OCCUPIED' FROM parking_slots WHERE slot_id = 3));
CALL t_run('T02c second vehicle on occupied slot rejected', 'CALL sp_vehicle_entry(13,3,NULL,@x)', 'Slot is occupied');
CALL t_run('T02d same vehicle in a 2nd slot rejected', 'CALL sp_vehicle_entry(1,4,NULL,@x)', 'already has an active session');
CALL t_run('T02e exit computes bill', 'CALL sp_vehicle_exit(@sid1,NULL,@amt1)', NULL);
CALL t_assert('T02f amount = 90', @amt1 = 90);
CALL t_assert('T02g slot freed by trigger', (SELECT status = 'AVAILABLE' FROM parking_slots WHERE slot_id = 3));
CALL t_assert('T02h payment PENDING for 90', (SELECT COUNT(*) FROM payments WHERE session_id = @sid1 AND status = 'PENDING' AND amount = 90) = 1);
CALL t_run('T02i double exit rejected', 'CALL sp_vehicle_exit(@sid1,NULL,@x)', 'already closed');
CALL t_run('T02j failed payment', CONCAT('CALL sp_record_payment(', @sid1, ',''UPI'',0)'), NULL);
CALL t_assert('T02k failed payment leaves a new PENDING row', (SELECT COUNT(*) FROM payments WHERE session_id = @sid1 AND status = 'PENDING') = 1
                                                          AND (SELECT COUNT(*) FROM payments WHERE session_id = @sid1 AND status = 'FAILED') = 1);
CALL t_run('T02l successful payment', CONCAT('CALL sp_record_payment(', @sid1, ',''UPI'',1)'), NULL);
CALL t_assert('T02m session fully paid', (SELECT payment_status FROM v_itemized_bill WHERE session_id = @sid1) = 'PAID');

-- T03 eligibility rules ------------------------------------------------------
CALL t_run('T03a bike into car slot rejected',        'CALL sp_vehicle_entry(2,5,NULL,@x)', 'does not match slot type');
CALL t_run('T03b accessible bay needs permit',        'CALL sp_vehicle_entry(1,1,NULL,@x)', 'accessibility permit');
CALL t_run('T03c permit holder may use accessible bay','CALL sp_vehicle_entry(5,1,NULL,@sid5)', NULL);
CALL t_run('T03d EV bay refused to non-EV',           'CALL sp_vehicle_entry(1,9,NULL,@x)', 'reserved for EVs');
CALL t_run('T03e EV may use charger bay',             'CALL sp_vehicle_entry(3,9,NULL,@sid3)', NULL);
CALL t_run('T03f raw INSERT into maintenance/type-mismatch blocked by trigger',
           'INSERT INTO parking_sessions (vehicle_id,slot_id,tariff_id,entry_time) VALUES (2,5,1,NOW())', 'does not match slot type');

-- T04 reservations ------------------------------------------------------------
CALL t_run('T04a reserve A-05 (user2/vehicle1) +60..+180 min',
           'CALL sp_create_reservation(2,1,5,NOW() + INTERVAL 60 MINUTE,NOW() + INTERVAL 180 MINUTE,0.9,''test'',@r1)', NULL);
CALL t_run('T04b overlapping booking on same slot rejected',
           'CALL sp_create_reservation(5,7,5,NOW() + INTERVAL 120 MINUTE,NOW() + INTERVAL 240 MINUTE,NULL,NULL,@x)', 'already booked');
CALL t_run('T04c adjacent booking (starts when other ends) allowed',
           'CALL sp_create_reservation(5,7,5,NOW() + INTERVAL 180 MINUTE,NOW() + INTERVAL 240 MINUTE,NULL,NULL,@r2)', NULL);
CALL t_run('T04d vehicle of another user rejected',
           'CALL sp_create_reservation(3,1,6,NOW() + INTERVAL 60 MINUTE,NOW() + INTERVAL 90 MINUTE,NULL,NULL,@x)', 'does not belong');
CALL t_run('T04e past start rejected',
           'CALL sp_create_reservation(2,1,6,NOW() - INTERVAL 2 HOUR,NOW() + INTERVAL 1 HOUR,NULL,NULL,@x)', 'in the past');
CALL t_run('T04f same vehicle double-booked rejected',
           'CALL sp_create_reservation(2,1,7,NOW() + INTERVAL 90 MINUTE,NOW() + INTERVAL 100 MINUTE,NULL,NULL,@x)', 'already has a reservation');
CALL t_run('T04g cancel by wrong user rejected', CONCAT('CALL sp_cancel_reservation(', @r2, ',2)'), 'Not your reservation');
CALL t_run('T04h cancel by owner', CONCAT('CALL sp_cancel_reservation(', @r2, ',5)'), NULL);
CALL t_run('T04i cancel twice rejected', CONCAT('CALL sp_cancel_reservation(', @r2, ',5)'), 'Only PENDING');
CALL t_run('T04j illegal status jump blocked by trigger',
           CONCAT('UPDATE reservations SET status=''ACTIVE'' WHERE reservation_id=', @r2), 'Invalid reservation status transition');

-- T05 reserved slot protection + reservation-linked entry ----------------------
CALL t_run('T05a reserve A-06 starting in 10 min (vehicle 7)',
           'CALL sp_create_reservation(5,7,6,NOW() + INTERVAL 10 MINUTE,NOW() + INTERVAL 70 MINUTE,0.8,''test'',@r3)', NULL);
CALL t_assert('T05b live board shows A-06 RESERVED', (SELECT live_status = 'RESERVED' FROM v_slot_live_status WHERE slot_id = 6));
CALL t_run('T05c walk-in on a reserved slot rejected', 'CALL sp_vehicle_entry(11,6,NULL,@x)', 'reserved for another vehicle');
CALL t_run('T05d reserved vehicle enters (within early window)', 'CALL sp_vehicle_entry(7,6,NULL,@sid7)', NULL);
CALL t_assert('T05e reservation became ACTIVE and linked', (SELECT status FROM reservations WHERE reservation_id = @r3) = 'ACTIVE'
                                                         AND (SELECT reservation_id FROM parking_sessions WHERE session_id = @sid7) = @r3);

-- T06 overstay ----------------------------------------------------------------
CALL t_run('T06a reserve A-07 (vehicle 11)', 'CALL sp_create_reservation(7,11,7,NOW() + INTERVAL 1 MINUTE,NOW() + INTERVAL 61 MINUTE,NULL,NULL,@r4)', NULL);
CALL t_run('T06b enter', 'CALL sp_vehicle_entry(11,7,NOW(),@sid11)', NULL);
CALL t_run('T06c exit 75 min after booked end', 'CALL sp_vehicle_exit(@sid11, NOW() + INTERVAL 136 MINUTE, @amt11)', NULL);
CALL t_assert('T06d overstay fine = ceil((75-10)/60)=2 x 50 = 100',
              (SELECT fine_amount FROM violations WHERE session_id = @sid11 AND violation_type = 'OVERSTAY') = 100);
CALL t_assert('T06e reservation COMPLETED', (SELECT status FROM reservations WHERE reservation_id = @r4) = 'COMPLETED');

-- T07 no-show scheduler job ----------------------------------------------------
-- (raw INSERT: simulates a booking that started 30 min ago; the procedure forbids past starts)
INSERT INTO reservations (user_id, vehicle_id, slot_id, start_time, end_time)
VALUES (2, 13, 8, NOW() - INTERVAL 30 MINUTE, NOW() + INTERVAL 30 MINUTE);
SET @r5 = LAST_INSERT_ID();
CALL t_run('T07a sp_release_no_shows runs', 'CALL sp_release_no_shows()', NULL);
CALL t_assert('T07b late PENDING reservation -> NO_SHOW', (SELECT status FROM reservations WHERE reservation_id = @r5) = 'NO_SHOW');
CALL t_assert('T07c NO_SHOW violation recorded', (SELECT COUNT(*) FROM violations WHERE reservation_id = @r5 AND violation_type = 'NO_SHOW') = 1);
CALL t_run('T07d scheduler is idempotent (2nd run)', 'CALL sp_release_no_shows()', NULL);
CALL t_assert('T07e still exactly one NO_SHOW violation', (SELECT COUNT(*) FROM violations WHERE reservation_id = @r5 AND violation_type = 'NO_SHOW') = 1);
CALL t_assert('T07f future reservations untouched', (SELECT status FROM reservations WHERE reservation_id = @r1) = 'PENDING');

-- T08 overstay scheduler job (vehicle still parked long after its booked window) ----
INSERT INTO reservations (user_id, vehicle_id, slot_id, start_time, end_time, status)
VALUES (3, 14, 11, NOW() - INTERVAL 5 HOUR, NOW() - INTERVAL 2 HOUR, 'PENDING');
SET @r6 = LAST_INSERT_ID();
CALL t_run('T08a entry linked to that reservation', 'CALL sp_vehicle_entry(14, 11, NOW() - INTERVAL 4 HOUR, @sid14)', NULL);
CALL t_run('T08b sp_flag_overstays runs', 'CALL sp_flag_overstays()', NULL);
CALL t_assert('T08c OVERSTAY flagged with fine > 0', (SELECT fine_amount FROM violations WHERE session_id = @sid14 AND violation_type = 'OVERSTAY') > 0);
CALL t_run('T08d 2nd run does not duplicate', 'CALL sp_flag_overstays()', NULL);
CALL t_assert('T08e still one OVERSTAY row', (SELECT COUNT(*) FROM violations WHERE session_id = @sid14 AND violation_type = 'OVERSTAY') = 1);

-- T09 guards, constraints, audit ----------------------------------------------------
CALL t_run('T09a cannot free a slot that holds a vehicle', 'UPDATE parking_slots SET status=''AVAILABLE'' WHERE slot_id=1', 'active parking session');
CALL t_run('T09b cannot disable an occupied slot', 'UPDATE parking_slots SET status=''MAINTENANCE'' WHERE slot_id=1', 'active parking session');
SET @app_user_id = 1;
CALL t_run('T09c maintenance on a free slot works', 'UPDATE parking_slots SET status=''MAINTENANCE'' WHERE slot_id=24', NULL);
CALL t_assert('T09d maintenance toggle audited with actor', (SELECT COUNT(*) FROM audit_logs WHERE action = 'SLOT_MAINTENANCE' AND entity_id = 24 AND actor_user_id = 1) = 1);
CALL t_run('T09e maintenance slot cannot be entered', 'CALL sp_vehicle_entry(1,24,NULL,@x)', 'under maintenance');
UPDATE parking_slots SET status = 'AVAILABLE' WHERE slot_id = 24;
UPDATE tariff_rules SET hourly_rate = 31.00 WHERE tariff_id = 1;
CALL t_assert('T09f tariff change audited', (SELECT COUNT(*) FROM audit_logs WHERE action = 'TARIFF_UPDATE' AND entity_id = 1) = 1);
UPDATE tariff_rules SET hourly_rate = 30.00 WHERE tariff_id = 1;
CALL t_run('T09g CHECK: rate must be positive', 'UPDATE tariff_rules SET hourly_rate = 0 WHERE tariff_id = 1', 'chk_tariff_rate');
CALL t_run('T09h UNIQUE: duplicate registration number', 'INSERT INTO vehicles (user_id,reg_number,vehicle_type) VALUES (2,''MH12AB1001'',''CAR'')', 'Duplicate entry');
CALL t_run('T09i FK: vehicle with unknown owner', 'INSERT INTO vehicles (user_id,reg_number,vehicle_type) VALUES (999,''MH00XX0000'',''CAR'')', 'foreign key');

-- T10 snapshot + views ---------------------------------------------------------------
CALL t_run('T10a snapshot procedure', 'CALL sp_take_snapshot(NULL)', NULL);
CALL t_assert('T10b one snapshot row per zone at the latest aligned time',
  (SELECT COUNT(*) FROM occupancy_snapshots WHERE captured_at = (SELECT MAX(captured_at) FROM occupancy_snapshots)) = 4);
CALL t_assert('T10c views answer', (SELECT COUNT(*) FROM v_zone_occupancy) = 4
  AND (SELECT COUNT(*) FROM v_occupancy_forecast) > 0 AND (SELECT COUNT(*) FROM v_daily_revenue) > 0
  AND (SELECT COUNT(*) FROM v_carbon_estimate) > 0 AND (SELECT COUNT(*) FROM v_active_sessions) >= 1);
CALL t_assert('T10d allocation weights sum to 1.00',
  (SELECT SUM(CAST(setting_value AS DECIMAL(5,2))) FROM system_settings
    WHERE setting_key IN ('w_distance','w_ev','w_accessible','w_cost')) = 1.00);

-- ===================== RESULTS =====================
SELECT result, COUNT(*) AS n FROM t_results GROUP BY result ORDER BY result;
SELECT * FROM t_results WHERE result <> 'PASS';          -- empty set = everything passed
SELECT test_name, result FROM t_results;

-- ============ Recommendation (visual check; a procedure result set cannot be asserted in SQL)
-- Window well in the future so currently parked cars do not matter.
SET @t0 = NOW() + INTERVAL 5 HOUR, @t1 = NOW() + INTERVAL 6 HOUR;
-- Ordinary car (vehicle 1)  -> EXPECT top = A-03 (nearest non-accessible, non-charger slot)
CALL sp_recommend_slots(1, @t0, @t1);
-- EV car (vehicle 3)        -> EXPECT top = B-01 or B-02 (charger bay beats a nearer plain bay)
CALL sp_recommend_slots(3, @t0, @t1);
-- Permit holder (vehicle 5) -> EXPECT top = A-01 (accessible + nearest)
CALL sp_recommend_slots(5, @t0, @t1);
-- Bike (vehicle 2)          -> EXPECT top = C-01
CALL sp_recommend_slots(2, @t0, @t1);

DROP PROCEDURE IF EXISTS t_assert;
DROP PROCEDURE IF EXISTS t_run;
