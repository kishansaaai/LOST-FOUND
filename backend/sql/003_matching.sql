-- =====================================================================
-- 003  Matching engine: Reciprocal Rank Fusion in SQL
--
--   rrf_score(d) = sum over rankings r of  1 / (k + rank_r(d)),   k = 60
--
-- Two rankings are fused: text (MiniLM cosine) and image (CLIP cosine).
-- Ranks are positions inside the candidate pool, so RRF is scale-free:
-- text and image similarities live on different scales and are never mixed.
-- =====================================================================

-- Pure fusion step. NULL rank = "not present in that ranking".
CREATE FUNCTION rrf_fuse(p_text_rank integer, p_image_rank integer, p_k integer DEFAULT 60)
RETURNS double precision LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
        WHEN p_text_rank IS NULL AND p_image_rank IS NULL THEN NULL
        ELSE COALESCE(1.0::float8 / (p_k + p_text_rank),  0)
           + COALESCE(1.0::float8 / (p_k + p_image_rank), 0)
    END
$$;

-- find_matches: rank opposite-type open items for one item. Read-only.
--
-- Step 1  candidate filter   : opposite item_type, status 'open', plausible time
--                              window (found date >= lost date).
-- Step 2  text ranking       : cosine distance on text_vect, top p_pool (HNSW).
-- Step 3  image ranking      : cosine distance on image_vector, only when both
--                              sides have an image.
-- Step 4  fusion             : FULL JOIN of the two rankings + rrf_fuse().
-- Step 5  gate               : keep a candidate only if it is genuinely similar
--                              (text >= p_min_text OR image >= p_min_image). RRF alone is
--                              rank-based, so without a floor the least-bad candidate
--                              would always "match".
-- Step 6  explainable boost  : tiny additive nudge for same category / location /
--                              colour / brand. Reported separately; rrf_score stays pure.
--
-- hnsw.iterative_scan lets the HNSW index keep scanning when the filter in
-- Step 1 discards many of the nearest neighbours (pgvector >= 0.8).
CREATE FUNCTION find_matches(
    p_item_id   bigint,
    p_limit     integer DEFAULT 10,
    p_min_text  real    DEFAULT 0.60,
    p_min_image real    DEFAULT 0.90,
    p_pool      integer DEFAULT 100,
    p_k         integer DEFAULT 60)
RETURNS TABLE (candidate_id bigint, rrf_score double precision, boost real,
               text_score real, image_score real, text_rank integer, image_rank integer)
LANGUAGE plpgsql STABLE
SET hnsw.iterative_scan = 'strict_order'
AS $$
#variable_conflict use_column
DECLARE
    v_type  item_type;
    v_other item_type;                            -- the opposite type
    v_date  date;
    v_lo    date;                                 -- candidate date window [v_lo, v_hi]
    v_hi    date;
    v_cat   item_category;
    v_color text;
    v_brand text;
    v_loc   bigint;
    v_text  vector(384);
    v_img   vector(512);
BEGIN
    SELECT i.item_type, i.date_lost_or_found, i.category, lower(i.color), lower(i.brand),
           i.location_id, e.text_vect, e.image_vector
      INTO v_type, v_date, v_cat, v_color, v_brand, v_loc, v_text, v_img
      FROM item i JOIN embedding e ON e.item_id = i.item_id
     WHERE i.item_id = p_item_id;
    IF NOT FOUND THEN
        RETURN;                                   -- no embedding yet: nothing to rank
    END IF;
    -- Equality + range predicates (not <> / CASE) so the planner can use the partial index
    -- item_open_type_date_idx; then cost depends on the candidate set, not on table size.
    v_other := CASE WHEN v_type = 'lost' THEN 'found'::item_type ELSE 'lost'::item_type END;
    v_lo := CASE WHEN v_type = 'lost'  THEN v_date ELSE '-infinity'::date END;   -- found on/after lost
    v_hi := CASE WHEN v_type = 'found' THEN v_date ELSE 'infinity'::date  END;

    RETURN QUERY
    WITH cand AS (
        SELECT c.item_id, c.category, c.location_id, lower(c.color) AS color, lower(c.brand) AS brand
          FROM item c
         WHERE c.status = 'open'
           AND c.item_type = v_other
           AND c.item_id <> p_item_id
           AND c.date_lost_or_found BETWEEN v_lo AND v_hi
    ),
    t AS (                                        -- text ranking
        SELECT s.item_id, (1 - s.dist)::real AS score,
               (row_number() OVER (ORDER BY s.dist, s.item_id))::integer AS rnk
          FROM (SELECT e.item_id, e.text_vect <=> v_text AS dist
                  FROM embedding e JOIN cand ON cand.item_id = e.item_id
                 ORDER BY e.text_vect <=> v_text
                 LIMIT p_pool) s
    ),
    im AS (                                       -- image ranking (only if we have an image)
        SELECT s.item_id, (1 - s.dist)::real AS score,
               (row_number() OVER (ORDER BY s.dist, s.item_id))::integer AS rnk
          FROM (SELECT e.item_id, e.image_vector <=> v_img AS dist
                  FROM embedding e JOIN cand ON cand.item_id = e.item_id
                 WHERE v_img IS NOT NULL AND e.image_vector IS NOT NULL
                 ORDER BY e.image_vector <=> v_img
                 LIMIT p_pool) s
    ),
    fused AS (
        SELECT COALESCE(t.item_id, im.item_id) AS item_id,
               t.score AS text_score, im.score AS image_score,
               t.rnk   AS text_rank,  im.rnk   AS image_rank
          FROM t FULL JOIN im ON im.item_id = t.item_id
    )
    SELECT r.item_id, r.rrf, r.bst, r.t_score, r.i_score, r.t_rank, r.i_rank
      FROM (
        SELECT f.item_id,
               rrf_fuse(f.text_rank, f.image_rank, p_k) AS rrf,
               (  CASE WHEN c.category    = v_cat   THEN 0.0020 ELSE 0 END
                + CASE WHEN c.location_id = v_loc   THEN 0.0010 ELSE 0 END
                + CASE WHEN c.color       = v_color THEN 0.0005 ELSE 0 END
                + CASE WHEN c.brand       = v_brand THEN 0.0005 ELSE 0 END)::real AS bst,
               f.text_score AS t_score, f.image_score AS i_score,
               f.text_rank AS t_rank, f.image_rank AS i_rank
          FROM fused f JOIN cand c ON c.item_id = f.item_id
         WHERE f.text_score >= p_min_text OR f.image_score >= p_min_image
      ) r
     ORDER BY r.rrf + r.bst DESC, r.item_id        -- best fused score first (NOT positional: "ORDER BY 2 + 3" would be a constant)
     LIMIT p_limit;
END $$;

-- persist_match: store ONE scored candidate pair. Used by refresh_matches (pg backend)
-- and directly by the application when the Qdrant backend produced the ranking, so
-- both backends share exactly the same uniqueness / immutability rules.
-- Idempotent: the pair is UNIQUE (pair_key); an existing 'suggested' match gets fresh
-- scores, confirmed/rejected matches are left alone (a rejected pair is never
-- re-suggested). Returns no row when the pair was already decided.
CREATE FUNCTION persist_match(
    p_item_id      bigint,
    p_candidate_id bigint,
    p_rrf_score    double precision,
    p_boost        real,
    p_text_score   real,
    p_image_score  real,
    p_text_rank    integer,
    p_image_rank   integer)
RETURNS TABLE (out_match_id bigint, out_is_new boolean)
LANGUAGE plpgsql AS $$
DECLARE
    v_type  item_type;
    v_lost  bigint;
    v_found bigint;
    v_id    bigint;
    v_new   boolean;
BEGIN
    SELECT item_type INTO v_type FROM item WHERE item_id = p_item_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'item % not found', p_item_id USING ERRCODE = 'LF003';
    END IF;
    v_lost  := CASE WHEN v_type = 'lost'  THEN p_item_id ELSE p_candidate_id END;
    v_found := CASE WHEN v_type = 'found' THEN p_item_id ELSE p_candidate_id END;

    INSERT INTO match AS m (pair_key, rrf_score, boost, text_score, image_score, text_rank, image_rank)
    VALUES (v_lost || ':' || v_found, p_rrf_score, p_boost, p_text_score, p_image_score,
            p_text_rank, p_image_rank)
    ON CONFLICT (pair_key) DO UPDATE
       SET rrf_score = EXCLUDED.rrf_score, boost = EXCLUDED.boost,
           text_score = EXCLUDED.text_score, image_score = EXCLUDED.image_score,
           text_rank = EXCLUDED.text_rank, image_rank = EXCLUDED.image_rank
     WHERE m.verification_status = 'suggested'
    RETURNING m.match_id, (xmax = 0) INTO v_id, v_new;       -- xmax = 0  <=>  freshly inserted

    IF v_id IS NULL THEN
        RETURN;                                              -- decided earlier: leave it alone
    END IF;
    IF v_new THEN
        INSERT INTO match_item (match_id, item_id, role)
        VALUES (v_id, v_lost, 'lost'), (v_id, v_found, 'found');
    END IF;
    out_match_id := v_id; out_is_new := v_new;
    RETURN NEXT;
END $$;

-- refresh_matches: rank with find_matches() and persist the top candidates in the
-- caller's transaction (one transaction => all-or-nothing).
CREATE FUNCTION refresh_matches(
    p_item_id   bigint,
    p_limit     integer DEFAULT 10,
    p_min_text  real    DEFAULT 0.60,
    p_min_image real    DEFAULT 0.90)
RETURNS TABLE (out_match_id bigint, out_candidate_id bigint, out_rrf_score double precision,
               out_is_new boolean)
LANGUAGE plpgsql AS $$
DECLARE
    r record;
    p record;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM item WHERE item_id = p_item_id AND status = 'open') THEN
        RETURN;                                   -- only open items are matched
    END IF;
    -- Persist in ONE global order (lost id, then found id). Two sessions that insert overlapping pairs in different
    -- orders (the worker and a user pressing "Find matches", or two workers) would otherwise deadlock on the pair_key
    -- unique index; with a total order every session waits in the same direction, so no cycle can form.
    FOR r IN SELECT * FROM find_matches(p_item_id, p_limit, p_min_text, p_min_image) f
              ORDER BY (SELECT CASE WHEN i.item_type = 'lost' THEN p_item_id ELSE f.candidate_id END FROM item i WHERE i.item_id = p_item_id),
                       (SELECT CASE WHEN i.item_type = 'found' THEN p_item_id ELSE f.candidate_id END FROM item i WHERE i.item_id = p_item_id)
    LOOP
        SELECT * INTO p FROM persist_match(p_item_id, r.candidate_id, r.rrf_score, r.boost,
                                           r.text_score, r.image_score, r.text_rank, r.image_rank);
        IF FOUND THEN
            out_match_id := p.out_match_id; out_candidate_id := r.candidate_id;
            out_rrf_score := r.rrf_score;   out_is_new := p.out_is_new;
            RETURN NEXT;
        END IF;
    END LOOP;
END $$;
