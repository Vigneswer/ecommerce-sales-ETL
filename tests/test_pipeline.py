import csv
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'databricks'))
from ecommerce_sales import CHANNEL_FIELDS, SALES_FIELDS, SCHEMAS, run_batch


def csv_rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


class PipelineTests(unittest.TestCase):
    def test_snapshot_deduplicates_and_counts_distinct_orders(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            day = date(2025, 1, 15)
            summary = run_batch(PROJECT / 'sample_data', output, day)
            self.assertEqual(summary, {
                'sales_date': '2025-01-15', 'orders': 3, 'sales_lines': 4,
                'rejected_records': 11, 'net_cents': 14000,
            })
            daily, = csv_rows(output / 'daily_sales.csv')
            self.assertEqual(tuple(daily.values()), ('2025-01-15', '3', '7', '17500', '3500', '14000'))
            channels = {row['channel']: row for row in csv_rows(output / 'daily_channel_sales.csv')}
            self.assertEqual(channels['marketplace']['refund_cents'], '2500')
            self.assertEqual(channels['web']['order_count'], '1')
            reasons = [row['reason'] for row in csv_rows(output / 'rejected_records.csv')]
            self.assertEqual(reasons.count('conflicting duplicate ID O1009'), 2)
            self.assertIn('duplicate ID I02', reasons)
            self.assertIn('combined refunds exceed item gross', reasons)
            self.assertIn('unknown order_id', reasons)
            self.assertIn('unknown item_id', reasons)
            before = {file.name: file.read_bytes() for file in output.iterdir()}
            run_batch(PROJECT / 'sample_data', output, day)
            self.assertEqual(before, {file.name: file.read_bytes() for file in output.iterdir()})

    def test_dates_and_zero_sales_keep_fixed_upsert_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            later = run_batch(PROJECT / 'sample_data', output, date(2025, 1, 16))
            self.assertEqual((later['orders'], later['net_cents']), (1, 2000))
            market, web = csv_rows(output / 'daily_channel_sales.csv')
            self.assertEqual((market['channel'], market['net_cents']), ('marketplace', '0'))
            self.assertEqual((web['channel'], web['net_cents']), ('web', '2000'))
            no_sales = run_batch(PROJECT / 'sample_data', output, date(2025, 1, 17))
            self.assertEqual((no_sales['orders'], no_sales['net_cents']), (0, 0))
            self.assertEqual(len(csv_rows(output / 'daily_channel_sales.csv')), 2)

    def test_bad_input_header_fails_before_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'orders.csv').write_text('unexpected_header\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'orders.csv must have columns'):
                run_batch(root, root / 'output', date(2025, 1, 15))
            self.assertFalse((root / 'output').exists())

    def test_data_factory_contract_matches_notebook_exports(self):
        template = json.loads((PROJECT / 'adf' / 'azuredeploy.json').read_text(encoding='utf-8'))
        pipeline, = (resource['properties'] for resource in template['resources']
                     if resource['type'].endswith('/pipelines'))
        activities = {activity['name']: activity for activity in pipeline['activities']}
        stages = {name for name in activities if name.startswith('Stage')}
        self.assertEqual({activities[name]['inputs'][0]['parameters']['fileName'] for name in stages},
                         {f'{source}.csv' for source in SCHEMAS})
        notebook = activities['ValidateAndAggregateSales']
        self.assertEqual({dependency['activity'] for dependency in notebook['dependsOn']}, stages)
        self.assertEqual(set(notebook['typeProperties']['baseParameters']), {'volume_path', 'sales_date', 'run_id'})
        for name, table, fields, keys in (
            ('UpsertDailySales', 'daily_sales', SALES_FIELDS, ['sales_date']),
            ('UpsertChannelSales', 'daily_channel_sales', CHANNEL_FIELDS, ['sales_date', 'channel']),
        ):
            activity = activities[name]
            self.assertIn(f"/{table}'", activity['inputs'][0]['parameters']['folderPath']['value'])
            self.assertEqual(activity['outputs'][0]['parameters']['tableName'], table)
            props = activity['typeProperties']
            self.assertEqual(props['sink']['upsertSettings']['keys'], keys)
            self.assertEqual([mapping['source']['name'] for mapping in props['translator']['mappings']], list(fields))


if __name__ == '__main__':
    unittest.main()
