# Catsy to SparkLayer Sync Script

An enterprise-grade Python utility designed to synchronize B2B pricing data between Catsy PIM and the SparkLayer B2B engine. This tool ensures that your trade pricing remains consistent across systems with minimal API overhead.

## Workflow Architecture

The script performs the following steps:

1. State Check: Verifies the existence of a local CSV cache (`catsy_products_full_export.csv`).

2. Ingestion: * Hot Path: Loads data directly from CSV if present and valid.
    - Cold Path: Executes paginated `GET` requests to Catsy API and updates the local cache.

3. Transformation: Maps Catsy `sku` and `price_trade` fields to the SparkLayer JSON pricing schema.

4. Transmission: Authenticates via OAuth2 and pushes updates via batched `PATCH` requests to SparkLayer.

Designed for daily or automated runs – safe, repeatable, and easy to monitor.

## Prerequisites & Installation

- Python 3.7 or higher
- Install dependencies:

```bash
pip install requests python-dotenv
```
## Environment Configuration

Create a `.env` file in the root directory:
```env
# Catsy API Configuration
CATSY_BEARER_TOKEN=your_token_here

# SparkLayer API Configuration
SPARKLAYER_URL=https://api.sparklayer.io
SITE_ID=your_site_id
CLIENT_ID=your_client_id
CLIENT_SECRET=your_client_secret
```

## Operations & Monitoring
### Logging Strategy
The script implements a dual-stream logging system to keep monitoring clean while maintaining a "black box" recorder for troubleshooting.
|File | Purpose |
|------|------|
|`sync_info.log` | Clean log with INFO level and above – perfect for daily monitoring|
|`sync_debug.log` | Full detailed log including DEBUG messages – for troubleshooting|

### Console Commands:

| Mode | Command | Output Behavior |
|------|------|------|
**Standard** | `python sync.py` | Concise progress updates.
**Debug** | `python sync.py --debug` |High-verbosity output for developers.

## How to Run
### Normal daily run

```bash
python sparkLayerApi.py
```
→ Clean output and logs.

### Debug / troubleshooting run
```bash
python sparkLayerApi.py --debug
```
→ Verbose console + extra debug details in logs.

## Key Configuration (top of script)
Variable|Description|Default Value
|--------|--------|--------|
`CATSY_LIMIT`|Page size for Catsy API requests|500|
`CATSY_DELAY`|Delay (seconds) between Catsy pages|0.5|
`BATCH_SIZE`| Items per SparkLayer PATCH request|500|
`BATCH_DELAY`|Delay (seconds) between SparkLayer batches|0.5|

## Safety & Reliability Features

- CSV caching avoids unnecessary Catsy API load
- Batched uploads prevent payload-too-large errors
- Polite delays between requests
- Fresh SparkLayer token for every batch
- Clear per-batch success/failure logging
- Easy `--debug` flag for deeper insight

