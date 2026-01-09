import os
import csv
import time
import requests
import logging
import argparse
from datetime import datetime  # ← Added for weekly logic
from dotenv import load_dotenv

load_dotenv()

# ==================== ARGUMENT PARSER FOR DEBUG MODE ====================
parser = argparse.ArgumentParser(description="Catsy to SparkLayer Sync")
parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
args = parser.parse_args()

# ==================== LOGGING SETUP ====================
LOG_FORMAT = "%(asctime)s [%(name)s] [%(levelname)s] %(message)s"
DEBUG_LOG_FILE = "sync_debug.log"
INFO_LOG_FILE = "sync_info.log"

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

if not root_logger.handlers:
    info_handler = logging.FileHandler(INFO_LOG_FILE, encoding="utf-8")
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(info_handler)

    debug_handler = logging.FileHandler(DEBUG_LOG_FILE, encoding="utf-8")
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(debug_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if args.debug else logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(console_handler)

main_logger = logging.getLogger("MAIN")
catsy_logger = logging.getLogger("CATSY")
sparklayer_logger = logging.getLogger("SPARKLAYER")

if args.debug:
    main_logger.debug("Debug mode enabled - verbose output active")

# ==================== CONFIG ====================
CATSY_BASE_URL = "https://api.catsy.com/api/v3/queries/4919552a-c2c9-48af-ae88-a5159c8af053/items"
CATSY_BEARER_TOKEN = os.getenv("CATSY_BEARER_TOKEN")
if not CATSY_BEARER_TOKEN:
    raise ValueError("Please set CATSY_BEARER_TOKEN in your .env file")

CATSY_HEADERS = {
    "Authorization": f"Bearer {CATSY_BEARER_TOKEN}",
    "Accept": "application/json"
}

CATSY_LIMIT = 500
CATSY_DELAY = 0.5
OUTPUT_FILE = "catsy_products_full_export.csv"  # Weekly cached file

SPARK_BASE_URL = os.getenv('SPARKLAYER_URL')
SITE_ID = os.getenv('SITE_ID')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

BATCH_SIZE = 500
BATCH_DELAY = 0.5

# Folder and filename for debug export
EXPORT_FOLDER = "exports"
os.makedirs(EXPORT_FOLDER, exist_ok=True)  # Create folder if it doesn't exist

# ==================== CATSY EXPORT ====================
def fetch_catsy_products():
    all_products = []
    offset = 0
    total = None

    catsy_logger.info("Starting full Catsy export...\n")
    if args.debug:
        catsy_logger.debug(f"Using URL: {CATSY_BASE_URL}")

    while True:
        params = {"limit": CATSY_LIMIT, "offset": offset}
        catsy_logger.info(f"Fetching offset {offset}...")
        try:
            response = requests.get(CATSY_BASE_URL, headers=CATSY_HEADERS, params=params, timeout=90)
            if args.debug:
                catsy_logger.debug(f"Response status: {response.status_code}")
        except Exception as e:
            catsy_logger.error(f"Request failed: {e}")
            break

        if response.status_code != 200:
            catsy_logger.error(f"Error {response.status_code}: {response.text[:500]}")
            break

        data = response.json()

        if offset == 0:
            total = data.get("total") or data.get("totalCount") or data.get("pagination", {}).get("total_results")
            if total:
                catsy_logger.info(f"Total products: {total}")

        items = data.get("items", [])
        if not items:
            catsy_logger.info("No items found. Stopping export.")
            break

        all_products.extend(items)
        catsy_logger.info(f"✓ Fetched {len(items)} products | Total: {len(all_products)}")

        if len(items) < CATSY_LIMIT or (total and offset + CATSY_LIMIT >= total):
            catsy_logger.info("Reached last page.")
            break

        offset += CATSY_LIMIT
        time.sleep(CATSY_DELAY)

    return all_products

def save_debug_csv(products, timestamp_str):
    if not products:
        main_logger.info("No products to save to debug CSV.")
        return

    # Get all unique keys
    all_keys = set()
    for p in products:
        all_keys.update(p.keys())

    # Prioritize important columns
    priority_keys = ["sku", "price_trade"]
    fieldnames = [k for k in priority_keys if k in all_keys] + sorted([k for k in all_keys if k not in priority_keys])

    filename = f"catsy_export_{timestamp_str}.csv"
    filepath = os.path.join(EXPORT_FOLDER, filename)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)

    main_logger.info(f"🗄️  Debug export saved: {filepath} ({len(products)} products)")

# ==================== SPARKLAYER AUTH & PATCH (unchanged) ====================
def get_sparklayer_token():
    token_url = f"{SPARK_BASE_URL}/api/auth/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json", "Site-Id": SITE_ID}

    sparklayer_logger.info("Requesting new access token from SparkLayer...")
    if args.debug:
        sparklayer_logger.debug(f"Token URL: {token_url}")

    response = requests.post(token_url, json=payload, headers=headers)
    response.raise_for_status()
    sparklayer_logger.info("Access token obtained successfully.")
    return response.json()["access_token"]

def patch_to_sparklayer(data, resource="price-lists/wholesale/pricing"):
    token = get_sparklayer_token()
    url = f"{SPARK_BASE_URL}/api/v1/{resource}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Site-Id": SITE_ID
    }

    payload = data

    try:
        response = requests.patch(url, json=payload, headers=headers, timeout=180)
        if response.status_code in (200, 201, 204):
            sparklayer_logger.info(f"✅ Patch successful ({len(data)} items)")
            return response.json() if response.content else None
        else:
            try:
                error_json = response.json()
                sparklayer_logger.error(f"❌ Patch error {response.status_code}: {error_json}")
            except Exception:
                sparklayer_logger.error(f"❌ Patch error {response.status_code}: {response.text[:500]}")
            return None
    except requests.exceptions.RequestException as e:
        sparklayer_logger.error(f"❌ PATCH request failed: {e}")
        return None

def batch(iterable, n=500):
    for i in range(0, len(iterable), n):
        yield iterable[i:i + n]

# ==================== MAIN ====================
if __name__ == "__main__":
    required_env = ["CATSY_BEARER_TOKEN", "SPARKLAYER_URL", "SITE_ID", "CLIENT_ID", "CLIENT_SECRET"]
    missing = [var for var in required_env if not os.getenv(var)]
    if missing:
        main_logger.critical(f"Missing required environment variables: {missing}")
        exit(1)

    try:
        main_logger.info("=== Starting Catsy → SparkLayer Sync ===")

        # Generate timestamp for filename
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # Always fetch fresh data from Catsy (no caching)
        main_logger.info("Fetching fresh product data from Catsy...")
        catsy_products = fetch_catsy_products()

        if not catsy_products:
            main_logger.warning("No products received from Catsy. Nothing to sync.")
            exit(0)

        save_debug_csv(catsy_products,timestamp_str)

        # Prepare and upload pricing
        sparklayer_items = []
        for p in catsy_products:
            sku = p.get("sku")
            price = p.get("price_trade")
            if sku and price is not None:
                try:
                    price_float = float(price)
                    sparklayer_items.append({
                        "sku": sku,
                        "pricing": [{"quantity": 1, "price": price_float, "unit_of_measure": None}]
                    })
                except (ValueError, TypeError):
                    catsy_logger.warning(f"Invalid price_trade value for SKU {sku}: {price}")

        main_logger.info(f"Prepared {len(sparklayer_items)} items for upload to SparkLayer.")

        if sparklayer_items:
            total_batches = (len(sparklayer_items) + BATCH_SIZE - 1) // BATCH_SIZE
            main_logger.info(f"Uploading in {total_batches} batch(es)...")
            for i, chunk in enumerate(batch(sparklayer_items, BATCH_SIZE), start=1):
                sparklayer_logger.info(f"Uploading batch {i} ({len(chunk)} items)...")
                if args.debug:
                    first_sku = chunk[0]['sku'] if chunk else 'N/A'
                    sparklayer_logger.debug(f"Batch {i} contains {len(chunk)} items, first SKU: {first_sku}")
                patch_to_sparklayer(chunk)
                time.sleep(BATCH_DELAY)
            main_logger.info("\n🎉 All batches uploaded successfully!")
        else:
            main_logger.info("No valid products to upload to SparkLayer.")

        main_logger.info("=== Sync completed successfully ===\n")
        exit(0)
    except Exception as e:
        main_logger.critical(f"Sync failed with unexpected error: {e}", exc_info=True)
        exit(1)