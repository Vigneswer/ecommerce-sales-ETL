-- Run in psql from the project root after writing the default output directory.
BEGIN;

CREATE TEMP TABLE load_daily (LIKE sales.daily_sales) ON COMMIT DROP;
CREATE TEMP TABLE load_channel (LIKE sales.daily_channel_sales) ON COMMIT DROP;

\copy load_daily (sales_date, order_count, units_sold, gross_cents, refund_cents, net_cents) FROM 'output/daily_sales.csv' WITH (FORMAT csv, HEADER true)
\copy load_channel (sales_date, channel, order_count, units_sold, gross_cents, refund_cents, net_cents) FROM 'output/daily_channel_sales.csv' WITH (FORMAT csv, HEADER true)

INSERT INTO sales.daily_sales (sales_date, order_count, units_sold, gross_cents, refund_cents, net_cents)
SELECT sales_date, order_count, units_sold, gross_cents, refund_cents, net_cents
FROM load_daily
ON CONFLICT (sales_date) DO UPDATE SET
    order_count  = EXCLUDED.order_count,
    units_sold   = EXCLUDED.units_sold,
    gross_cents  = EXCLUDED.gross_cents,
    refund_cents = EXCLUDED.refund_cents,
    net_cents    = EXCLUDED.net_cents;

INSERT INTO sales.daily_channel_sales (sales_date, channel, order_count, units_sold, gross_cents, refund_cents, net_cents)
SELECT sales_date, channel, order_count, units_sold, gross_cents, refund_cents, net_cents
FROM load_channel
ON CONFLICT (sales_date, channel) DO UPDATE SET
    order_count  = EXCLUDED.order_count,
    units_sold   = EXCLUDED.units_sold,
    gross_cents  = EXCLUDED.gross_cents,
    refund_cents = EXCLUDED.refund_cents,
    net_cents    = EXCLUDED.net_cents;

COMMIT;
