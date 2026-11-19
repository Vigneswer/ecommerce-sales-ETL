# Databricks notebook source
import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


CHANNELS = ('marketplace', 'web')
STATUSES = ('paid', 'completed', 'pending', 'cancelled')
REVENUE_STATUSES = ('paid', 'completed')
SCHEMAS = {
    'orders': ('order_id', 'order_date', 'channel', 'status'),
    'order_items': ('item_id', 'order_id', 'sku', 'quantity', 'unit_price_usd'),
    'refunds': ('refund_id', 'item_id', 'amount_usd'),
}
MEASURES = ('order_count', 'units_sold', 'gross_cents', 'refund_cents')
SALES_FIELDS = ('sales_date', *MEASURES, 'net_cents')
CHANNEL_FIELDS = ('sales_date', 'channel', *MEASURES, 'net_cents')
REJECT_FIELDS = ('source_file', 'line_number', 'reason', 'record')


@dataclass(frozen=True)
class Order:
    order_date: date
    channel: str
    status: str


@dataclass(frozen=True)
class Item:
    order_id: str
    sku: str
    quantity: int
    unit_cents: int

    @property
    def gross_cents(self):
        return self.quantity * self.unit_cents


@dataclass(frozen=True)
class Refund:
    item_id: str
    amount_cents: int


@dataclass(frozen=True)
class SourceRecord:
    source_file: str
    line_number: int
    raw: dict
    value: object


@dataclass(frozen=True)
class SalesLine:
    order_id: str
    channel: str
    units_sold: int
    gross_cents: int
    refund_cents: int


def iso_date(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('expected date in YYYY-MM-DD format')
    return parsed


def token(value, field):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise ValueError(f'invalid {field}')
    return value


def money_cents(value):
    if not re.fullmatch(r'[0-9]{1,7}(?:\.[0-9]{1,2})?', value):
        raise ValueError('expected a nonnegative USD amount with at most two decimal places')
    amount = Decimal(value)
    if not 0 < amount <= 1_000_000:
        raise ValueError('USD amount must be positive and at most 1000000')
    return int(amount * 100)


def parse_order(row):
    channel = row['channel'].lower()
    status = row['status'].lower()
    if channel not in CHANNELS or status not in STATUSES:
        raise ValueError('invalid order channel or status')
    return token(row['order_id'], 'order_id'), Order(iso_date(row['order_date']), channel, status)


def parse_item(row):
    if not re.fullmatch('[0-9]{1,4}', row['quantity']) or not 1 <= int(row['quantity']) <= 1000:
        raise ValueError('quantity must be an integer from 1 to 1000')
    item = Item(token(row['order_id'], 'order_id'), token(row['sku'], 'sku'),
                int(row['quantity']), money_cents(row['unit_price_usd']))
    return token(row['item_id'], 'item_id'), item


def parse_refund(row):
    refund = Refund(token(row['item_id'], 'item_id'), money_cents(row['amount_usd']))
    return token(row['refund_id'], 'refund_id'), refund


def reject(rejections, rejected, reason):
    rejections.append({
        'source_file': rejected.source_file,
        'line_number': rejected.line_number,
        'reason': reason,
        'record': json.dumps(rejected.raw, ensure_ascii=False),
    })


def read_records(input_dir, name, parser, rejections):
    path = input_dir / f'{name}.csv'
    records_by_id = defaultdict(list)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream, strict=True)
        header = tuple(next(reader, ()))
        if header != SCHEMAS[name]:
            raise ValueError(f'{path.name} must have columns {SCHEMAS[name]} in that order')
        for cells in reader:
            if not cells:
                continue
            if len(cells) != len(header):
                record = SourceRecord(path.name, reader.line_num, {'values': cells}, None)
                reject(rejections, record, 'wrong number of columns')
                continue
            raw = dict(zip(header, cells))
            try:
                record_id, value = parser({key: cell.strip() for key, cell in raw.items()})
            except ValueError as error:
                reject(rejections, SourceRecord(path.name, reader.line_num, raw, None), str(error))
                continue
            records_by_id[record_id].append(SourceRecord(path.name, reader.line_num, raw, value))

    accepted = {}
    for record_id, records in records_by_id.items():
        first = records[0]
        if any(record.value != first.value for record in records[1:]):
            for record in records:
                reject(rejections, record, f'conflicting duplicate ID {record_id}')
            continue
        accepted[record_id] = first
        for record in records[1:]:
            reject(rejections, record, f'duplicate ID {record_id}')
    return accepted


def validate_sales(input_dir, sales_date):
    rejections = []
    orders = read_records(input_dir, 'orders', parse_order, rejections)
    items = read_records(input_dir, 'order_items', parse_item, rejections)
    refunds = read_records(input_dir, 'refunds', parse_refund, rejections)

    valid_items = {}
    for item_id, record in items.items():
        if record.value.order_id not in orders:
            reject(rejections, record, 'unknown order_id')
            continue
        valid_items[item_id] = record.value

    refunds_by_item = defaultdict(list)
    for record in refunds.values():
        if record.value.item_id not in valid_items:
            reject(rejections, record, 'unknown item_id')
            continue
        refunds_by_item[record.value.item_id].append(record)

    # Reduce refunds to one amount per item before building sales lines.
    refund_totals = {}
    for item_id, records in refunds_by_item.items():
        total = sum(record.value.amount_cents for record in records)
        if total > valid_items[item_id].gross_cents:
            for record in records:
                reject(rejections, record, 'combined refunds exceed item gross')
            continue
        refund_totals[item_id] = total

    eligible_orders = {
        order_id: record for order_id, record in orders.items()
        if record.value.order_date == sales_date and record.value.status in REVENUE_STATUSES
    }
    orders_with_items = {item.order_id for item in valid_items.values()}
    for order_id in eligible_orders.keys() - orders_with_items:
        reject(rejections, eligible_orders[order_id], 'paid or completed order has no valid items')

    lines = [
        SalesLine(item.order_id, eligible_orders[item.order_id].value.channel, item.quantity,
                  item.gross_cents, refund_totals.get(item_id, 0))
        for item_id, item in valid_items.items() if item.order_id in eligible_orders
    ]
    rejections.sort(key=lambda row: (row['source_file'], row['line_number']))
    return lines, rejections


# COMMAND ----------


def aggregate_python(lines):
    totals = {}
    for channel in CHANNELS:
        selected = [line for line in lines if line.channel == channel]
        totals[channel] = {
            'order_count': len({line.order_id for line in selected}),
            'units_sold': sum(line.units_sold for line in selected),
            'gross_cents': sum(line.gross_cents for line in selected),
            'refund_cents': sum(line.refund_cents for line in selected),
        }
    return totals


def aggregate_spark(spark_session, lines):
    from pyspark.sql import functions as F

    frame = spark_session.createDataFrame(
        [(line.order_id, line.channel, line.units_sold, line.gross_cents, line.refund_cents)
         for line in lines],
        'order_id string, channel string, units_sold long, gross_cents long, refund_cents long',
    )
    grouped = frame.groupBy('channel').agg(
        F.countDistinct('order_id').alias('order_count'),
        F.sum('units_sold').alias('units_sold'),
        F.sum('gross_cents').alias('gross_cents'),
        F.sum('refund_cents').alias('refund_cents'),
    )
    return {row.channel: {field: row[field] for field in MEASURES} for row in grouped.collect()}


def sales_reports(sales_date, totals):
    daily_measures = dict.fromkeys(MEASURES, 0)
    channel_rows = []
    # Emit every channel so reruns can replace old nonzero totals with zero.
    for channel in CHANNELS:
        measures = totals.get(channel, dict.fromkeys(MEASURES, 0))
        channel_rows.append({
            'sales_date': sales_date, 'channel': channel, **measures,
            'net_cents': measures['gross_cents'] - measures['refund_cents'],
        })
        for field in MEASURES:
            daily_measures[field] += measures[field]
    daily_row = {
        'sales_date': sales_date, **daily_measures,
        'net_cents': daily_measures['gross_cents'] - daily_measures['refund_cents'],
    }
    return [daily_row], channel_rows


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def write_parquet(spark_session, path, fields, rows):
    types = {'sales_date': 'date', 'channel': 'string'}
    schema = ', '.join(f'{field} {types.get(field, "long")}' for field in fields)
    values = [tuple(row[field] for field in fields) for row in rows]
    spark_session.createDataFrame(values, schema).coalesce(1).write.mode('overwrite').parquet(str(path))


def run_batch(input_dir, output_dir, sales_date, spark_session=None):
    lines, rejections = validate_sales(input_dir, sales_date)
    totals = aggregate_python(lines) if spark_session is None else aggregate_spark(spark_session, lines)
    daily_rows, channel_rows = sales_reports(sales_date, totals)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / 'rejected_records.csv', REJECT_FIELDS, rejections)
    for name, fields, rows in (
        ('daily_sales', SALES_FIELDS, daily_rows),
        ('daily_channel_sales', CHANNEL_FIELDS, channel_rows),
    ):
        if spark_session is None:
            write_csv(output_dir / f'{name}.csv', fields, rows)
        else:
            write_parquet(spark_session, output_dir / name, fields, rows)
    return {
        'sales_date': sales_date.isoformat(),
        'orders': daily_rows[0]['order_count'],
        'sales_lines': len(lines),
        'rejected_records': len(rejections),
        'net_cents': daily_rows[0]['net_cents'],
    }


# COMMAND ----------


if 'dbutils' in globals():
    dbutils.widgets.text('volume_path', '')
    dbutils.widgets.text('run_id', '')
    dbutils.widgets.text('sales_date', '')


# COMMAND ----------


def run_databricks(dbutils_client, spark_session):
    volume = dbutils_client.widgets.get('volume_path').rstrip('/')
    if not re.fullmatch(r'/Volumes/[^/]+/[^/]+/[^/]+', volume):
        raise ValueError('volume_path must be /Volumes/<catalog>/<schema>/<volume>')
    run_id = token(dbutils_client.widgets.get('run_id'), 'run_id')
    sales_date = iso_date(dbutils_client.widgets.get('sales_date'))
    summary = run_batch(Path(volume) / 'raw' / run_id, Path(volume) / 'exports' / run_id,
                        sales_date, spark_session)
    print(json.dumps(summary))
    dbutils_client.notebook.exit(json.dumps(summary))


def run_local():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description='Build the daily e-commerce sales reports.')
    parser.add_argument('--input', type=Path, default=project / 'sample_data')
    parser.add_argument('--output', type=Path, default=project / 'output')
    parser.add_argument('--sales-date', required=True, type=iso_date)
    args = parser.parse_args()
    print(json.dumps(run_batch(args.input, args.output, args.sales_date)))


if 'dbutils' in globals() and 'spark' in globals():
    run_databricks(dbutils, spark)
elif __name__ == '__main__':
    run_local()
