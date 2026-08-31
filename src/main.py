#!/usr/bin/env python3
import os
import json
from datetime import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials

print("=" * 70)
print("🚀 Amazon Inventory Sync to Google Sheets")
print("=" * 70)

# ---------------------------------------------------------------------------
# Step 0: Load credentials
# ---------------------------------------------------------------------------
try:
    amazon_refresh = os.getenv('AMAZON_REFRESH_TOKEN')
    amazon_client_id = os.getenv('AMAZON_CLIENT_ID')
    amazon_client_secret = os.getenv('AMAZON_CLIENT_SECRET')
    google_creds = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    sheet_id = os.getenv('GOOGLE_SHEET_ID')
    # Amazon.in by default — override with a repo/environment secret if selling
    # on a different marketplace.
    marketplace_id = os.getenv('AMAZON_MARKETPLACE_ID', 'A21TJRUUN4KGV')

    if not all([amazon_refresh, amazon_client_id, amazon_client_secret, google_creds, sheet_id]):
        raise ValueError("Missing required environment variables")

    print("\n✓ All credentials loaded from GitHub Secrets")
except Exception as e:
    print(f"\n❌ Configuration error: {e}")
    exit(1)

# ---------------------------------------------------------------------------
# Step 1: Get Amazon access token (LWA — no AWS SigV4 needed)
# ---------------------------------------------------------------------------
print("\n📡 Step 1: Getting Amazon access token...")
try:
    token_url = "https://api.amazon.com/auth/o2/token"
    token_data = {
        'grant_type': 'refresh_token',
        'refresh_token': amazon_refresh,
        'client_id': amazon_client_id,
        'client_secret': amazon_client_secret
    }

    response = requests.post(token_url, data=token_data, timeout=30)
    response.raise_for_status()
    token_response = response.json()
    access_token = token_response['access_token']
    print("✓ Access token obtained")
except Exception as e:
    print(f"❌ Failed to get access token: {e}")
    try:
        print(f"   Response body: {response.text[:500]}")
    except Exception:
        pass
    exit(1)

# ---------------------------------------------------------------------------
# Step 2: Fetch inventory from Amazon SP-API
# ---------------------------------------------------------------------------
print("\n📊 Step 2: Fetching inventory from Amazon SP-API...")
summaries = []
try:
    # SP-API auth uses this header — NOT "Authorization: Bearer ..."
    headers = {
        'x-amz-access-token': access_token,
        'Content-Type': 'application/json'
    }

    # Correct FBA Inventory API path (the old code pointed at a path that
    # doesn't exist on SP-API).
    api_url = "https://sellingpartnerapi-eu.amazon.com/fba/inventory/v1/summaries"
    params = {
        'details': 'true',
        'granularityType': 'Marketplace',   # only valid enum value
        'granularityId': marketplace_id,
        'marketplaceIds': marketplace_id,   # required — was missing before
    }

    response = requests.get(api_url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    inventory_data = response.json()

    # SP-API wraps results in a "payload" object — reading the top level
    # directly (as the old code did) always returns an empty list.
    summaries = inventory_data.get('payload', {}).get('inventorySummaries', [])
    print(f"✓ Retrieved {len(summaries)} SKUs from Amazon")

except Exception as e:
    print(f"⚠️  Could not fetch inventory: {e}")
    try:
        print(f"   Response status: {response.status_code}")
        print(f"   Response body: {response.text[:500]}")
    except Exception:
        pass
    print("   (This is normal if your seller account hasn't made sales yet,")
    print("    but if this keeps happening, check the response body above —")
    print("    common causes: role not approved yet, wrong marketplace ID,")
    print("    or an expired/revoked refresh token.)")
    summaries = []

# ---------------------------------------------------------------------------
# Step 3: Connect to Google Sheets
# ---------------------------------------------------------------------------
print("\n📝 Step 3: Connecting to Google Sheets...")
try:
    credentials_dict = json.loads(google_creds)
    credentials = Credentials.from_service_account_info(
        credentials_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(credentials)
    print("✓ Authenticated with Google")

    sheet = gc.open_by_key(sheet_id)
    worksheet = sheet.worksheet("Sheet1")
    print("✓ Opened Google Sheet")

except Exception as e:
    print(f"❌ Failed to connect to Google Sheets: {e}")
    exit(1)

# ---------------------------------------------------------------------------
# Step 4: Process and write data to sheet
# ---------------------------------------------------------------------------
print("\n✍️  Step 4: Writing inventory data to sheet...")
try:
    if summaries:
        data_rows = []
        for item in summaries:
            sku = item.get('sellerSku', item.get('sku', 'N/A'))
            asin = item.get('asin', 'N/A')
            product_name = item.get('productName', asin)

            details = item.get('inventoryDetails', {})
            fulfillable = details.get('fulfillableQuantity', 0)
            inbound = details.get('inboundWorkingQuantity', 0) + \
                details.get('inboundShippedQuantity', 0) + \
                details.get('inboundReceivingQuantity', 0)
            reserved = details.get('reservedQuantity', {}).get('totalReservedQuantity', 0)
            # NOTE: item.get('totalQuantity', fulfillable + inbound) looked like a
            # safe fallback but dict.get() only falls back when the key is MISSING,
            # not when it's present-but-zero. Amazon's response often includes
            # "totalQuantity": 0 even when fulfillable/inbound are non-zero, which
            # silently discarded real stock numbers. Compute directly instead.
            total_stock = fulfillable + inbound + reserved

            row = [
                'Amazon',                                          # MARKETPLACE
                sku,                                                # SKU
                product_name,                                       # PRODUCT_NAME
                total_stock,                                        # CURRENT_STOCK
                0,                                                  # DAILY_SALES_VELOCITY (TODO: calculate from Orders/Sales API)
                0,                                                  # DAYS_SUPPLY (TODO: total_stock / velocity)
                0,                                                  # REORDER_LEVEL (manual config for now)
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),       # LAST_UPDATED
                0,                                                  # RETURN_RATE (TODO: needs Returns API)
                0                                                   # RETURNS_7D (TODO: needs Returns API)
            ]
            data_rows.append(row)

        # Clear existing data rows (row 1 = headers, kept).
        # Guard against row_count <= 1 (nothing to delete yet).
        if worksheet.row_count > 1:
            worksheet.delete_rows(2, worksheet.row_count)
        print("✓ Cleared old data")

        worksheet.append_rows(data_rows, value_input_option='USER_ENTERED')
        print(f"✓ Wrote {len(data_rows)} rows to sheet")

    else:
        print("⚠️  No inventory data to write (this is OK for first run)")
        test_row = [
            'Amazon',
            'TEST-SKU-001',
            'Test Product',
            100,
            0,
            0,
            0,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            0,
            0
        ]
        worksheet.append_rows([test_row], value_input_option='USER_ENTERED')
        print("✓ Wrote test row to verify connection")

except Exception as e:
    print(f"❌ Failed to write to sheet: {e}")
    exit(1)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("✅ SYNC COMPLETE")
print("=" * 70)
print("📊 Data written to: marketplace-inventory-dashboard")
print(f"🕐 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
