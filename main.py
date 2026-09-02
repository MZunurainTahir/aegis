import os
from dotenv import load_dotenv, find_dotenv

from alpaca.trading.client import TradingClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest

# Force find and load the .env file
load_dotenv(find_dotenv())

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# Debugging print to verify keys are loaded
if not API_KEY or not SECRET_KEY:
    raise ValueError("API Keys failed to load from .env file! Check your file path and key names.")

print(f"Loaded API Key: {API_KEY[:5]}...")

# 1. Initialize Trading Client
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

account = trading_client.get_account()
print(f"Connected to Account ID: {account.id}")
print(f"Account Status: {account.status}")
print(f"Buying Power: ${account.buying_power}")

# 2. Initialize Option Historical Data Client
option_data_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)

# Fetch option chain contracts for AAPL
request_params = OptionChainRequest(underlying_symbol="AAPL")
option_chain = option_data_client.get_option_chain(request_params)

print(f"Retrieved {len(option_chain)} option contracts for AAPL.")