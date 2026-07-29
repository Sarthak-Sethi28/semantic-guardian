## 🛡️ Semantic Guardian — review of this change

**BREAKING semantic change detected** on `account_status` (categorical remap).

**What changed** — the diff inverts the encoding:
```sql
- account_status
+ case when account_status = 1 then 0 else 1 end as account_status
```

**Why it matters** — the DataHub catalog declares `1 = active, 0 = deleted`. This CASE flips
every value's meaning while leaving the value set and distribution **identical**, so statistical
monitors are blind to it. Downstream models reading `account_status` are now inverted.

**Competing hypotheses**
1. Intentional re-encoding to a different convention (0 = active) — still breaks the declared contract.
2. An accidental logic reversal.

**Blast radius** — severity `medium`; 1 downstream ML feature affected. Routed to owner `jdoe`.

**Recommendation** — confirm intent. If unintended, revert the CASE. On confirmation, Semantic
Guardian compiles a durable DataHub assertion so this exact break is caught deterministically next time.

*Confidence — code: 0.97 · catalog: 0.80 · stats: 0.00 (invisible to stats)*
