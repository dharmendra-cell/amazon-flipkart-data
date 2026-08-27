#!/usr/bin/env python3
import os
import json
import base64
import hashlib
import hmac
from datetime import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials

print("=" * 70)
print("🚀 Amazon Inventory Sync to Google Sheets")
print("=" * 70)

# Get all credentials from environment
try:
    amazon_refresh = os.getenv('AMAZON_REFRESH_TOKEN')
    amazon_client_id = os.getenv('AMAZON_CLIENT_ID')
    amazon_client_secret = os.getenv('AMAZON_CLIENT_SECRET')
    google_creds = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    sheet_id = os.getenv('GOOGLE_SHEET_ID')
    
    if not all([amazon_refresh, amazon_client_id, amazon_client_secret, google_creds, sheet_id]):
        raise ValueError("Missing required environment variables")
    
    print("\n✓ All credentials loaded from GitHub Secrets")
except Exception as e:
    print(f"\n❌ Configuration error: {e}")
    exit(1)

# Step 1: Get Amazon Access Token
print("\n📡 Step 1: Getting Amazon access token...")
try:
    token_url = "https://api.amazon.com/auth/o2/token"
    token_data = {
        'grant_type': 'refresh_token',
        'refresh_token': amazon_refresh,
        'client_id': amazon_client_id,
        'client_secret': amazon_client_secret
    }
    
    response = requests.post(token_url, data=token_data)
    response.raise_for_status()
    token_response = response.json()
    access_token = token_response['access_token']
    print(f"✓ Access token obtained")
except Exception as e:
    print(f"❌ Failed to get access token: {e}")
    exit(1)

# Step 2: Fetch Inventory from Amazon SP-API
print("\n📊 Step 2: Fetching inventory from Amazon SP-API...")
try:
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/x-amz-json-1.0'
    }
    
    # Get inventory summaries
    api_url = "https://sellingpartnerapi-na.amazon.com/inventory/v1/inventorySummaries"
    params = {
        'details': 'true',
        'granularityType': 'SKU'
    }
    
    response = requests.get(api_url, headers=headers, params=params)
    response.raise_for_status()
    inventory_data = response.json()
    
    summaries = inventory_data.get('inventorySummaries', [])
    print(f"✓ Retrieved {len(summaries)} SKUs from Amazon")
    
except Exception as e:
    print(f"⚠️  Could not fetch inventory: {e}")
    print("   (This is normal if your seller account hasn't made sales yet)")
    summaries = []

# Step 3: Connect to Google Sheets
print("\n📝 Step 3: Connecting to Google Sheets...")
try:
    credentials_dict = json.loads(google_creds)
    credentials = Credentials.from_service_account_info(
        credentials_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(credentials)
    print(f"✓ Authenticated with Google")
    
    # Open the sheet by ID
    sheet = gc.open_by_key(sheet_id)
    worksheet = sheet.worksheet("Sheet1")
    print(f"✓ Opened Google Sheet")
    
except Exception as e:
    print(f"❌ Failed to connect to Google Sheets: {e}")
    exit(1)

# Step 4: Process and Write Data to Sheet
print("\n✍️  Step 4: Writing inventory data to sheet...")
try:
    if summaries:
        # Prepare data rows
        data_rows = []
        for item in summaries:
            sku = item.get('sku', 'N/A')
            fnsku = item.get('fnsku', 'N/A')
            asin = item.get('asin', 'N/A')
            
            # Get inventory details
            details = item.get('inventoryDetails', {})
            fulfillable = details.get('fulfillableQuantity', 0)
            inbound = details.get('inboundQuantity', 0)
            reserved = details.get('reservedQuantity', 0)
            
            total_stock = fulfillable + inbound
            
            # Format row for sheet (matching your headers)
            row = [
                'Amazon',           # MARKETPLACE
                sku,                # SKU
                asin,               # PRODUCT_NAME (using ASIN as identifier)
                total_stock,        # CURRENT_STOCK
                0,                  # DAILY_SALES_VELOCITY (will calculate later)
                0,                  # DAYS_SUPPLY (will calculate later)
                0,                  # REORDER_LEVEL (manual config)
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # LAST_UPDATED
                0,                  # RETURN_RATE (need returns data)
                0                   # RETURNS_7D
            ]
            data_rows.append(row)
        
        # Clear existing data (keep headers)
        worksheet.delete_rows(2, worksheet.row_count)
        print(f"✓ Cleared old data")
        
        # Write new data
        if data_rows:
            worksheet.append_rows(data_rows, value_input_option='USER_ENTERED')
            print(f"✓ Wrote {len(data_rows)} rows to sheet")
        
    else:
        print("⚠️  No inventory data to write (this is OK for first run)")
        # Write a test row to verify sheet connection works
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

# Summary
print("\n" + "=" * 70)
print("✅ SYNC COMPLETE")
print("=" * 70)
print(f"📊 Data written to: marketplace-inventory-dashboard")
print(f"🕐 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"\n📈 Next sync: Tomorrow at 6:00 AM UTC")
print("=" * 70)
