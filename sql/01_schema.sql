CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE IF NOT EXISTS sales.daily_sales (
    sales_date   date PRIMARY KEY,
    order_count  bigint NOT NULL CHECK (order_count >= 0),
    units_sold   bigint NOT NULL CHECK (units_sold >= order_count),
    gross_cents  bigint NOT NULL CHECK (gross_cents >= 0),
    refund_cents bigint NOT NULL CHECK (refund_cents BETWEEN 0 AND gross_cents),
    net_cents    bigint NOT NULL CHECK (net_cents = gross_cents - refund_cents)
);

CREATE TABLE IF NOT EXISTS sales.daily_channel_sales (
    sales_date   date NOT NULL,
    channel      text NOT NULL CHECK (channel IN ('marketplace', 'web')),
    order_count  bigint NOT NULL CHECK (order_count >= 0),
    units_sold   bigint NOT NULL CHECK (units_sold >= order_count),
    gross_cents  bigint NOT NULL CHECK (gross_cents >= 0),
    refund_cents bigint NOT NULL CHECK (refund_cents BETWEEN 0 AND gross_cents),
    net_cents    bigint NOT NULL CHECK (net_cents = gross_cents - refund_cents),
    PRIMARY KEY (sales_date, channel)
);
