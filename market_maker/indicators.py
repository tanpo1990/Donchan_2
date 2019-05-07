import requests
import math
import numpy as np
import pandas as pd
import time
import datetime
import logging 
import json
import sys
from market_maker.utils import log

#### Class ####
class motion_by_connect_bitmex():
    
    def __init__(self):

        self.minute = 1 #分足
        self.term = 21  #何本
        self.Atr_Length = 20
        self.Sma_Length = 20

    def run(self):
        # Run
        self.now = round(int(datetime.datetime.now().timestamp()))
        self.ohlc =self._read_ohlc(self.now,self.minute,self.term)
        self.ans = self._calculate_value(self.ohlc,self.Atr_Length,self.Sma_Length)
        return self.ans

    def run_test(self):
        # Run
        self.now = round(int(datetime.datetime.now().timestamp()))
        self.ohlc =self._read_ohlc(self.now,self.minute,self.term)
        self.ans = self._calculate_value(self.ohlc,self.Atr_Length,self.Sma_Length)
        self.ohlc.update(self.ans)
        return self.ohlc

    def _read_ohlc(self,time,minute,term):
        self.time = time
        self.minute = minute
        self.term = term
        if self.minute == 1:
            # 1minutes
            r = requests.get('https://www.bitmex.com/api/udf/history?symbol=XBTUSD&resolution=1&from=' + str(self.time-(60*self.term)) + '&to=' + str(self.time)) 
        elif self.minute == 5:
            # 1minutes
            r = requests.get('https://www.bitmex.com/api/udf/history?symbol=XBTUSD&resolution=1&from=' + str(self.time-(300*self.term)) + '&to=' + str(self.time)) 
        # exit を記載する    
        
        if r.json():
            ohlc = r.json()                # JSONデータをリストに変換
        else:
            while not r.json():
                print("---json check!")
                time.sleep(1)
        return ohlc

    def _calculate_value(self,ohlc,Atr_Length,Sma_Length):
        self.ohlc = ohlc
        self.Atr_Length = Atr_Length
        self.Sma_Length = Sma_Length
        high_array = np.array(ohlc['h'])[::-1]
        low_array = np.array(ohlc['l'])[::-1]
        close_array = np.array(ohlc['c'])[::-1] 
        open_array = np.array(ohlc['o'])[::-1] #tradingviewは最新が0、bitmexapiは最新が最後のため[::-1]でreverseする
        sma = self.return_sma(self.Sma_Length,close_array)
        # import pdb; pdb.set_trace()
        atr = self.return_atr(self.Atr_Length,high_array,low_array,close_array)
        # hl_line = self.calc_hl_line(atr,sma,close_array) 
        hl_line = (max(close_array[0:self.Sma_Length-1]),min(close_array[0:self.Sma_Length-1]))
        # return  hl_line
        return atr,sma,hl_line[0],hl_line[1]
        
    def return_atr(self,length,high_array,low_array,close_array):
        close = close_array[2:]
        high = high_array[1:]
        low = low_array[1:]
        result = 0
        
        for i in range(1,length):
            tr = max(abs(high[i]- low[i]),abs(high[i]-close[i]),abs(close[i]-low[i]))
            result += tr
        result = round(result/length,3)
        return result

    def return_sma(self,length,close_array):
        if length == 1:
            ans = close_array[1]
        else:
            ans = pd.Series(close_array).rolling(length).mean()
        return ans[length]
    
    def calc_hl_line(self,atr,sma,close_array):
        close = close_array[1]

        #print(str(close),str(atr),str(sma))
        #UPRATIO = 0.6 # 5minute
        #DOWNRATIO = 0.4 # 5minute
        UPRATIO = 1.2 # 1,3minute
        DOWNRATIO = 0.8 # 1,3minute
        #### 未検証 ####
        high_line = max(sma)
        low_line = min(sma)
        # high_line = close + (atr * UPRATIO)
        # low_line = close - (atr * DOWNRATIO)

        return high_line,low_line


        
def run():
    logger = log.setup_custom_logger('root')
    logger.info('calc_indicators')
    mb = motion_by_connect_bitmex()

    try:
        mb.run()
    except (KeyboardInterrupt, SystemExit):
        sys.exit()
        

