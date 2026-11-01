-- Query showcase: DML, joins, nested / correlated subqueries, recursive CTE.
-- Run against the seeded database:   make psql < docs/queries.sql      (or: psql -f docs/queries.sql)
-- Every statement is read-only except section 1, which runs inside a transaction that is rolled back.

\echo '=== 1. DML: INSERT / UPDATE / DELETE (rolled back, nothing is kept) ==='
BEGIN;

INSERT INTO location (location_name, campus, building)            -- INSERT
VALUES ('Demo annex', 'Main campus', 'Annex 9')
RETURNING location_id, location_name;

UPDATE location SET floor = '2'                                     -- UPDATE
WHERE location_name = 'Demo annex'
RETURNING location_id, location_name, floor;

DELETE FROM location WHERE location_name = 'Demo annex'             -- DELETE
RETURNING location_id, location_name;

-- Deliberate refusal: a location that has items can never be deleted (ON DELETE RESTRICT).
SAVEPOINT try_delete;
DELETE FROM location WHERE location_id = (SELECT location_id FROM item LIMIT 1);
ROLLBACK TO try_delete;
ROLLBACK;

\echo '=== 2. JOINS ==='
-- 2a. INNER JOIN across three tables: who reported what, where.
SELECT i.item_id, i.item_type, i.title, u.name AS reporter, l.location_name
FROM item i
JOIN users    u ON u.user_id     = i.reporter_id
JOIN location l ON l.location_id = i.location_id
ORDER BY i.item_id
LIMIT 5;

-- 2b. LEFT JOIN + anti-join pattern: open lost items that have no suggested match yet.
SELECT i.item_id, i.title
FROM item i
LEFT JOIN match_item mi ON mi.item_id = i.item_id
WHERE i.item_type = 'lost' AND i.status = 'open' AND mi.match_id IS NULL
ORDER BY i.item_id
LIMIT 5;

-- 2c. Self-join through the junction table: each match as one row (lost title vs found title).
SELECT m.match_id, round(m.rrf_score::numeric, 4) AS rrf, lost.title AS lost_title, found.title AS found_title
FROM match m
JOIN match_item ml ON ml.match_id = m.match_id AND ml.role = 'lost'
JOIN item lost     ON lost.item_id = ml.item_id
JOIN match_item mf ON mf.match_id = m.match_id AND mf.role = 'found'
JOIN item found    ON found.item_id = mf.item_id
ORDER BY m.rrf_score DESC
LIMIT 5;

\echo '=== 3. NESTED (non-correlated) subqueries ==='
-- 3a. Locations with more items than the average location (aggregate inside a subquery over a subquery).
SELECT l.location_name, count(*) AS items
FROM item i JOIN location l USING (location_id)
GROUP BY l.location_name
HAVING count(*) > (SELECT avg(c) FROM (SELECT count(*) AS c FROM item GROUP BY location_id) per_loc)
ORDER BY items DESC
LIMIT 5;

-- 3b. Users who reported BOTH lost and found items (IN with two nested subqueries).
SELECT user_id, name FROM users
WHERE user_id IN (SELECT reporter_id FROM item WHERE item_type = 'lost')
  AND user_id IN (SELECT reporter_id FROM item WHERE item_type = 'found')
ORDER BY user_id
LIMIT 5;

\echo '=== 4. CORRELATED subqueries ==='
-- 4a. For every open lost item, its best match score (scalar subquery re-evaluated per outer row).
SELECT i.item_id, i.title,
       (SELECT round(max(m.rrf_score)::numeric, 4)
          FROM match m JOIN match_item mi ON mi.match_id = m.match_id
         WHERE mi.item_id = i.item_id) AS best_rrf
FROM item i
WHERE i.item_type = 'lost' AND i.status = 'open'
ORDER BY best_rrf DESC NULLS LAST
LIMIT 5;

-- 4b. Items with more matches than the average item OF THE SAME CATEGORY (the inner query refers to the outer row).
SELECT i.item_id, i.category, i.title,
       (SELECT count(*) FROM match_item mi WHERE mi.item_id = i.item_id) AS n_matches
FROM item i
WHERE (SELECT count(*) FROM match_item mi WHERE mi.item_id = i.item_id) >
      (SELECT avg(cnt) FROM (SELECT i2.item_id, (SELECT count(*) FROM match_item mi2 WHERE mi2.item_id = i2.item_id) AS cnt
                               FROM item i2 WHERE i2.category = i.category) same_cat)
ORDER BY n_matches DESC, i.item_id
LIMIT 5;

-- 4c. EXISTS: found items that currently have at least one pending claim.
SELECT i.item_id, i.title
FROM item i
WHERE i.item_type = 'found'
  AND EXISTS (SELECT 1 FROM claim c WHERE c.item_id = i.item_id AND c.result = 'pending')
ORDER BY i.item_id
LIMIT 5;

\echo '=== 5. RECURSIVE CTE ==='
-- 5a. A day-by-day calendar generated recursively, left-joined to reports, so days with zero reports still appear.
WITH RECURSIVE calendar(day) AS (
    SELECT (SELECT max(reported_at)::date FROM item) - 13
  UNION ALL
    SELECT day + 1 FROM calendar WHERE day < (SELECT max(reported_at)::date FROM item)
)
SELECT c.day,
       count(i.item_id) FILTER (WHERE i.item_type = 'lost')  AS lost,
       count(i.item_id) FILTER (WHERE i.item_type = 'found') AS found
FROM calendar c
LEFT JOIN item i ON i.reported_at::date = c.day
GROUP BY c.day
ORDER BY c.day;

-- 5b. Running total with a window function over the same calendar idea (CTE + window).
WITH per_day AS (
    SELECT reported_at::date AS day, count(*) AS n FROM item GROUP BY 1
)
SELECT day, n, sum(n) OVER (ORDER BY day) AS running_total
FROM per_day
ORDER BY day DESC
LIMIT 5;
