# E-commerce Sales Pipeline

Turn synthetic order, order item, and refund CSVs into daily sales reports. This is an independent portfolio project based on a familiar e-commerce workflow. All sample records are fictional.

```text
Order CSVs -> Data Factory stages files in Azure Data Lake Storage
          -> Databricks validates records and aggregates sales with PySpark
          -> Data Factory loads the reports into PostgreSQL
          -> SQL reports daily revenue, channel performance, and reconciliation
```

| Tool | What it does here |
| --- | --- |
| Azure Data Factory | Runs the workflow. It stages the three input files, waits for all three copies, launches the Databricks notebook with the run ID and sales date, and loads both completed reports into PostgreSQL. |
| Azure Data Lake Storage Gen2 | Holds the input CSVs and keeps each run's raw files, rejected rows, and Parquet exports together. |
| Databricks notebook | Runs Python validation and uses PySpark to count distinct paid orders and aggregate item sales and refunds by channel. |
| PostgreSQL | Stores the reporting tables and lets you verify and query the results with SQL. |

## Run the free local demo

Open PowerShell in this project folder. Use Python 3.10 or newer. If Windows recognizes `py` instead of `python`, use `py` in these commands. The local path uses Python's standard library and writes CSV output.

```powershell
python .\databricks\ecommerce_sales.py --sales-date 2025-01-15
Get-Content .\output\daily_sales.csv
Get-Content .\output\rejected_records.csv
python -m unittest discover -s tests -v
```

For January 15, 2025, the sample has **3 orders**, **7 units**, **$175.00 gross**, **$35.00 in refunds**, **$140.00 net**, and **11 rejected records**. Marketplace contributes $85.00 net and web contributes $55.00. January 16 has 1 order and $20.00 net.

To show the actual PostgreSQL tables, start a local PostgreSQL instance, create a database, and run the following in this folder. Adjust the username and database if your local setup uses different names. `psql` is the PostgreSQL command-line client. The commands assume it is on your `PATH` or you are using its full executable path.

```powershell
createdb -h localhost -U postgres ecommerce_demo
psql -h localhost -U postgres -d ecommerce_demo -v ON_ERROR_STOP=1 -f .\sql\01_schema.sql
psql -h localhost -U postgres -d ecommerce_demo -v ON_ERROR_STOP=1 -f .\sql\02_load_local.sql
psql -h localhost -U postgres -d ecommerce_demo -v ON_ERROR_STOP=1 -f .\sql\03_analysis.sql
```

Run `02_load_local.sql` again to demonstrate that the same sale date updates existing rows. Run the Python command for January 16 and repeat the load to add a second day. The analysis file's final query should return zero rows when the channel and daily totals agree. You can also open the resulting tables and run `03_analysis.sql` in pgAdmin's Query Tool. The local load script uses `psql` because its `\copy` commands read CSVs from your laptop.

## Files to walk through in the interview

| File | Why it exists |
| --- | --- |
| `sample_data/orders.csv` | One order header per `order_id`, including its date, channel, and status. |
| `sample_data/order_items.csv` | Individual items sold, linked to an order, with quantities and unit prices. |
| `sample_data/refunds.csv` | Refund events linked to individual items. One item can have multiple refunds. |
| `databricks/ecommerce_sales.py` | An importable Databricks source notebook and a runnable local Python script. Validation is shared. The local run writes CSVs and the notebook writes typed Parquet reports. |
| `sql/01_schema.sql` | Creates `sales.daily_sales` with one row per date and `sales.daily_channel_sales` with one row per date and channel. |
| `sql/02_load_local.sql` | Loads both local CSV reports into PostgreSQL in one transaction. |
| `sql/03_analysis.sql` | Answers three questions about revenue, sales channels, and reconciliation. |
| `adf/azuredeploy.json` | Defines the data factory, its connections and datasets, and the orchestrated pipeline. |
| `tests/test_pipeline.py` | Checks the sample totals, rejects, rerun output, an invalid header, and agreement between the notebook and ADF configuration. |

## Business and data quality rules

- Count paid and completed orders with at least one valid item. Count an order once even if it has multiple lines. Pending and cancelled orders are excluded from revenue.
- Calculate `gross = quantity * unit_price` and `net = gross - refunds`. Keep money in integer US cents and convert to dollars in SQL.
- Attribute refunds to the original order date. Each run reads a complete snapshot of the three files and rebuilds one selected order date. A snapshot that adds late refunds can update the original date on rerun.
- Keep one copy of a repeated identical record. Quarantine every valid version of an ID when their values disagree. Quarantine invalid values, broken references, and all refunds for an item when their combined value exceeds that item's gross. Row-level validation records the source file, row position, reason, and original values in `rejected_records.csv`. Missing files, wrong headers, and invalid CSV syntax stop the run.
- Publish a row for the selected day and one row per supported channel, including zero sales. This lets a corrected snapshot clear old totals with an upsert. The two ADF sink activities commit separately. If one fails, rerun the batch and use the reconciliation query to confirm both reports agree.

This demo uses driver-side validation for a small snapshot. For a larger dataset I would move parsing and validation into Spark DataFrames, including joins and duplicate checks, then retain the same reporting rules.

## Interview walkthrough

1. Show that `O1001` has two item lines. Explain how the gross includes both lines while the order count increases by one.
2. Open `rejected_records.csv` and show the duplicate item and the refund that exceeds its item's gross. Explain how each rule keeps gross sales and refunds accurate.
3. Run the SQL and show $140.00 in net sales. Rerun the load and show the same row count.
4. Open the ADF definition or a provisioned ADF canvas and trace how it stages files, triggers the notebook, and loads PostgreSQL in order.

Suggested resume bullet after you have run the local demo:

> Built and tested a batch ETL pipeline for synthetic e-commerce orders and refunds using Python and PostgreSQL. Implemented data validation, rejected-record logging, and rerunnable daily sales reports, with an Azure Data Factory and Databricks configuration for cloud execution.

See [Azure and Databricks setup](AZURE_SETUP.md) for a standalone Databricks demo and the full Azure deployment path. The local demo uses no Azure resources. The Azure deployment can incur charges.
