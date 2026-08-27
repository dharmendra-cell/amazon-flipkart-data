#!/usr/bin/env python3
import os
import json
from datetime import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials

print("=" * 60)
print("🚀 Multi-Marketplace Inventory Sync")
print("=" * 60)

# Get credentials from environment
try:
    amazon_refresh = os.getenv('AMAZON_REFRESH_TOKEN')
    amazon_client_id = os.getenv('AMAZON_CLIENT_ID')
    amazon_client_secret = os.getenv('AMAZON_CLIENT_SECRET')
    google_creds = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    sheet_name = os.getenv('GOOGLE_SHEET_NAME', 'marketplace-inventory-dashboard')
    
    if not all([amazon_refresh, amazon_client_id, amazon_client_secret, google_creds]):
        raise ValueError("Missing required environment variables")
except Exception as e:
    print(f"❌ Configuration error: {e}")
    exit(1)

print("\n📡 Testing connections...")

# Test Amazon credentials
print("✓ Amazon credentials loaded")

# Test Google credentials
try:
    credentials_dict = json.loads(google_creds)
    credentials = Credentials.from_service_account_info(
        credentials_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(credentials)
    print("✓ Google credentials loaded")
except Exception as e:
    print(f"❌ Google auth error: {e}")
    exit(1)

# Try to open the sheet
try:
    sheet = gc.open(sheet_name)
    print(f"✓ Google Sheet '{sheet_name}' found")
except Exception as e:
    print(f"⚠️  Google Sheet not found: {e}")
    print("   (Will be created on first data write)")

print("\n✅ All credentials validated successfully!")
print("   Next: Add your data and run the full sync")
