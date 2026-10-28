-- =====================================================================
-- 004  Workflow procedures: claims, matches, returns
--
-- Concurrency design for approve_claim (see docs/concurrency.md):
--   Isolation: READ COMMITTED + explicit row locks. Every approval takes
--   `SELECT ... FOR UPDATE` on the ITEM row first, so all approvals/claim
--   inserts for one item are serialised on a single lock, then locks the
--   claim row and re-reads it. A second approver blocks on the item lock,
--   wakes up after the first COMMITs, re-reads the claim (now auto-rejected)
--   and fails with LF002. Locking the item before the claim also avoids the
--   deadlock that would arise from the approval trigger touching competing
--   claim rows. The partial unique index claim_one_approved_per_item is the
--   last line of defence even if locking were bypassed.
--   REPEATABLE READ/SERIALIZABLE would also be correct but would turn the
--   conflict into SQLSTATE 40001 and force client retries for no benefit.
-- =====================================================================
CREATE FUNCTION assert_staff(p_user_id bigint) RETURNS void LANGUAGE plpgsql STABLE AS $$
DECLARE v_role user_role;
BEGIN
    SELECT role INTO v_role FROM users WHERE user_id = p_user_id;
    IF v_role IS NULL OR v_role NOT IN ('staff', 'admin') THEN
        RAISE EXCEPTION 'user % is not staff or admin', p_user_id USING ERRCODE = 'LF001';
    END IF;
END $$;

CREATE FUNCTION start_claim_review(p_claim_id bigint, p_staff_id bigint) RETURNS claim
LANGUAGE plpgsql AS $$
DECLARE v_claim claim;
BEGIN
    PERFORM assert_staff(p_staff_id);
    SELECT * INTO v_claim FROM claim WHERE claim_id = p_claim_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'claim % not found', p_claim_id USING ERRCODE = 'LF003';
    END IF;
    IF v_claim.verification_status <> 'pending' THEN
        RAISE EXCEPTION 'claim % is %, expected pending', p_claim_id, v_claim.verification_status
            USING ERRCODE = 'LF002';
    END IF;
    UPDATE claim SET verification_status = 'under_review', reviewed_by = p_staff_id
     WHERE claim_id = p_claim_id RETURNING * INTO v_claim;
    RETURN v_claim;
END $$;

CREATE FUNCTION approve_claim(p_claim_id bigint, p_staff_id bigint, p_notes text DEFAULT NULL)
RETURNS claim LANGUAGE plpgsql AS $$
DECLARE
    v_item_id bigint;
    v_status  item_status;
    v_claim   claim;
BEGIN
    PERFORM assert_staff(p_staff_id);

    SELECT item_id INTO v_item_id FROM claim WHERE claim_id = p_claim_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'claim % not found', p_claim_id USING ERRCODE = 'LF003';
    END IF;

    -- 1) serialisation point: the item row
    SELECT status INTO v_status FROM item WHERE item_id = v_item_id FOR UPDATE;
    -- 2) now lock and RE-READ the claim: a concurrent winner may have auto-rejected it
    SELECT * INTO v_claim FROM claim WHERE claim_id = p_claim_id FOR UPDATE;

    IF v_claim.result <> 'pending' THEN
        RAISE EXCEPTION 'claim % is already % ', p_claim_id, v_claim.result USING ERRCODE = 'LF002';
    END IF;
    IF v_status NOT IN ('open', 'matched') THEN
        RAISE EXCEPTION 'item % is % and cannot be claimed', v_item_id, v_status USING ERRCODE = 'LF002';
    END IF;

    UPDATE claim
       SET verification_status = 'verified', result = 'approved',
           reviewed_by = p_staff_id, reviewed_at = now(),
           notes = COALESCE(p_notes, notes)
     WHERE claim_id = p_claim_id
    RETURNING * INTO v_claim;           -- trigger trg_claim_after_approval does the cascade
    RETURN v_claim;
END $$;

CREATE FUNCTION reject_claim(p_claim_id bigint, p_staff_id bigint, p_notes text DEFAULT NULL)
RETURNS claim LANGUAGE plpgsql AS $$
DECLARE v_claim claim;
BEGIN
    PERFORM assert_staff(p_staff_id);
    SELECT * INTO v_claim FROM claim WHERE claim_id = p_claim_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'claim % not found', p_claim_id USING ERRCODE = 'LF003';
    END IF;
    IF v_claim.result <> 'pending' THEN
        RAISE EXCEPTION 'claim % is already %', p_claim_id, v_claim.result USING ERRCODE = 'LF002';
    END IF;
    UPDATE claim
       SET verification_status = 'rejected', result = 'denied',
           reviewed_by = p_staff_id, reviewed_at = now(), notes = COALESCE(p_notes, notes)
     WHERE claim_id = p_claim_id RETURNING * INTO v_claim;
    RETURN v_claim;
END $$;

-- Found item with an approved claim -> returned; the lost reports that were
-- confirmed-matched to it are returned in the same transaction.
CREATE FUNCTION mark_returned(p_item_id bigint, p_staff_id bigint) RETURNS item
LANGUAGE plpgsql AS $$
DECLARE v_item item;
BEGIN
    PERFORM assert_staff(p_staff_id);
    SELECT * INTO v_item FROM item WHERE item_id = p_item_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'item % not found', p_item_id USING ERRCODE = 'LF003';
    END IF;
    IF v_item.item_type <> 'found' OR v_item.status <> 'claimed' THEN
        RAISE EXCEPTION 'only a claimed found item can be marked returned (item % is % %)',
            p_item_id, v_item.item_type, v_item.status USING ERRCODE = 'LF002';
    END IF;

    UPDATE item SET status = 'returned' WHERE item_id = p_item_id RETURNING * INTO v_item;

    UPDATE item l SET status = 'returned'
     WHERE l.status = 'matched' AND l.item_type = 'lost'
       AND EXISTS (SELECT 1 FROM match_item ml
                   JOIN match m       ON m.match_id = ml.match_id AND m.verification_status = 'confirmed'
                   JOIN match_item mf ON mf.match_id = m.match_id AND mf.role = 'found' AND mf.item_id = p_item_id
                   WHERE ml.item_id = l.item_id);
    RETURN v_item;
END $$;

CREATE FUNCTION close_item(p_item_id bigint, p_actor_id bigint) RETURNS item
LANGUAGE plpgsql AS $$
DECLARE v_item item; v_role user_role;
BEGIN
    SELECT * INTO v_item FROM item WHERE item_id = p_item_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'item % not found', p_item_id USING ERRCODE = 'LF003';
    END IF;
    SELECT role INTO v_role FROM users WHERE user_id = p_actor_id;
    IF v_item.reporter_id <> p_actor_id AND v_role IS DISTINCT FROM 'staff' AND v_role IS DISTINCT FROM 'admin' THEN
        RAISE EXCEPTION 'only the reporter or staff can close an item' USING ERRCODE = 'LF001';
    END IF;
    UPDATE item SET status = 'closed' WHERE item_id = p_item_id RETURNING * INTO v_item;
    -- pending claims on a closed item cannot be decided any more
    UPDATE claim SET verification_status = 'rejected', result = 'denied',
           reviewed_by = CASE WHEN v_role IN ('staff','admin') THEN p_actor_id ELSE NULL END,
           reviewed_at = now(), notes = concat_ws(E'\n', notes, 'Auto-rejected: item closed.')
     WHERE item_id = p_item_id AND result = 'pending' AND v_role IN ('staff', 'admin');
    RETURN v_item;
END $$;

CREATE FUNCTION confirm_match(p_match_id bigint, p_staff_id bigint) RETURNS match
LANGUAGE plpgsql AS $$
DECLARE v_match match;
BEGIN
    PERFORM assert_staff(p_staff_id);
    SELECT * INTO v_match FROM match WHERE match_id = p_match_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'match % not found', p_match_id USING ERRCODE = 'LF003';
    END IF;
    IF v_match.verification_status <> 'suggested' THEN
        RAISE EXCEPTION 'match % is already %', p_match_id, v_match.verification_status USING ERRCODE = 'LF002';
    END IF;
    UPDATE match SET verification_status = 'confirmed' WHERE match_id = p_match_id RETURNING * INTO v_match;
    -- both reports are now spoken for
    UPDATE item SET status = 'matched'
     WHERE status = 'open' AND item_id IN (SELECT item_id FROM match_item WHERE match_id = p_match_id);
    -- every other suggestion that involves either item is stale
    UPDATE match SET verification_status = 'rejected'
     WHERE verification_status = 'suggested' AND match_id <> p_match_id
       AND match_id IN (SELECT match_id FROM match_item
                         WHERE item_id IN (SELECT item_id FROM match_item WHERE match_id = p_match_id));
    RETURN v_match;
END $$;

CREATE FUNCTION reject_match(p_match_id bigint, p_staff_id bigint) RETURNS match
LANGUAGE plpgsql AS $$
DECLARE v_match match;
BEGIN
    PERFORM assert_staff(p_staff_id);
    SELECT * INTO v_match FROM match WHERE match_id = p_match_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'match % not found', p_match_id USING ERRCODE = 'LF003';
    END IF;
    IF v_match.verification_status <> 'suggested' THEN
        RAISE EXCEPTION 'match % is already %', p_match_id, v_match.verification_status USING ERRCODE = 'LF002';
    END IF;
    UPDATE match SET verification_status = 'rejected' WHERE match_id = p_match_id RETURNING * INTO v_match;
    RETURN v_match;
END $$;
