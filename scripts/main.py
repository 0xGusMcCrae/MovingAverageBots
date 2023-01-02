import web3
import time 
import datetime
from brownie import *
import os
from dotenv import load_dotenv
import requests
import json
from scripts.populate import *

#_______________________________________________________________________________

#Global Variables

prices = [] #prices, updates every 4h to simualte 4h candles
MA4H21 = [] #keep track of the 4h 21 MA the same way you would price
cumulativePnL = 0 #total USDC gain/loss since start of current bot session
usdcStartingBalance = 0 #initial balance of current session (for tracking PnL)
usdcCurrentBalance = 0 #USDC value of wallet
wethCurrentBalance = 0
ethCurrentBalance = 0 #ETH in wallet for gas


#_______________________________________________________________________________

load_dotenv()
#VAULT_ADDRESS = os.getenv('VAULT_ADDRESS')
ROUTER_ADDRESS = os.getenv('ROUTER_ADDRESS')
#POSITION_ROUTER_ADDRESS = os.getenv('POSITION_ROUTER_ADDRESS')
#POSITION_MANAGER_ADDRESS = os.getenv('POSITION_MANAGER_ADDRESS')
#ORDERBOOK_ADDRESS = os.getenv('ORDERBOOK_ADDRESS')
#READER_ADDRESS = os.getenv('READER_ADDRESS')
#ORDERBOOK_READER_ADDRESS = os.getenv('ORDERBOOK_READER_ADDRESS')

#_______________________________________________________________________________

#token addresses
WETH = os.getenv('WETH_TOKEN_ADDRESS')
#WBTC = os.getenv('WBTC_TOKEN_ADDRESS')
#LINK = os.getenv('LINK_TOKEN_ADDRESS')
#UNI = os.getenv('UNI_TOKEN_ADDRESS')
USDC = os.getenv('USDC_TOKEN_ADDRESS')

#_______________________________________________________________________________

#MISC
PRICE_API = os.getenv('PRICE_API_URL') #Gets current price from GMX API
buyWethPath = [USDC,WETH]
sellWethPath = [WETH,USDC]

#_______________________________________________________________________________

#Contracts
#vault = Contract.from_explorer(VAULT_ADDRESS)
router = Contract.from_explorer(ROUTER_ADDRESS)
#positionRouter = Contract.from_explorer(POSITION_ROUTER_ADDRESS)
#positionManager = Contract.from_explorer(POSITION_MANAGER_ADDRESS)
#orderbook = Contract.from_explorer(ORDERBOOK_ADDRESS)
#reader = Contract.from_explorer(READER_ADDRESS)
#orderbookReader = Contract.from_explorer(ORDERBOOK_READER_ADDRESS)
usdcContract = Contract.from_explorer(USDC)
wethContract = Contract.from_explorer(WETH)

#_______________________________________________________________________________

def main(botAccount):
 
    prices = populate()
    MA4H21.append(calcMA(21,prices)) # get an initial MA location based on pre-populated prices

    bot = botAccount #feed already logged in brownie account into main to get started

    #check for approval to spend USDC and WETH by the router
    if usdcContract.allowance(bot.address, router.address) == 0:
        usdcContract.approve(router.address, 2**256-1, {'from': bot})
    if wethContract.allowance(bot.address, router.address) == 0:
        wethContract.approve(router.address, 2**256-1, {'from': bot})

    usdcCurrentBalance = getUsdcBalance(bot)
    ethCurrentBalance = getEthBalance(bot)
    wethCurrentBalance = getWethBalance(bot)

    usdcStartingBalance = usdcCurrentBalance

    waitingMessagePrinted = False #so it doesn't print a billion waiting messages, just 1 per 4h candle

    while(True):
        #time.sleep(4*60*60) #wait 4h between loops to simulate 4h candles
        time.sleep(1) 

        if(not waitingMessagePrinted):
            print("Waiting for next 4h candle close...")
            waitingMessagePrinted = True
        if (datetime.datetime.now().hour %4 == 0 and datetime.datetime.now().minute == 0 and datetime.datetime.now().second == (0 or 1 or 2)): #run a loop at each 4h candle close
            newPrice = getPrice(WETH) #get updated price from the GMX api
            prices.append(newPrice)
            newMA4H21 = calcMA(21,prices)
            MA4H21.append(newMA4H21)

            #Print out current USDC, ETH, and WETH balances with each loop
            usdcCurrentBalance = getUsdcBalance(bot)
            ethCurrentBalance = getEthBalance(bot)
            wethCurrentBalance = getWethBalance(bot)
            print(f"Current USDC Balance: {usdcCurrentBalance/(10**6)}") #USDC only has 6 decimals
            print(f"Current WETH Balance: {wethCurrentBalance/(10**18)}") #weth has the normal 18 decimals
            print(f"Current ETH Balance: {ethCurrentBalance/(10**18)}") #ETH has 18 decimals

            #Print out current price and MA location
            print(f"Current ETH price: ${newPrice}")
            print(f"Current 4h 21 SMA Location: ${newMA4H21}")

            #If there's a new cross of price above the MA, swap all USDC to WETH
            if usdcCurrentBalance > 0 and isNewMaCrossAbove(prices,MA4H21):
                buy(usdcCurrentBalance,newPrice, bot)
            #if there's a new cross of price below the MA, swap all WETH to USDC
            elif wethCurrentBalance > 0 and isNewMaCrossBelow(prices,MA4H21):
                sell(wethCurrentBalance,newPrice, bot)

            cumulativePnL = getCumulativePnL(usdcCurrentBalance,usdcStartingBalance,wethCurrentBalance,newPrice)
            print(f"Cumulative PnL: ${cumulativePnL}")
            print()

            #check to see if eth needs to be refilled

            #reset waitingMessagePrinted
            waitingMessagePrinted = False

            time.sleep(3) #don't want the loop to execute more than once cus of the (0 or 1 or 2)
#_______________________________________________________________________________

#Function to calculate the current price/location of a standard moving average
def calcMA(period,prices):
    total = 0
    i = 1 #iteration variable
    while i <= period:
        total += prices[len(prices)-i]
        i += 1
    return total/period;

#_______________________________________________________________________________

#Function to return current price from the GMX pricefeed API
def getPrice(token):
    res = requests.get(PRICE_API)
    j = json.loads(res.text)
    price = int(j[token])/(10**30) #GMX api automatically multiplies by 10^30
    return price

#_______________________________________________________________________________

def buy(amountIn, currentWethPrice, account):
    #need to change to account for decimals
    initialWethBalance = wethContract.balanceOf(account.address) #make sure this is correct - i.e. its not balanceOf()
    initialUsdcBalance = usdcContract.balanceOf(account.address)

    minAmountOut = (amountIn / currentWethPrice)*0.985 #not sure what to put for min, ideally it will never be such a rediculous slippage

    tx=router.swap(buyWethPath, amountIn, minAmountOut, account.address, {'from':account})
    tx.wait(1) #added this because it was calculating new balances before tx finished

    finalWethBalance = wethContract.balanceOf(account.address)
    finalUsdcBalance = usdcContract.balanceOf(account.address)
    print(f"Swapped {(initialUsdcBalance-finalUsdcBalance)/(10**6)} USDC for {(finalWethBalance-initialWethBalance)/(10**18)} WETH")
    print("Updated Balances: ")
    print(f"{finalUsdcBalance/(10**6)} USDC")
    print(f"{finalWethBalance/(10**18)} WETH")
    print()

#_______________________________________________________________________________

def sell(amountIn, currentWethPrice, account):
    #need to change to account for decimals
    initialWethBalance = wethContract.balanceOf(account.address) #make sure this is correct
    initialUsdcBalance = usdcContract.balanceOf(account.address)

    minAmountOut = (amountIn * currentWethPrice)*0.00 #not sure what to put for min, ideally it will never be such a rediculous slippage
    ######change the above line, only changed to 0.00 for testing purposes
    #giving insufficient amountOut, I'm wondering if the differnece between USDC and WETH
    #decimals is causing the issue
    tx=router.swap(sellWethPath, amountIn, minAmountOut, account.address, {'from': account})
    tx.wait(1)
    finalWethBalance = wethContract.balanceOf(account.address)
    finalUsdcBalance = usdcContract.balanceOf(account.address)
    print(f"Swapped {(initialWethBalance-finalWethBalance)/(10**18)} WETH for {(finalUsdcBalance-initialUsdcBalance)/(10**6)} USDC")
    print("Updated Balances: ")
    print(f"{finalUsdcBalance/(10**6)} USDC")
    print(f"{finalWethBalance/(10**18)} WETH")
    print()
#_______________________________________________________________________________

#return remaining ETH in bot's wallet (to be used for gas)
def getEthBalance(account):
    return account.balance()

#_______________________________________________________________________________

def getWethBalance(account):
    return wethContract.balanceOf(account.address) #need to correct for decimals

#_______________________________________________________________________________

def getUsdcBalance(account):
    return usdcContract.balanceOf(account.address) #need to correct for decimals

#_______________________________________________________________________________
#I think something's wrong with this sicne it's giving like 1 cent as pnl
def getCumulativePnL(usdcCurrentBalance,usdcStartingBalance,wethCurrentBalance,wethCurrentPrice):
    return (usdcCurrentBalance/(10**6) + wethCurrentBalance*wethCurrentPrice/(10**18)) - usdcStartingBalance/(10**6)

#_______________________________________________________________________________
#Spend USDC to refill ETH reserves when low so bot doesn't run out of gas
def refillEth(account, currentWethPrice):
    amountIn = 50*10**usdcContract.decimals(); #might change this number but keep ~$50 of gas in reserve
    minAmountOut = (amountIn * currentWethPrice)*0.985
    router.swapTokensToETH(buyWethPath, amountIn, minAmountOut, account.address)

#_______________________________________________________________________________
#determine if the price has crossed above the MA (buy signal)
def isNewMaCrossAbove(prices,MAs):
    prevPrice = prices[-2]
    prevMA = MAs[-2]
    currentPrice = prices[-1]
    currentMA = MAs[-1]
    if prevPrice <= prevMA and currentPrice > currentMA:
        return True
    else:
        return False

#_______________________________________________________________________________
#determine if price has crossed below the MA (sell signal)
def isNewMaCrossBelow(prices,MAs):
    prevPrice = prices[-2]
    prevMA = MAs[-2]
    currentPrice = prices[-1]
    currentMA = MAs[-1]
    if prevPrice >= prevMA and currentPrice < currentMA:
        return True
    else:
        return False

#_______________________________________________________________________________
