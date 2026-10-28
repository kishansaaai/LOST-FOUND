-- =====================================================================
-- 002  Triggers: integrity, state machines, audit, outbox
--
-- Custom SQLSTATEs used by every function in this project (mapped to HTTP
-- codes by the API):  LF001 = not authorised (403)
--                     LF002 = invalid state / conflict (409)
--                     LF003 = not found (404)
-- =====================================================================

-- ---- generic: updated_at -------------------------------------------------
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

-- ---- ITEM: validation + state machine -----------------------------------
-- Allowed status transitions (anything else raises LF002):
--   open    -> matched | claimed | closed
--   matched -> open | claimed | returned (lost side) | closed
--   claimed -> returned | closed
--   closed  -> open                       (staff reopen)
--   returned is terminal.
-- Business guards on top of the graph:
--   * 'claimed'  only for FOUND items that own an approved claim
--   * 'returned' for a found item needs an approved claim; for a lost item it
--                needs a confirmed match whose found item has an approved claim.
CREATE FUNCTION item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'open' THEN
            RAISE EXCEPTION 'new items must start as open' USING ERRCODE = 'LF002';
        END IF;
        IF NEW.date_lost_or_found > current_date THEN
            RAISE EXCEPTION 'date_lost_or_found % is in the future', NEW.date_lost_or_found
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    -- UPDATE
    IF NEW.item_type <> OLD.item_type OR NEW.reporter_id <> OLD.reporter_id THEN
        RAISE EXCEPTION 'item_type and reporter_id are immutable' USING ERRCODE = 'LF002';
    END IF;
    IF NEW.date_lost_or_found IS DISTINCT FROM OLD.date_lost_or_found
       AND NEW.date_lost_or_found > current_date THEN
        RAISE EXCEPTION 'date_lost_or_found % is in the future', NEW.date_lost_or_found
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status = 'returned' THEN
        RAISE EXCEPTION 'item % is returned and can no longer change', OLD.item_id
            USING ERRCODE = 'LF002';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT ((OLD.status, NEW.status) IN (
                ('open','matched'), ('open','claimed'), ('open','closed'),
                ('matched','open'), ('matched','claimed'), ('matched','returned'), ('matched','closed'),
                ('claimed','returned'), ('claimed','closed'),
                ('closed','open'))) THEN
            RAISE EXCEPTION 'illegal item status transition % -> %', OLD.status, NEW.status
                USING ERRCODE = 'LF002';
        END IF;

        IF NEW.status = 'claimed' THEN
            IF NEW.item_type <> 'found' OR NOT EXISTS (
                   SELECT 1 FROM claim WHERE item_id = NEW.item_id AND result = 'approved') THEN
                RAISE EXCEPTION 'item % cannot be claimed without an approved claim', NEW.item_id
                    USING ERRCODE = 'LF002';
            END IF;
        ELSIF NEW.status = 'returned' THEN
            IF NEW.item_type = 'found' THEN
                IF NOT EXISTS (SELECT 1 FROM claim
                               WHERE item_id = NEW.item_id AND result = 'approved') THEN
                    RAISE EXCEPTION 'item % cannot be returned without an approved claim', NEW.item_id
                        USING ERRCODE = 'LF002';
                END IF;
            ELSIF NOT EXISTS (
                    SELECT 1
                    FROM match_item ml
                    JOIN match m        ON m.match_id = ml.match_id AND m.verification_status = 'confirmed'
                    JOIN match_item mf  ON mf.match_id = m.match_id AND mf.role = 'found'
                    JOIN claim c        ON c.item_id = mf.item_id AND c.result = 'approved'
                    WHERE ml.item_id = NEW.item_id) THEN
                RAISE EXCEPTION 'lost item % cannot be returned without a confirmed match to a claimed item',
                    NEW.item_id USING ERRCODE = 'LF002';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_item_guard      BEFORE INSERT OR UPDATE ON item
    FOR EACH ROW EXECUTE FUNCTION item_guard();
CREATE TRIGGER trg_item_updated_at BEFORE UPDATE ON item
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---- MATCH: structural integrity (deferred to COMMIT) -------------------
-- A match must contain exactly one lost and one found item, each match_item
-- role must equal item.item_type, and match.pair_key must name that pair.
-- Deferred so a transaction can insert the match and its two rows in any order.
CREATE FUNCTION check_match_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_match bigint;
    v_n     integer;
    v_lost  bigint;
    v_found bigint;
BEGIN
    v_match := CASE WHEN TG_OP = 'DELETE' THEN OLD.match_id ELSE NEW.match_id END;
    IF NOT EXISTS (SELECT 1 FROM match WHERE match_id = v_match) THEN
        RETURN NULL;                                  -- match deleted (cascade); nothing to check
    END IF;

    SELECT count(*),
           max(item_id) FILTER (WHERE role = 'lost'),
           max(item_id) FILTER (WHERE role = 'found')
      INTO v_n, v_lost, v_found
      FROM match_item WHERE match_id = v_match;

    IF v_n <> 2 OR v_lost IS NULL OR v_found IS NULL THEN
        RAISE EXCEPTION 'match % must pair exactly one lost and one found item', v_match
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM match_item mi JOIN item i USING (item_id)
               WHERE mi.match_id = v_match AND mi.role <> i.item_type) THEN
        RAISE EXCEPTION 'match % has a participant whose role differs from its item_type', v_match
            USING ERRCODE = 'check_violation';
    END IF;
    IF (SELECT pair_key FROM match WHERE match_id = v_match) <> v_lost || ':' || v_found THEN
        RAISE EXCEPTION 'match % pair_key does not match its participants', v_match
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER trg_match_integrity
    AFTER INSERT OR UPDATE ON match
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_match_integrity();
CREATE CONSTRAINT TRIGGER trg_match_item_integrity
    AFTER INSERT OR UPDATE OR DELETE ON match_item
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_match_integrity();

-- ---- CLAIM: validation, state machine, approval cascade -----------------
CREATE FUNCTION claim_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_type     item_type;
    v_status   item_status;
    v_reporter bigint;
    v_role     user_role;
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- FOR SHARE: waits for a concurrent approval (which holds FOR UPDATE on the
        -- item) and then sees status = 'claimed', so late claims are refused.
        SELECT item_type, status, reporter_id INTO v_type, v_status, v_reporter
          FROM item WHERE item_id = NEW.item_id FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'item % not found', NEW.item_id USING ERRCODE = 'LF003';
        END IF;
        IF v_type <> 'found' THEN
            RAISE EXCEPTION 'claims must target a found item' USING ERRCODE = 'LF002';
        END IF;
        IF v_status NOT IN ('open', 'matched') THEN
            RAISE EXCEPTION 'item % is % and cannot be claimed', NEW.item_id, v_status
                USING ERRCODE = 'LF002';
        END IF;
        IF v_reporter = NEW.claimant_id THEN
            RAISE EXCEPTION 'you cannot claim an item you reported yourself' USING ERRCODE = 'LF002';
        END IF;
        IF NEW.match_id IS NOT NULL AND NOT EXISTS (
               SELECT 1 FROM match_item WHERE match_id = NEW.match_id AND item_id = NEW.item_id) THEN
            RAISE EXCEPTION 'match % does not involve item %', NEW.match_id, NEW.item_id
                USING ERRCODE = 'LF002';
        END IF;
        IF NEW.result <> 'pending' OR NEW.verification_status <> 'pending' THEN
            RAISE EXCEPTION 'new claims must be pending' USING ERRCODE = 'LF002';
        END IF;
        RETURN NEW;
    END IF;

    -- UPDATE
    IF NEW.item_id <> OLD.item_id OR NEW.claimant_id <> OLD.claimant_id
       OR NEW.proof_description <> OLD.proof_description
       OR NEW.proof_image_url IS DISTINCT FROM OLD.proof_image_url
       OR NEW.submitted_at <> OLD.submitted_at THEN
        RAISE EXCEPTION 'claim evidence and ownership are immutable' USING ERRCODE = 'LF002';
    END IF;
    IF OLD.result <> 'pending' THEN
        RAISE EXCEPTION 'claim % is already decided (%)', OLD.claim_id, OLD.result
            USING ERRCODE = 'LF002';
    END IF;
    -- pending -> under_review | verified | rejected ; under_review -> verified | rejected
    IF NEW.verification_status <> OLD.verification_status
       AND NOT ((OLD.verification_status, NEW.verification_status) IN (
                ('pending','under_review'), ('pending','verified'), ('pending','rejected'),
                ('under_review','verified'), ('under_review','rejected'))) THEN
        RAISE EXCEPTION 'illegal claim transition % -> %', OLD.verification_status,
            NEW.verification_status USING ERRCODE = 'LF002';
    END IF;
    IF NEW.reviewed_by IS NOT NULL THEN
        SELECT role INTO v_role FROM users WHERE user_id = NEW.reviewed_by;
        IF v_role IS NULL OR v_role NOT IN ('staff', 'admin') THEN
            RAISE EXCEPTION 'only staff or admin can review claims' USING ERRCODE = 'LF001';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_claim_guard BEFORE INSERT OR UPDATE ON claim
    FOR EACH ROW EXECUTE FUNCTION claim_guard();

-- When a claim is approved: the item becomes 'claimed' and every competing
-- open claim on the same item is auto-rejected, all inside the approver's
-- transaction. The linked match (if any) becomes 'confirmed'.
CREATE FUNCTION claim_after_approval() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE claim
       SET verification_status = 'rejected',
           result              = 'denied',
           reviewed_by         = NEW.reviewed_by,
           reviewed_at         = now(),
           notes = concat_ws(E'\n', notes,
                             'Auto-rejected: claim ' || NEW.claim_id || ' was approved for this item.')
     WHERE item_id = NEW.item_id AND claim_id <> NEW.claim_id AND result = 'pending';

    UPDATE item SET status = 'claimed' WHERE item_id = NEW.item_id;

    IF NEW.match_id IS NOT NULL THEN
        UPDATE match SET verification_status = 'confirmed'
         WHERE match_id = NEW.match_id AND verification_status = 'suggested';
    END IF;
    RETURN NULL;
END $$;

CREATE TRIGGER trg_claim_after_approval AFTER UPDATE OF result ON claim
    FOR EACH ROW WHEN (NEW.result = 'approved' AND OLD.result IS DISTINCT FROM 'approved')
    EXECUTE FUNCTION claim_after_approval();

-- ---- AUDIT ---------------------------------------------------------------
-- SECURITY DEFINER: the application role can cause audit rows but cannot write
-- or edit audit_log directly. Secrets / bulky columns are stripped.
CREATE FUNCTION audit_row() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    v_old jsonb := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) - 'password_hash' - 'search_tsv' END;
    v_new jsonb := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) - 'password_hash' - 'search_tsv' END;
    v_pk  bigint := (COALESCE(v_new, v_old) ->> TG_ARGV[0])::bigint;
BEGIN
    -- ignore no-op updates (only updated_at moved)
    IF TG_OP = 'UPDATE' AND (v_old - 'updated_at') = (v_new - 'updated_at') THEN
        RETURN NULL;
    END IF;
    INSERT INTO audit_log (table_name, row_pk, action, actor_id, old_data, new_data)
    VALUES (TG_TABLE_NAME, v_pk, TG_OP,
            nullif(current_setting('app.user_id', true), '')::bigint, v_old, v_new);
    RETURN NULL;
END $$;

CREATE TRIGGER trg_audit_item  AFTER INSERT OR UPDATE OR DELETE ON item
    FOR EACH ROW EXECUTE FUNCTION audit_row('item_id');
CREATE TRIGGER trg_audit_claim AFTER INSERT OR UPDATE OR DELETE ON claim
    FOR EACH ROW EXECUTE FUNCTION audit_row('claim_id');
CREATE TRIGGER trg_audit_match AFTER INSERT OR UPDATE OR DELETE ON match
    FOR EACH ROW EXECUTE FUNCTION audit_row('match_id');
CREATE TRIGGER trg_audit_users AFTER UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_row('user_id');

-- ---- OUTBOX (transactional outbox pattern) ------------------------------
-- The business write and its event commit or roll back together; the worker
-- relays events to Qdrant / Mongo / Redis at-least-once.
CREATE FUNCTION enqueue_outbox() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    v_row jsonb := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
BEGIN
    INSERT INTO outbox (aggregate, aggregate_id, event_type, payload)
    VALUES (TG_ARGV[0], (v_row ->> TG_ARGV[1])::bigint,
            TG_ARGV[0] || '.' || lower(TG_OP),
            v_row - 'password_hash' - 'search_tsv' - 'text_vect' - 'image_vector' - 'image_urls'
                  - 'proof_description' - 'proof_image_url');
    RETURN NULL;
END $$;

CREATE TRIGGER trg_outbox_item  AFTER INSERT OR UPDATE OR DELETE ON item
    FOR EACH ROW EXECUTE FUNCTION enqueue_outbox('item', 'item_id');
CREATE TRIGGER trg_outbox_match AFTER INSERT OR UPDATE ON match
    FOR EACH ROW EXECUTE FUNCTION enqueue_outbox('match', 'match_id');
CREATE TRIGGER trg_outbox_claim AFTER INSERT OR UPDATE ON claim
    FOR EACH ROW EXECUTE FUNCTION enqueue_outbox('claim', 'claim_id');

-- Embedding events carry only the item id (the vectors stay out of the payload).
CREATE FUNCTION enqueue_outbox_embedding() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    INSERT INTO outbox (aggregate, aggregate_id, event_type, payload)
    VALUES ('embedding', NEW.item_id, 'embedding.' || lower(TG_OP),
            jsonb_build_object('item_id', NEW.item_id, 'has_image', NEW.image_vector IS NOT NULL));
    RETURN NULL;
END $$;

CREATE TRIGGER trg_outbox_embedding AFTER INSERT OR UPDATE ON embedding
    FOR EACH ROW EXECUTE FUNCTION enqueue_outbox_embedding();
