# Run the notebook and Azure pipeline

## Show the notebook in Databricks Free Edition

Use this path to demonstrate the Databricks transform separately from the full Azure integration. Free Edition uses a serverless workspace with usage limits.

1. In Databricks Free Edition, create a managed Unity Catalog volume in a catalog and schema you can write to, such as `workspace.default.sales_demo`.
2. In the volume, create `raw/demo` and upload `orders.csv`, `order_items.csv`, and `refunds.csv` from `sample_data/` into that directory. Use the Databricks file upload UI.
3. In **Workspace**, import `databricks/ecommerce_sales.py` as a Python source notebook. Run the first three cells to define the functions and create the widgets. Fill the three widgets as shown below, then run the fourth cell.

   | Widget | Example value |
   | --- | --- |
   | `volume_path` | `/Volumes/workspace/default/sales_demo` |
   | `run_id` | `demo` |
   | `sales_date` | `2025-01-15` |

4. Check the final JSON for `orders` of 3, `rejected_records` of 11, and `net_cents` of 14000. The reports are under `exports/demo/` in the volume. To inspect a report, run the following from a second notebook, using your volume path.

   ```python
   reports = '/Volumes/workspace/default/sales_demo/exports/demo'
   display(spark.read.parquet(f'{reports}/daily_channel_sales'))
   ```

The ADF integration below targets an Azure Databricks workspace with an existing compute cluster. Use the local PostgreSQL steps in the README to show SQL and persistence separately during a zero-cloud-cost interview demo.

## Deploy the full pipeline in Azure

This path requires an Azure subscription and services you can provision or are authorized to use. Data Factory orchestration, Data Lake Storage, managed PostgreSQL, and Databricks compute can incur charges. The template creates the Data Factory and its pipeline definitions. The following steps prepare and connect the underlying services.

1. **Create or select an ADLS Gen2 account.** Enable hierarchical namespace. Create a private container such as `sales-demo`, then upload the sample CSVs under `incoming/` and create `pipeline/` for the Unity Catalog volume's backing path.
2. **Prepare Azure Databricks.** Use a Unity Catalog-enabled workspace and a Unity Catalog-compatible interactive cluster with Databricks Runtime 13.3 LTS or newer. In **Workspace**, import `databricks/ecommerce_sales.py` as a source notebook. Copy the absolute notebook workspace path, without the `.py` extension, and the existing cluster ID. Generate a short-lived Databricks personal access token for an identity that can run the notebook, attach to the cluster, and read and write the volume.
3. **Point an external volume at the same storage.** Configure an Azure Databricks Access Connector and Unity Catalog storage credential with access to your ADLS account. Create an external location that covers the demo directory and create an external volume backed by `abfss://sales-demo@<storage-account>.dfs.core.windows.net/pipeline/`. Grant the notebook identity `USE CATALOG`, `USE SCHEMA`, `READ VOLUME`, and `WRITE VOLUME` as needed. Record the `/Volumes/<catalog>/<schema>/<volume>` path. ADF writes to the cloud URI and Databricks uses the volume path to reach the same files.
4. **Prepare Azure Database for PostgreSQL Flexible Server.** Create the target database and run `sql/01_schema.sql` using an account that can create a schema and tables. Use a database login with schema access and permissions to select, insert, and update both tables. Ensure the integration runtime can reach the server and the storage account. The supplied linked services use the default Azure Integration Runtime. A private-network setup can require a different runtime or private endpoint configuration.
5. **Deploy `adf/azuredeploy.json`.** In Azure Portal, open **Deploy a custom template**, choose **Build your own template in the editor**, load the JSON, and fill in the deployment parameters. Enter the PostgreSQL password and Databricks token as secure deployment parameters. Keep credentials out of the project folder and source control. Use a dedicated demo factory name.

   | Parameter | Value |
   | --- | --- |
   | `factoryName` | Globally unique name for this data factory |
   | `factoryLocation` | Azure region for the data factory |
   | `storageAccountName`, `fileSystem` | ADLS account name and private container name |
   | `databricksWorkspaceUrl`, `databricksClusterId` | Workspace HTTPS base URL and existing compute ID |
   | `databricksToken` | Short-lived Databricks access token |
   | `notebookPath`, `databricksVolumePath` | Imported notebook path and external `/Volumes` path |
   | `postgresServer`, `postgresDatabase`, `postgresUsername`, `postgresPassword` | PostgreSQL Flexible Server hostname, database, username, and password |

6. **Authorize the data factory.** On the demo container, assign **Storage Blob Data Contributor** to the factory's system-assigned managed identity. In ADF Studio, test the Data Lake, Databricks, and PostgreSQL linked services.
7. **Run and verify.** Open `EcommerceSalesDaily` in ADF Studio and trigger it with `salesDate=2025-01-15`. In **Monitor**, verify the three Stage activities, `ValidateAndAggregateSales`, `UpsertChannelSales`, and `UpsertDailySales` all succeeded. Inspect `pipeline/exports/<run-id>/rejected_records.csv` and run `sql/03_analysis.sql` against PostgreSQL. Trigger the same date again and verify one daily row and two channel rows.

For a complete interview demo, show the Databricks notebook output, the ADF run status if you have deployed it, and the PostgreSQL query results. Stop any demo compute and remove disposable Azure resources when you finish with them.
