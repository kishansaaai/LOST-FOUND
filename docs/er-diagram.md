# ER diagram

The contract is the Chen diagram in [`reference/er-diagram.pdf`](reference/er-diagram.pdf). This page is the
same model in Mermaid plus the mapping from Chen constructs to tables.

```mermaid
erDiagram
    USERS    ||--o{ ITEM      : "REPORTS (1:N)"
    LOCATION ||--o{ ITEM      : "OCCURS_AT (1:N)"
    ITEM     ||--|| EMBEDDING : "HAS_EMBEDDING (1:1)"
    ITEM     }o--o{ MATCH     : "PARTICIPATES_IN (N:N via match_item)"
    ITEM     ||--o{ CLAIM     : "TARGETS (1:N)"
    USERS    ||--o{ CLAIM     : "SUBMITS (1:N)"
    MATCH    |o--o{ CLAIM     : "RESULTS_IN (1:N, optional)"

    USERS     { bigint user_id PK  user_role role  text name  text email  text password_hash  text phone  timestamptz created_at }
    LOCATION  { bigint location_id PK  text location_name  text campus  text building  text floor  numeric latitude  numeric longitude }
    ITEM      { bigint item_id PK  item_type item_type  item_status status  text title  text description  item_category category  text color  text brand  date date_lost_or_found  text_array image_urls  tsvector search_tsv  bigint reporter_id FK  bigint location_id FK }
    EMBEDDING { bigint embedding_id PK  bigint item_id FK_UNIQUE  vector384 text_vect  vector512 image_vector  text model_name  text content_hash }
    MATCH     { bigint match_id PK  double rrf_score  match_status verification_status  real text_score  real image_score  int text_rank  int image_rank  real boost  text pair_key UNIQUE }
    MATCH_ITEM{ bigint match_id PK_FK  bigint item_id PK_FK  item_type role }
    CLAIM     { bigint claim_id PK  claim_result result  verification_status verification_status  text proof_description  text proof_image_url  bigint item_id FK  bigint claimant_id FK  bigint match_id FK_NULL  bigint reviewed_by FK_NULL  timestamptz reviewed_at  text notes }
```

| Chen construct | Cardinality | Implementation | `ON DELETE` |
|---|---|---|---|
| USER | – | table `users` (`user` is a reserved word in PostgreSQL) | – |
| REPORTS | USER 1 : N ITEM | `item.reporter_id → users` | `RESTRICT` |
| OCCURS_AT | LOCATION 1 : N ITEM | `item.location_id → location` | `RESTRICT` |
| HAS_EMBEDDING | ITEM 1 : 1 EMBEDDING | `embedding.item_id` `UNIQUE` FK | `CASCADE` |
| PARTICIPATES_IN | ITEM N : N MATCH | junction `match_item(match_id, item_id, role)` | `CASCADE` both |
| TARGETS | ITEM 1 : N CLAIM | `claim.item_id → item` (trigger: must be a *found* item) | `RESTRICT` |
| SUBMITS | USER 1 : N CLAIM | `claim.claimant_id → users` | `RESTRICT` |
| RESULTS_IN | MATCH 1 : N CLAIM | `claim.match_id → match`, nullable | `SET NULL` |

`RESTRICT` is deliberate: a user, place or item with history can never silently disappear (deactivation is a
business action, not a cascade). `CASCADE` is used only where the child has no meaning without the parent
(an embedding without its item, a participation without its match).

## Deliberate deviations (all flagged, none structural)

* **`verification_status` appears on MATCH in the diagram and on CLAIM in the brief.** Both exist:
  `claim.verification_status` is the staff verification workflow (`pending / under_review / verified / rejected`);
  `match.verification_status` is the staff decision on a suggestion (`suggested / confirmed / rejected`).
* **Extra tables:** `audit_log` (filled by triggers) and `outbox` (transactional outbox). Both are
  infrastructure required by the brief, neither is a domain entity.
* **Extra columns** are listed in [schema.md](schema.md). The one worth defending is `match.pair_key`
  ([normalization.md](normalization.md)).
