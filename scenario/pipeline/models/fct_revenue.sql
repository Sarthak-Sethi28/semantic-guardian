-- fct_revenue: per-order revenue fact.
-- CONTRACT: `revenue` is in USD dollars (not cents). See DataHub glossary term Money.USD_Dollars.
select
    order_id,
    customer_id,
    revenue,
    created_at
from {{ ref('stg_orders') }}
