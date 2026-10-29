-- =====================================================================
-- Demo queries for the viva: DML, joins, nested / correlated / recursive
-- queries, CTEs, window functions, procedures, triggers, views.
--
-- Run against a migrated database (make migrate) as the OWNER role:
--     make psql   then   \i docs/demo_queries.sql
-- or  psql "$MIGRATION_DATABASE_URL" -f docs/demo_queries.sql
--
-- Everything runs inside ONE transaction that ends with ROLLBACK, so the
-- script can be re-run any number of times and leaves no data behind.
-- (The API role app_rw cannot DELETE or change statuses directly: see
-- docs/schema.md, "Security model". Run this script as the owner.)
-- =====================================================================
BEGIN;

-- ---------------------------------------------------------------------
-- 1. DML: INSERT
-- ---------------------------------------------------------------------
INSERT INTO users (name, email, password_hash, role) VALUES
    ('Demo Owner',  'owner@demo.dev',  'x', 'user'),
    ('Demo Finder', 'finder@demo.dev', 'x', 'user'),
    ('Demo Staff',  'staff@demo.dev',  'x', 'staff');

INSERT INTO location (location_name, campus, building) VALUES
    ('Demo Library', 'North', 'Main'),
    ('Demo Cafeteria', 'North', 'Annex'),
    ('Demo Unused Place', 'North', NULL);

-- two lost reports and two found reports
INSERT INTO item (reporter_id, location_id, item_type, title, description, category, color, date_lost_or_found)
SELECT u.user_id, l.location_id, v.item_type::item_type, v.title, v.descr, 'wallet_bag', v.color, current_date - v.days_ago
  FROM (VALUES
        ('owner@demo.dev',  'Demo Library',   'lost',  'Demo lost wallet',   'Black leather wallet with a student card', 'black', 4),
        ('owner@demo.dev',  'Demo Cafeteria', 'lost',  'Demo lost purse',    'Brown purse with a zip',                   'brown', 3),
        ('finder@demo.dev', 'Demo Library',   'found', 'Demo found wallet',  'Black wallet found near the desk',         'black', 2),
        ('finder@demo.dev', 'Demo Cafeteria', 'found', 'Demo found purse',   'Brown purse left on a table',              'brown', 1)
       ) AS v(email, loc, item_type, title, descr, color, days_ago)
  JOIN users u    ON u.email = v.email
  JOIN location l ON l.location_name = v.loc;

-- ---------------------------------------------------------------------
-- 2. DML: UPDATE and DELETE
-- ---------------------------------------------------------------------
UPDATE item SET color = 'dark brown' WHERE title = 'Demo lost purse' RETURNING item_id, title, color, updated_at;

DELETE FROM location WHERE location_name = 'Demo Unused Place' RETURNING location_id, location_name;

-- A trigger refuses an illegal change; the error is caught so the script keeps going.
DO $$
BEGIN
    UPDATE item SET status = 'returned' WHERE title = 'Demo lost wallet';   -- open -> returned is not allowed
EXCEPTION WHEN SQLSTATE 'LF002' THEN
    RAISE NOTICE 'trigger item_guard blocked it: %', SQLERRM;
END $$;

-- ---------------------------------------------------------------------
-- 3. Joins
-- ---------------------------------------------------------------------
-- INNER JOIN across three tables
SELECT i.item_id, i.item_type, i.title, u.name AS reporter, l.location_name
  FROM item i
  JOIN users u    ON u.user_id = i.reporter_id
  JOIN location l ON l.location_id = i.location_id
 WHERE l.location_name LIKE 'Demo%'
 ORDER BY i.item_id;

-- LEFT JOIN: locations and how many items each has (zero included)
SELECT l.location_name, count(i.item_id) AS items
  FROM location l LEFT JOIN item i ON i.location_id = l.location_id
 WHERE l.location_name LIKE 'Demo%'
 GROUP BY l.location_name
 ORDER BY l.location_name;

-- ---------------------------------------------------------------------
-- 4. Aggregates, GROUP BY / HAVING
-- ---------------------------------------------------------------------
SELECT l.location_name, count(*) FILTER (WHERE i.item_type = 'lost')  AS lost,
                        count(*) FILTER (WHERE i.item_type = 'found') AS found
  FROM item i JOIN location l USING (location_id)
 GROUP BY l.location_name
HAVING count(*) >= 2
 ORDER BY l.location_name;

-- ---------------------------------------------------------------------
-- 5. Nested (non-correlated) subquery
-- ---------------------------------------------------------------------
-- items that sit in a location where more than one item was reported
SELECT item_id, title
  FROM item
 WHERE location_id IN (SELECT location_id FROM item GROUP BY location_id HAVING count(*) > 1)
 ORDER BY item_id;

-- ---------------------------------------------------------------------
-- 6. Correlated subqueries
-- ---------------------------------------------------------------------
-- EXISTS: users who have reported at least one item
SELECT u.name FROM users u
 WHERE EXISTS (SELECT 1 FROM item i WHERE i.reporter_id = u.user_id)
 ORDER BY u.name;

-- scalar correlated subquery: for every item, how many OTHER items were reported at the same location
SELECT i.title,
       (SELECT count(*) FROM item o
         WHERE o.location_id = i.location_id AND o.item_id <> i.item_id) AS others_at_same_location
  FROM item i
 WHERE i.title LIKE 'Demo%'
 ORDER BY i.item_id;

-- ---------------------------------------------------------------------
-- 7. CTE and window functions
-- ---------------------------------------------------------------------
WITH per_location AS (
    SELECT l.location_id, l.location_name, count(*) AS n
      FROM item i JOIN location l USING (location_id)
     GROUP BY l.location_id, l.location_name
)
SELECT location_name, n, rank() OVER (ORDER BY n DESC) AS busiest_rank
  FROM per_location
 ORDER BY busiest_rank, location_name;

-- ---------------------------------------------------------------------
-- 8. Stored function: persist matches, then a RECURSIVE query over them
-- ---------------------------------------------------------------------
-- chain:  lost wallet - found wallet - lost purse - found purse
SELECT out_match_id FROM persist_match(
    (SELECT item_id FROM item WHERE title = 'Demo lost wallet'),
    (SELECT item_id FROM item WHERE title = 'Demo found wallet'), 0.03, 0, 0.9, NULL, 1, NULL);
SELECT out_match_id FROM persist_match(
    (SELECT item_id FROM item WHERE title = 'Demo lost purse'),
    (SELECT item_id FROM item WHERE title = 'Demo found wallet'), 0.02, 0, 0.7, NULL, 2, NULL);
SELECT out_match_id FROM persist_match(
    (SELECT item_id FROM item WHERE title = 'Demo lost purse'),
    (SELECT item_id FROM item WHERE title = 'Demo found purse'), 0.03, 0, 0.9, NULL, 1, NULL);

-- WITH RECURSIVE inside related_items() (backend/sql/005_views.sql): follow matches hop by hop
SELECT related_item_id, related_title, related_type, hops
  FROM related_items((SELECT item_id FROM item WHERE title = 'Demo lost wallet'));

-- the same idea written out, to show the recursion itself
WITH RECURSIVE chain(item_id, hops, path) AS (
    SELECT item_id, 0, ARRAY[item_id] FROM item WHERE title = 'Demo lost wallet'
    UNION ALL
    SELECT mo.item_id, c.hops + 1, c.path || mo.item_id
      FROM chain c
      JOIN match_item mi ON mi.item_id = c.item_id
      JOIN match_item mo ON mo.match_id = mi.match_id AND mo.item_id <> mi.item_id
     WHERE NOT mo.item_id = ANY (c.path)
)
SELECT c.hops, i.title FROM chain c JOIN item i USING (item_id) ORDER BY c.hops;

-- ---------------------------------------------------------------------
-- 9. Procedures and triggers: the claim workflow
-- ---------------------------------------------------------------------
INSERT INTO claim (item_id, claimant_id, proof_description)
SELECT (SELECT item_id FROM item WHERE title = 'Demo found wallet'), user_id, 'Student card inside has my name'
  FROM users WHERE email = 'owner@demo.dev';

SELECT start_claim_review((SELECT claim_id FROM claim ORDER BY claim_id DESC LIMIT 1),
                          (SELECT user_id FROM users WHERE email = 'staff@demo.dev'));

SELECT claim_id, verification_status, result
  FROM approve_claim((SELECT claim_id FROM claim ORDER BY claim_id DESC LIMIT 1),
                     (SELECT user_id FROM users WHERE email = 'staff@demo.dev'), 'ID checked');

-- the trigger trg_claim_after_approval already moved the item to 'claimed'
SELECT title, status FROM item WHERE title = 'Demo found wallet';

SELECT title, status
  FROM mark_returned((SELECT item_id FROM item WHERE title = 'Demo found wallet'),
                     (SELECT user_id FROM users WHERE email = 'staff@demo.dev'));

-- ---------------------------------------------------------------------
-- 10. Views and the audit trail written by triggers
-- ---------------------------------------------------------------------
SELECT item_id, title, location_name, suggested_matches FROM v_open_items ORDER BY item_id;

SELECT table_name, action, row_pk, changed_at
  FROM audit_log
 ORDER BY audit_id DESC
 LIMIT 5;

ROLLBACK;
