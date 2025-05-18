import os
import time
import numpy as np
import pandas as pd
import requests
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv
import datetime

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

client = Client(API_KEY, API_SECRET)
client.API_URL = 'https://testnet.binance.vision/api'

symbol = 'BTCUSDT'
interval = Client.KLINE_INTERVAL_1HOUR

def notify_discord(message):
    if DISCORD_WEBHOOK:
        data = {"content": message}
        try:
            requests.post(DISCORD_WEBHOOK, json=data)
        except Exception as e:
            print("Erreur envoi Discord:", e)

def get_klines():
    klines = client.get_klines(symbol=symbol, interval=interval, limit=500)
    df = pd.DataFrame(klines, columns=['Open time','Open','High','Low','Close','Volume',
                                       'Close time','Quote asset volume','Number of trades',
                                       'Taker buy base asset volume','Taker buy quote asset volume','Ignore'])
    df['Close'] = df['Close'].astype(float)
    df['High'] = df['High'].astype(float)
    df['Low'] = df['Low'].astype(float)
    return df[['Close', 'High', 'Low']]

def calculate_indicators(df):
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def place_order(side, quantity, price):
    try:
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notify_discord(f"✅ {side} {quantity} BTC @ {price:.2f} USD ({now})")
        print(f"Order placed: {side} {quantity} BTC @ {price}")
    except Exception as e:
        notify_discord(f"❌ Error placing order: {e}")
        print("Error placing order:", e)

in_position = False
entry_price = 0
btc_quantity = 0

while True:
    try:
        df = get_klines()
        df = calculate_indicators(df)

        current = df.iloc[-1]
        price = current['Close']

        if not in_position:
            if current['MA50'] > current['MA200'] and current['RSI'] < 50:
                usdt_balance = float(client.get_asset_balance(asset='USDT')['free'])
                btc_quantity = round(usdt_balance / price, 6)
                place_order(SIDE_BUY, btc_quantity, price)
                entry_price = price
                sl = entry_price * 0.95
                tp = entry_price * 1.15
                in_position = True
        else:
            if price >= entry_price * 1.10:
                sl = max(sl, price * 0.98)
            else:
                sl = max(sl, price * 0.95)

            if price >= tp or price <= sl:
                place_order(SIDE_SELL, btc_quantity, price)
                in_position = False
                entry_price = 0
                btc_quantity = 0

        print(f"{datetime.datetime.now()} | Price: {price:.2f} | In Position: {in_position}")
        time.sleep(60)

    except Exception as e:
        notify_discord(f"⚠️ Bot error: {e}")
        print("Erreur dans la boucle principale:", e)
        time.sleep(60)
