-- =====================================================================
-- 001  Core schema (3NF).  Mirrors the Chen ER diagram in
--      docs/reference/er-diagram.pdf; extra columns are implementation
--      detail, extra tables (audit_log, outbox) are infrastructure.
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ---- Enumerated domains ------------------------------------------------
CREATE TYPE user_role           AS ENUM ('user', 'staff', 'admin');
CREATE TYPE item_type           AS ENUM ('lost', 'found');
CREATE TYPE item_status         AS ENUM ('open', 'matched', 'claimed', 'returned', 'closed');
CREATE TYPE item_category       AS ENUM ('electronics', 'wallet_bag', 'keys', 'id_card', 'clothing',
                                         'jewelry', 'documents', 'pet', 'other');
CREATE TYPE match_status        AS ENUM ('suggested', 'confirmed', 'rejected');
CREATE TYPE verification_status AS ENUM ('pending', 'under_review', 'verified', 'rejected');
CREATE TYPE claim_result        AS ENUM ('pending', 'approved', 'denied');

-- ---- USER  ("user" is reserved in PostgreSQL, so the table is `users`) ---
CREATE TABLE users (
    user_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          text        NOT NULL CHECK (char_length(btrim(name)) > 0),
    email         text        NOT NULL CHECK (email = btrim(email) AND position('@' in email) > 1),
    password_hash text        NOT NULL,
    phone         text,
    role          user_role   NOT NULL DEFAULT 'user',
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Case-insensitive uniqueness without the citext extension.
CREATE UNIQUE INDEX users_email_lower_uq ON users (lower(email));

-- ---- LOCATION ------------------------------------------------------------
CREATE TABLE location (
    location_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    location_name text NOT NULL UNIQUE,
    campus        text NOT NULL,
    building      text,
    floor         text,
    address       text,
    latitude      numeric(9,6) CHECK (latitude  BETWEEN  -90 AND  90),
    longitude     numeric(9,6) CHECK (longitude BETWEEN -180 AND 180),
    CHECK ((latitude IS NULL) = (longitude IS NULL))         -- both or neither
);

-- ---- ITEM ----------------------------------------------------------------
-- REPORTS   : users 1 --- N item        (item.reporter_id)
-- OCCURS_AT : location 1 --- N item     (item.location_id)
-- ON DELETE RESTRICT: an account or place with history can never silently
-- vanish; deactivation is a business action, not a cascade.
CREATE TABLE item (
    item_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reporter_id        bigint        NOT NULL REFERENCES users(user_id)       ON DELETE RESTRICT,
    location_id        bigint        NOT NULL REFERENCES location(location_id) ON DELETE RESTRICT,
    item_type          item_type     NOT NULL,
    status             item_status   NOT NULL DEFAULT 'open',
    title              text          NOT NULL CHECK (char_length(title) BETWEEN 3 AND 200),
    description        text          NOT NULL CHECK (char_length(btrim(description)) > 0),
    category           item_category NOT NULL,
    color              text,
    brand              text,
    -- "not in the future" cannot be a CHECK (current_date is not immutable and
    -- breaks dump/restore re-validation); see trg_item_validate_date in 002.
    date_lost_or_found date          NOT NULL,
    image_urls         text[]        NOT NULL DEFAULT '{}',
    -- Generated tsvector: kept in sync by the engine, no trigger needed.
    search_tsv         tsvector GENERATED ALWAYS AS (
                           to_tsvector('english',
                               coalesce(title, '')       || ' ' ||
                               coalesce(description, '') || ' ' ||
                               coalesce(brand, '')       || ' ' ||
                               coalesce(color, ''))
                       ) STORED,
    reported_at        timestamptz   NOT NULL DEFAULT now(),
    updated_at         timestamptz   NOT NULL DEFAULT now()
);
CREATE INDEX item_reporter_idx ON item (reporter_id);
CREATE INDEX item_location_idx ON item (location_id);
CREATE INDEX item_date_idx     ON item (date_lost_or_found);
CREATE INDEX item_search_gin   ON item USING gin (search_tsv);
-- Partial index: matching and browsing only ever touch open items.
CREATE INDEX item_open_idx     ON item (item_type, category, date_lost_or_found)
    WHERE status = 'open';
-- Matching asks "open items of the opposite type inside a date window" (no category).
CREATE INDEX item_open_type_date_idx ON item (item_type, date_lost_or_found)
    WHERE status = 'open';

-- ---- EMBEDDING  (HAS_EMBEDDING 1:1 via UNIQUE FK) ------------------------
CREATE TABLE embedding (
    embedding_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id      bigint      NOT NULL UNIQUE REFERENCES item(item_id) ON DELETE CASCADE,
    text_vect    vector(384) NOT NULL,        -- all-MiniLM-L6-v2
    image_vector vector(512),                 -- CLIP ViT-B/32; NULL when the item has no photo
    model_name   text        NOT NULL,
    content_hash text,                        -- hash of the inputs; unchanged => skip re-embedding
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX embedding_text_hnsw  ON embedding USING hnsw (text_vect vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX embedding_image_hnsw ON embedding USING hnsw (image_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64) WHERE image_vector IS NOT NULL;

-- ---- MATCH ---------------------------------------------------------------
-- The ER diagram puts verification_status on MATCH; it is kept here as the
-- staff confirmation state of a suggested match.
-- pair_key = '<lost_item_id>:<found_item_id>' is a deliberate denormalisation:
-- a junction table cannot express "this pair exists at most once" on its own.
-- A deferred constraint trigger (002) proves pair_key agrees with match_item.
CREATE TABLE match (
    match_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pair_key            text             NOT NULL UNIQUE,
    rrf_score           double precision NOT NULL CHECK (rrf_score > 0),
    text_score          real,
    image_score         real,
    text_rank           integer CHECK (text_rank  > 0),
    image_rank          integer CHECK (image_rank > 0),
    boost               real             NOT NULL DEFAULT 0 CHECK (boost >= 0),  -- ordering nudge; rrf_score stays pure
    verification_status match_status     NOT NULL DEFAULT 'suggested',
    created_at          timestamptz      NOT NULL DEFAULT now(),
    CHECK (text_score IS NOT NULL OR image_score IS NOT NULL),
    CHECK ((text_score  IS NULL) = (text_rank  IS NULL)),
    CHECK ((image_score IS NULL) = (image_rank IS NULL))
);

-- ---- PARTICIPATES_IN  (ITEM N:N MATCH) -----------------------------------
CREATE TABLE match_item (
    match_id bigint    NOT NULL REFERENCES match(match_id) ON DELETE CASCADE,
    item_id  bigint    NOT NULL REFERENCES item(item_id)   ON DELETE CASCADE,
    role     item_type NOT NULL,                      -- must equal item.item_type (trigger)
    PRIMARY KEY (match_id, item_id),
    UNIQUE (match_id, role)                           -- at most one lost + one found per match
);
CREATE INDEX match_item_item_idx ON match_item (item_id);

-- ---- CLAIM ---------------------------------------------------------------
-- TARGETS   : item 1 --- N claim    (claim.item_id: the FOUND item being claimed)
-- SUBMITS   : users 1 --- N claim   (claim.claimant_id)
-- RESULTS_IN: match 1 --- N claim   (claim.match_id, nullable)
CREATE TABLE claim (
    claim_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id             bigint              NOT NULL REFERENCES item(item_id)   ON DELETE RESTRICT,
    claimant_id         bigint              NOT NULL REFERENCES users(user_id)  ON DELETE RESTRICT,
    match_id            bigint                       REFERENCES match(match_id) ON DELETE SET NULL,
    proof_description   text                NOT NULL CHECK (char_length(btrim(proof_description)) > 0),
    proof_image_url     text,
    verification_status verification_status NOT NULL DEFAULT 'pending',
    result              claim_result        NOT NULL DEFAULT 'pending',
    submitted_at        timestamptz         NOT NULL DEFAULT now(),
    reviewed_by         bigint                       REFERENCES users(user_id)  ON DELETE RESTRICT,
    reviewed_at         timestamptz,
    notes               text,
    -- result and verification_status can never contradict each other
    CHECK ((result = 'pending')  = (verification_status IN ('pending', 'under_review'))),
    CHECK ((result = 'approved') = (verification_status = 'verified')),
    -- a decided claim always records who decided it and when
    CHECK (result = 'pending' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
    CHECK (reviewed_by IS DISTINCT FROM claimant_id)  -- nobody reviews their own claim
);
-- One live claim per (item, claimant).
CREATE UNIQUE INDEX claim_one_pending_per_user ON claim (item_id, claimant_id) WHERE result = 'pending';
-- Schema-level backstop for the concurrency story: even if app logic or
-- locking were wrong, two approved claims on one item cannot both commit.
CREATE UNIQUE INDEX claim_one_approved_per_item ON claim (item_id) WHERE result = 'approved';
CREATE INDEX claim_queue_idx    ON claim (submitted_at) WHERE result = 'pending';
CREATE INDEX claim_claimant_idx ON claim (claimant_id);
CREATE INDEX claim_match_idx    ON claim (match_id) WHERE match_id IS NOT NULL;

-- ---- Infrastructure tables (not domain entities) ---------------------------
CREATE TABLE audit_log (
    audit_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    table_name text        NOT NULL,
    row_pk     bigint      NOT NULL,
    action     text        NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    actor_id   bigint,                                  -- set_config('app.user_id', ...) by the API
    old_data   jsonb,
    new_data   jsonb,
    changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_row_idx  ON audit_log (table_name, row_pk, changed_at DESC);
CREATE INDEX audit_time_idx ON audit_log USING brin (changed_at);

-- Transactional outbox: written in the same transaction as the business
-- change, relayed to Qdrant / Mongo / Redis by the worker (at-least-once,
-- handlers are idempotent).
CREATE TABLE outbox (
    outbox_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate    text        NOT NULL,
    aggregate_id bigint      NOT NULL,
    event_type   text        NOT NULL,
    payload      jsonb       NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    attempts     integer     NOT NULL DEFAULT 0,
    last_error   text
);
CREATE INDEX outbox_pending_idx ON outbox (outbox_id) WHERE processed_at IS NULL;
