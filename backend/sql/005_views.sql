-- =====================================================================
-- 005  Views and materialized views
-- =====================================================================

-- Browse/search surface: open items joined to their place. No PII (no email/phone).
CREATE VIEW v_open_items AS
SELECT i.item_id, i.item_type, i.title, i.description, i.category, i.color, i.brand,
       i.date_lost_or_found, i.image_urls, i.reported_at, i.search_tsv,
       i.reporter_id, l.location_id, l.location_name, l.campus,
       (SELECT count(*) FROM match_item mi JOIN match m USING (match_id)
         WHERE mi.item_id = i.item_id AND m.verification_status = 'suggested') AS suggested_matches
  FROM item i JOIN location l USING (location_id)
 WHERE i.status = 'open';

-- One row per match with both sides unpacked: this is the "explain a match" surface.
CREATE VIEW v_match_details AS
SELECT m.match_id, m.verification_status, m.pair_key, m.created_at,
       m.rrf_score, m.boost, m.text_score, m.image_score, m.text_rank, m.image_rank,
       il.item_id AS lost_item_id,  il.title AS lost_title,  il.status AS lost_status,
       il.category AS lost_category, il.image_urls AS lost_images, il.reporter_id AS lost_reporter_id,
       ll.location_name AS lost_location,  il.date_lost_or_found AS lost_date,
       iF.item_id AS found_item_id, iF.title AS found_title, iF.status AS found_status,
       iF.category AS found_category, iF.image_urls AS found_images, iF.reporter_id AS found_reporter_id,
       lF.location_name AS found_location, iF.date_lost_or_found AS found_date
  FROM match m
  JOIN match_item mil ON mil.match_id = m.match_id AND mil.role = 'lost'
  JOIN item il        ON il.item_id = mil.item_id
  JOIN location ll    ON ll.location_id = il.location_id
  JOIN match_item mif ON mif.match_id = m.match_id AND mif.role = 'found'
  JOIN item iF        ON iF.item_id = mif.item_id
  JOIN location lF    ON lF.location_id = iF.location_id;

-- Staff claim queue. Window functions: how many rivals does each claim have and
-- who was first? security_invoker => row-level security on claim still applies,
-- so a non-staff caller sees (at most) their own claims.
CREATE VIEW v_claim_queue WITH (security_invoker = true) AS
SELECT c.claim_id, c.item_id, i.title AS item_title, i.image_urls AS item_images,
       c.claimant_id, u.name AS claimant_name, u.email AS claimant_email,
       c.proof_description, c.proof_image_url, c.verification_status, c.submitted_at,
       c.reviewed_by, c.match_id, m.rrf_score AS match_rrf_score,
       count(*)     OVER (PARTITION BY c.item_id)                         AS competing_claims,
       row_number() OVER (PARTITION BY c.item_id ORDER BY c.submitted_at) AS queue_position,
       now() - c.submitted_at                                            AS waiting_for
  FROM claim c
  JOIN item i  ON i.item_id = c.item_id
  JOIN users u ON u.user_id = c.claimant_id
  LEFT JOIN match m ON m.match_id = c.match_id
 WHERE c.result = 'pending';

-- "Most likely owners": for every found item, rank the lost reports that point at it.
CREATE VIEW v_likely_owners AS
SELECT found_item_id, lost_item_id, lost_reporter_id, rrf_score, verification_status,
       dense_rank() OVER (PARTITION BY found_item_id ORDER BY rrf_score + boost DESC) AS owner_rank
  FROM v_match_details
 WHERE verification_status <> 'rejected';

-- ---- Analytics (materialized) --------------------------------------------
-- Each MV has a UNIQUE index so REFRESH ... CONCURRENTLY works (readers are never
-- blocked). Refresh strategy: the worker calls refresh_analytics() every
-- ANALYTICS_REFRESH_SECONDS (default 300) and right after seeding; the dashboard
-- therefore lags writes by at most that interval. See docs/schema.md.

CREATE MATERIALIZED VIEW mv_status_counts AS
SELECT item_type, status, count(*)::int AS n FROM item GROUP BY item_type, status;
CREATE UNIQUE INDEX mv_status_counts_uq ON mv_status_counts (item_type, status);

-- Recovery rate and time-to-return per category plus an overall row (ROLLUP).
-- LATERAL finds the moment each item became 'returned' in the audit trail.
CREATE MATERIALIZED VIEW mv_recovery_stats AS
SELECT COALESCE(f.category::text, 'ALL')                            AS category,
       count(*)::int                                                AS found_items,
       count(*) FILTER (WHERE f.status = 'returned')::int          AS returned_items,
       round(100.0 * count(*) FILTER (WHERE f.status = 'returned') / NULLIF(count(*), 0), 1) AS recovery_rate_pct,
       round(avg(extract(epoch FROM r.returned_at - f.reported_at) / 3600.0), 1)             AS avg_hours_to_return,
       round((percentile_cont(0.5) WITHIN GROUP
              (ORDER BY extract(epoch FROM r.returned_at - f.reported_at) / 3600.0))::numeric, 1) AS median_hours_to_return
  FROM item f
  LEFT JOIN LATERAL (
        SELECT a.changed_at AS returned_at
          FROM audit_log a
         WHERE a.table_name = 'item' AND a.row_pk = f.item_id
           AND a.new_data ->> 'status' = 'returned'
         ORDER BY a.changed_at LIMIT 1) r ON f.status = 'returned'
 WHERE f.item_type = 'found'
 GROUP BY ROLLUP (f.category);
CREATE UNIQUE INDEX mv_recovery_stats_uq ON mv_recovery_stats (category);

-- Hot spots: where do things get lost/found? rank() and percent_rank() windows.
CREATE MATERIALIZED VIEW mv_location_hotspots AS
SELECT l.location_id, l.location_name, l.campus,
       count(*) FILTER (WHERE i.item_type = 'lost')::int  AS lost_count,
       count(*) FILTER (WHERE i.item_type = 'found')::int AS found_count,
       count(*)::int                                       AS total_items,
       rank()         OVER (ORDER BY count(*) DESC)        AS hotspot_rank,
       round((100 * percent_rank() OVER (ORDER BY count(*)))::numeric, 1) AS percentile
  FROM location l JOIN item i USING (location_id)
 GROUP BY l.location_id, l.location_name, l.campus;
CREATE UNIQUE INDEX mv_location_hotspots_uq ON mv_location_hotspots (location_id);

-- How good are the suggestions? Bucket matches by score; compare to staff decisions.
CREATE MATERIALIZED VIEW mv_match_quality AS
SELECT width_bucket(rrf_score, 0, 2.0 / 61, 8)               AS score_bucket,
       count(*)::int                                          AS matches,
       count(*) FILTER (WHERE verification_status = 'confirmed')::int AS confirmed,
       count(*) FILTER (WHERE verification_status = 'rejected')::int  AS rejected,
       round(100.0 * count(*) FILTER (WHERE verification_status = 'confirmed')
             / NULLIF(count(*) FILTER (WHERE verification_status <> 'suggested'), 0), 1) AS confirm_rate_pct,
       round(avg(text_score)::numeric, 3)                    AS avg_text_score,
       round(avg(image_score)::numeric, 3)                   AS avg_image_score
  FROM match GROUP BY 1;
CREATE UNIQUE INDEX mv_match_quality_uq ON mv_match_quality (score_bucket);

CREATE FUNCTION refresh_analytics() RETURNS void LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_status_counts;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_recovery_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_location_hotspots;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_match_quality;
END $$;
