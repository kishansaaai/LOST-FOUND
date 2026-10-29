-- =====================================================================
-- 006  Least-privilege roles, column grants, row-level security
--
--   app_rw     the API/worker. No DELETE, no direct status/result writes:
--              state changes go through SECURITY DEFINER procedures.
--   app_ro     read-only reporting of non-PII columns.
--   analytics  reads the materialized views only.
-- =====================================================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rw') THEN
        CREATE ROLE app_rw LOGIN PASSWORD '{{APP_RW_PASSWORD}}'; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_ro') THEN
        CREATE ROLE app_ro LOGIN PASSWORD '{{APP_RO_PASSWORD}}'; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analytics') THEN
        CREATE ROLE analytics LOGIN PASSWORD '{{ANALYTICS_PASSWORD}}'; END IF;
END $$;

GRANT USAGE ON SCHEMA public TO app_rw, app_ro, analytics;

-- ---- helpers used by policies ----------------------------------------------
-- The API runs `SELECT set_config('app.user_id', '<id>', true)` at the start of every
-- request transaction. Staff-ness is looked up in the users table, not taken from
-- client-supplied text, so a forged setting cannot grant staff powers.
CREATE FUNCTION app_user_id() RETURNS bigint LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('app.user_id', true), '')::bigint $$;
CREATE FUNCTION app_is_staff() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM users WHERE user_id = app_user_id() AND role IN ('staff', 'admin')) $$;

-- ---- app_rw: column-level grants ---------------------------------------------
GRANT SELECT ON users, location, item, embedding, match, match_item, claim, audit_log, outbox TO app_rw;
-- users can self-register but can never choose their own role
GRANT INSERT (name, email, password_hash, phone) ON users TO app_rw;
GRANT UPDATE (name, phone, password_hash)        ON users TO app_rw;
GRANT INSERT ON location TO app_rw;
GRANT UPDATE (location_name, campus, building, floor, address, latitude, longitude) ON location TO app_rw;
GRANT INSERT ON item TO app_rw;
GRANT UPDATE (title, description, category, color, brand, date_lost_or_found, image_urls, location_id)
    ON item TO app_rw;                                   -- NOT status: see procedures
GRANT INSERT, UPDATE ON embedding TO app_rw;             -- written by the embedding worker
GRANT INSERT ON claim TO app_rw;                         -- decisions only via procedures
GRANT INSERT, UPDATE ON outbox TO app_rw;                -- worker marks events processed

-- ---- app_ro / analytics ------------------------------------------------------
GRANT SELECT (user_id, name, role, created_at) ON users TO app_ro;
GRANT SELECT ON location, item, match, match_item, v_open_items, v_match_details TO app_ro;
GRANT SELECT ON mv_status_counts, mv_recovery_stats, mv_location_hotspots, mv_match_quality
    TO app_rw, app_ro, analytics;
GRANT SELECT ON v_open_items, v_match_details, v_likely_owners, v_claim_queue TO app_rw;

-- ---- procedures run with owner rights; they check the caller's role themselves
ALTER FUNCTION start_claim_review(bigint, bigint)      SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION approve_claim(bigint, bigint, text)     SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION reject_claim(bigint, bigint, text)      SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION mark_returned(bigint, bigint)           SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION close_item(bigint, bigint)              SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION confirm_match(bigint, bigint)           SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION reject_match(bigint, bigint)            SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION refresh_matches(bigint, integer, real, real) SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION persist_match(bigint, bigint, double precision, real, real, real, integer, integer)
    SECURITY DEFINER SET search_path = public, pg_temp;

-- Admin-only role management (the only way to change users.role)
CREATE FUNCTION set_user_role(p_admin_id bigint, p_user_id bigint, p_role user_role) RETURNS users
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_user users;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE user_id = p_admin_id AND role = 'admin') THEN
        RAISE EXCEPTION 'only an admin can change roles' USING ERRCODE = 'LF001';
    END IF;
    SELECT * INTO v_user FROM users WHERE user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'user % not found', p_user_id USING ERRCODE = 'LF003';
    END IF;
    IF v_user.role = 'admin' AND p_role <> 'admin'
       AND (SELECT count(*) FROM users WHERE role = 'admin') = 1 THEN
        RAISE EXCEPTION 'cannot demote the last admin' USING ERRCODE = 'LF002';
    END IF;
    UPDATE users SET role = p_role WHERE user_id = p_user_id RETURNING * INTO v_user;
    RETURN v_user;
END $$;

-- Only app_rw may call the state-changing procedures.
REVOKE EXECUTE ON FUNCTION start_claim_review, approve_claim, reject_claim, mark_returned, close_item,
    confirm_match, reject_match, refresh_matches, persist_match, set_user_role, refresh_analytics FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION start_claim_review, approve_claim, reject_claim, mark_returned, close_item,
    confirm_match, reject_match, refresh_matches, persist_match, set_user_role, refresh_analytics TO app_rw;

-- ---- row-level security --------------------------------------------------------
-- claim: owners see only their own claims, staff see all, anyone may only file a
-- claim as themselves. UPDATEs happen inside definer procedures (owner bypasses RLS).
ALTER TABLE claim ENABLE ROW LEVEL SECURITY;
CREATE POLICY claim_select ON claim FOR SELECT TO app_rw
    USING (claimant_id = app_user_id() OR app_is_staff());
CREATE POLICY claim_insert ON claim FOR INSERT TO app_rw
    WITH CHECK (claimant_id = app_user_id());

-- audit_log: staff only.
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_staff_select ON audit_log FOR SELECT TO app_rw USING (app_is_staff());
