-- What were our daily gross sales, refunds and net sales in USD?
SELECT sales_date, order_count, units_sold,
       round(gross_cents / 100.0, 2) AS gross_usd,
       round(refund_cents / 100.0, 2) AS refund_usd,
       round(net_cents / 100.0, 2) AS net_usd
FROM sales.daily_sales
ORDER BY sales_date;

-- Which channel had the most net sales, and what share of gross was refunded?
SELECT channel, sum(order_count) AS orders,
       round(sum(net_cents) / 100.0, 2) AS net_usd,
       round(100.0 * sum(refund_cents) / nullif(sum(gross_cents), 0), 2) AS refund_pct
FROM sales.daily_channel_sales
GROUP BY channel
ORDER BY net_usd DESC, channel;

-- Do channel totals match the daily rollup? An empty result is a pass.
WITH channel_totals AS (
    SELECT sales_date, count(*) AS channel_count, sum(order_count) AS order_count,
           sum(units_sold) AS units_sold, sum(gross_cents) AS gross_cents,
           sum(refund_cents) AS refund_cents, sum(net_cents) AS net_cents
    FROM sales.daily_channel_sales
    GROUP BY sales_date
)
SELECT sales_date, d.net_cents AS daily_net_cents, c.net_cents AS channel_net_cents
FROM sales.daily_sales d FULL JOIN channel_totals c USING (sales_date)
WHERE c.channel_count IS DISTINCT FROM 2
   OR (d.order_count, d.units_sold, d.gross_cents, d.refund_cents, d.net_cents)
      IS DISTINCT FROM (c.order_count, c.units_sold, c.gross_cents, c.refund_cents, c.net_cents)
ORDER BY sales_date;
