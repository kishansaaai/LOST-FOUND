# Transactions and concurrency

## The problem
Two staff members open the same item's claim queue. Claim A and claim B both target the same found wallet. Both click
**Approve** at the same instant. Exactly one claim may win; the item must end `claimed`; the loser must be told clearly,
and the database must never contain two approved claims for one item.

## The design (`approve_claim`, `backend/sql/004_workflow.sql`)
```
1. SELECT item_id FROM claim WHERE claim_id = :c            -- no lock, just find the item
2. SELECT … FROM item  WHERE item_id = :item FOR UPDATE      -- serialisation point: ONE lock per item
3. SELECT … FROM claim WHERE claim_id = :c FOR UPDATE        -- lock, and RE-READ: a concurrent winner may have rejected it
4. UPDATE claim SET result='approved' …                      -- trigger: item → claimed, rivals → denied, match → confirmed
```
* **Isolation level: `READ COMMITTED` + explicit row locks.** Locking the item first makes every approval, and every claim
  *insert* (which takes `FOR SHARE` on the item in `claim_guard`), queue behind one lock. After the winner commits, the loser
  acquires the lock, re-reads its claim in a *new statement* (which sees the winner's changes under READ COMMITTED) and fails
  with `LF002 "claim … is already denied"` → HTTP 409.
* **Why not SERIALIZABLE / REPEATABLE READ?** Both would also be correct, but the loser would receive `40001
  serialization_failure` and every caller would need retry logic, for no extra safety here: the contested resource is one row.
* **Lock order matters.** Locking the claim *before* the item deadlocks: the approver's trigger updates the rival claim row,
  which the other approver already holds, while that approver waits for the item lock held by the first. Item-then-claim is
  a total order, so there is no cycle.
* **Last line of defence:** `UNIQUE INDEX claim_one_approved_per_item … WHERE result='approved'`. Even if the procedure were
  bypassed (raw SQL, a buggy deploy), two approvals cannot both commit.
* A claim submitted *while* an approval is in flight waits on the item lock, then sees `status='claimed'` and is refused.

## Proof (tests/db/test_concurrency.py)
1. `test_second_approver_blocks_then_fails`: session A approves and holds its transaction open; session B calls
   `approve_claim` for the rival claim and is shown **blocked on a lock** in `pg_stat_activity.wait_event_type = 'Lock'`;
   A commits; B fails with `LF002`; exactly one claim is approved. No sleeps-and-hope: the test observes the wait.
2. `test_stress_exactly_one_winner`: 20 rounds of two simultaneous approvers released by a barrier. Every round: one `ok`,
   one `LF002`, one approved row, no deadlock.
3. `test_unique_index_is_the_backstop_even_without_the_procedure`: a raw second approval is rejected by the index.

## Other transactional guarantees
* `refresh_matches` persists a match and its two `match_item` rows in one transaction; the deferred integrity trigger checks the
  pair at commit.
* `confirm_match` locks the match, confirms it, moves both items to `matched` and rejects rival suggestions atomically.
* `mark_returned` returns the found item and every confirmed-matched lost report in one transaction.
* The outbox row is inserted by trigger in the same transaction as the change, so an event exists **iff** the change committed
  ([consistency.md](consistency.md)).
