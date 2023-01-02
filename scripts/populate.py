#script for populating price history from gemini api
import requests
import json
import os
from dotenv import load_dotenv

def populate():
    GEMINI_API = os.getenv('GEMINI_API_URL')
    res = requests.get(GEMINI_API)
    j = json.loads(res.text)
    prices = []
    i = 0
    while i < len(j)/4:
        #use i*4 to simulate 4h candles (api returns 1h)
        prices.insert(0,j[i*4][4]) #the 4th item in each subarray is the candle close price
        i += 1

    return prices

