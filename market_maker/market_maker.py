# midoridon2 2019.0501

from __future__ import absolute_import
from time import sleep
import sys
from datetime import datetime
from os.path import getmtime
import random
import requests
import atexit
import signal
from market_maker import bitmex
from market_maker import indicators
from market_maker.settings import settings
from market_maker.utils import log, constants, errors, math

# Used for reloading the bot - saves modified times of key files
import os
watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]
# [('market_maker/market_maker.py', 1545733833.8266635), ('market_maker/bitmex.py', 1544452384.0555239), ('settings.py', 1545722182.2053728)]

#
# Helpers
#
logger = log.setup_custom_logger('root')
logger_market = log.setup_custom_logger('market_info')
logger_order = log.setup_custom_logger('order_info')
logger_wallet = log.setup_custom_logger('wallet_info')

# challenging

# 1. rerun 2. print 3. cancel_all_orders 4. japan time 5. analysting
class ExchangeInterface:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run

        if len(sys.argv) > 1: # "2" ['marketmaker', 'XBTUSD']
            self.symbol = sys.argv[1]
        else:
            self.symbol = settings.SYMBOL
        self.line_notify_token= settings.line_notify_token
        self.bitmex = bitmex.BitMEX(base_url=settings.BASE_URL, symbol=self.symbol,
                                    apiKey=settings.API_KEY, apiSecret=settings.API_SECRET,
                                    orderIDPrefix=settings.ORDERID_PREFIX, postOnly=settings.POST_ONLY,
                                    timeout=settings.TIMEOUT)

    def cancel_order(self,name,order,hl_lines,ticker):
        order_info = {}
        # import pdb; pdb.set_trace()
        order_info.update(order=order['side'],orderQty=order['orderQty'],price=order['price'],last=ticker['last'],l_lines = hl_lines[1],h_lines = hl_lines[0])
        logger.info("%s- OrderReport - %s" % (name,order_info))
        logger_order.info("%s- OrderReport - %s" % (name,order_info))

        while True:
            try:
                self.bitmex.cancel(order['orderID'])
                sleep(settings.API_REST_INTERVAL)
            except ValueError as e:
                logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

    def cancel_all_orders(self,name,hl_lines=None,ticker=None):
        order_info = {}
        if self.dry_run:
            return

        logger.info("Resetting current position. Canceling all existing orders.")

        # In certain cases, a WS update might not make it through before we call this.
        # For that reason, we grab via HTTP to ensure we grab them all.
        # import pdb; pdb.set_trace()
        orders = self.bitmex.http_open_orders() # _curl_bitmex()
        if hl_lines == None:
            for order in orders:
                order_info.update(order=order['side'],orderQty=order['orderQty'],price=order['price'])
                logger.info("%s- OrderReport - %s" % (sys._getframe().f_code.co_name,order_info))
                logger_order.info("%s- OrderReport - %s" % (sys._getframe().f_code.co_name,order_info))
        else:
            for order in orders:
                order_info.update(order=order['side'],orderQty=order['orderQty'],price=order['price'],last=ticker['last'],l_lines = hl_lines[1],h_lines = hl_lines[0])
                logger.info("%s- OrderReport - %s" % (name,order_info))
                logger_order.info("%s- OrderReport - %s" % (name,order_info))


        if len(orders):
            self.bitmex.cancel([order['orderID'] for order in orders])

        sleep(settings.API_REST_INTERVAL)


    def get_portfolio(self):
        contracts = settings.CONTRACTS
        portfolio = {}
        for symbol in contracts:
            position = self.bitmex.position(symbol=symbol)
            instrument = self.bitmex.instrument(symbol=symbol)

            if instrument['isQuanto']:
                future_type = "Quanto"
            elif instrument['isInverse']:
                future_type = "Inverse"
            elif not instrument['isQuanto'] and not instrument['isInverse']:
                future_type = "Linear"
            else:
                raise NotImplementedError("Unknown future type; not quanto or inverse: %s" % instrument['symbol'])

            if instrument['underlyingToSettleMultiplier'] is None:
                multiplier = float(instrument['multiplier']) / float(instrument['quoteToSettleMultiplier'])
            else:
                multiplier = float(instrument['multiplier']) / float(instrument['underlyingToSettleMultiplier'])

            portfolio[symbol] = {
                "currentQty": float(position['currentQty']),
                "futureType": future_type,
                "multiplier": multiplier,
                "markPrice": float(instrument['markPrice']),
                "spot": float(instrument['indicativeSettlePrice'])
            }
        return portfolio
        # {'XBTUSD': {'currentQty': 0.0, 'futureType': 'Inverse', 'multiplier': 1.0, 'markPrice': 3761.33, 'spot': 3761.47}}

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.instrument(symbol)

    def get_margin(self):
        if self.dry_run:
            return {'marginBalance': float(settings.DRY_BTC), 'availableFunds': float(settings.DRY_BTC)}
        return self.bitmex.funds()
        
    def get_delta(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.get_position(symbol)['currentQty']


    def get_orders(self):
        if self.dry_run:
            return []
        return self.bitmex.open_orders()

    def get_position(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.position(symbol)

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.ticker_data(symbol)

    def is_open(self):
        """Check that websockets are still open."""
        return not self.bitmex.ws.exited

    def create_bulk_orders(self, orders):
        if self.dry_run:
            return orders
        return self.bitmex.create_bulk_orders(orders)
        
    def cancel_bulk_orders(self, orders):
        if self.dry_run:
            return orders
        return self.bitmex.cancel([order['orderID'] for order in orders])
        
    def lineNotify(self,message):
        line_notify_token = self.line_notify_token
        line_notify_api = 'https://notify-api.line.me/api/notify'
        payload = {'message': message}
        headers = {'Authorization': 'Bearer ' + line_notify_token} 
        requests.post(line_notify_api, data=payload, headers=headers)



class OrderManager:
    def __init__(self):
        # make class
        self.exchange = ExchangeInterface(settings.DRY_RUN)
        self.indicators = indicators.motion_by_connect_bitmex()

        # log
        logger.info("Using symbol %s." % self.exchange.symbol)
        if settings.DRY_RUN:
            logger.info("Initializing dry run. Orders printed below represent what would be posted to BitMEX.")
        else:
            logger.info("Order Manager initializing, connecting to BitMEX. Live run: executing real trades.")

        # get constant
        #self.Short_Interval = settings.LOOP_INTERVAL_01ds
        #self.Short_Interval = settings.LOOP_INTERVAL_0001
        self.Short_Interval = settings.LOOP_INTERVAL_0000000001
        #self.Short_Interval = settings.LOOP_INTERVAL_0000001
        self.Sleep_Interval = settings.LOOP_INTERVAL_1s
        self.Long_Interval = settings.LOOP_INTERVAL_10s
        self.Value_Term = settings.Value_Term
        self.Market_Term = settings.Market_Term
        self.RETRY_RANGE = settings.RETRY_RANGE
        self.MARKET_ORDER_RANGE = settings.MARKET_ORDER_RANGE
        self.Reference_Time_Value = settings.REFERENCE_TIME_VALUE
        self.Sanity_Check_Term = settings.Sanity_Check_Term
        self.Order_Count_Check = settings.Order_Count_Check
        self.lot = settings.LOT
        self.chacker = 'init'
        self.H_L_Range = settings.H_L_Range

        # on error
        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)
        
        # init proc
        self.order_count = 0
        # all order cancel
        # self.exchange.cancel_all_orders(sys._getframe().f_code.co_name)
        self.orderIDs = []

    def get_info_bitmex(self):
        ticker = self.exchange.get_ticker()
        tickLog = self.exchange.get_instrument()['tickLog']
        pos = self.exchange.get_position()['currentQty']
        ticker.update({'tickLog': tickLog, 'pos': pos})
        return ticker 
    
    def get_info_crypto_watch(self):
        info_indicators = self.indicators.run()
        return info_indicators
        
    def cross_over(self,x,y): # x=[a,b] y=[c]
        if x[0] < y and x[1] > y :
            return True
 
    def cross_under(self,x,y): # x=[a,b] y=[c]
        if x[0] > y and x[1] < y :
            return True

    def make_my_fifo(self,que,imp): # que:[]
        if not que:
            que = [imp,imp]
        else:
            #que[1] = que[0]
            #que[0] = imp
            que=[imp,que[0]]
        return que

    def count_my_order(self,orders): # que:[]
        ans=len(orders)
        #ans = 0
        #if not orders:
        #    ans = 0
        #else:
        #    for order in orders:
        #        ans += 1
        return ans
        
        
    def check_connection(self):
        """Ensure the WS connections are still open."""
        return self.exchange.is_open()

    def exit(self):
        logger.info("Shutting down. All open orders will be cancelled.")
        try:
            # self.exchange.cancel_all_orders(sys._getframe().f_code.co_name)
            self.exchange.bitmex.exit()
        except errors.AuthenticationError as e:
            logger.info("Was not authenticated; could not cancel orders.")
        except Exception as e:
            logger.info("Unable to cancel orders: %s" % e)

        sys.exit()
        
    def market_report(self,name,ticker,last,prm):
        
        ticker = self.get_info_bitmex()        
        prm = self.get_info_crypto_watch()
		# prm(0):atr,prm(1):sma,prm(2):high_line,prm(3):low_line 

        market_report = ticker
        market_report.update({"h_lines":prm[2],"l_lines":prm[3],"last_bef":last[0]\
        ,"last_aft":last[1],"atr":prm[0],"sma":prm[1]})
        logger_market.info("%s - MarketReport -%s" % (name,market_report))

    def wallet_report(self,name):
        wallet_info = {}
        margin = self.exchange.get_margin()
        self.running_qty = self.exchange.get_delta()
        self.start_XBt = margin["marginBalance"]
        wallet_info=XBt_to_XBT(self.start_XBt)
        logger_wallet.info("%s - WalletReport -%.6f" % (name,wallet_info))
        # self.exchange.lineNotify("%s - WalletReport -%.6f" % (name,wallet_info))
        
        while True:
            try:
                # import pdb; pdb.set_trace()
                self.exchange.lineNotify("%s - WalletReport -%.6f" % (name,wallet_info))
                sleep(1)
            except:
                logger.info("HTTPError raised. Retrying in 1 seconds...")
                sleep(1)
                continue
            break


    def run_loop(self):
        
        ticker = self.get_info_bitmex()        
        prm = self.get_info_crypto_watch()
		# prm(0):atr,prm(1):sma,prm(2):high_line,prm(3):low_line 
        existing_orders = self.exchange.get_orders()
        order_count = self.count_my_order(existing_orders)

        # lot
        mm_lot = 20
        mm_max_lot = 100
        init_don_lot = 300
        don_lot = 300
        don_max_lot = 500
        don_pira_lot = 50

        # make_switch 
        last_switch=[]
        status_switch=[]

        # make_channel
        piramidding_channel=0
        ## still undefine high_channel,low_channel

        # make_order
        execute_order = []
        prepare_order = {}
        set_order = {}
        cancel_execute_order = []
        set_cancel_order={}

        ## mode = settings.mode
        prepare_order.update(mode='init',execute='no')
        set_order.update(price=0,orderQty=0,side='init')        

        #count_count=0

        # set switch
        last_switch = self.make_my_fifo(last_switch,ticker['last'])            
        status_switch = self.make_my_fifo(status_switch,prepare_order['mode'])            

        #while True:
        for _ in range(1, 1000000000):
            # per short term
            # get price
            ticker = self.get_info_bitmex()
            existing_orders = self.exchange.get_orders()
            order_count = self.count_my_order(existing_orders)

            # count_count+=1
            
            # per short term
            ## switch mode(donchan) 
            ### entry
            if self.cross_over(last_switch,prm[2]): 
                prepare_order['mode'] = 'donb'
                piramidding_channel = ticker['last']+prm[0]/2
            
            if self.cross_under(last_switch,prm[3]): 
                prepare_order['mode'] = 'dons'
                piramidding_channel = ticker['last']-prm[0]/2
           
            ### close
            if self.cross_under(last_switch,prm[1]):
                if prepare_order['mode'] == 'donb':  
                    prepare_order['mode'] = 'closes'
            
            if self.cross_over(last_switch,prm[1]): 
                if prepare_order['mode'] == 'dons':
                    prepare_order['mode'] = 'closeb'
                    
            if prepare_order['mode'] == 'closeb': 
                if ticker['pos'] >= 0:
                    # self.cancel_all_order()
                    prepare_order['mode'] = 'init'
                    don_lot = init_don_lot
                    piramidding_channel=0

            if prepare_order['mode'] == 'closes': 
                if ticker['pos'] <= 0:
                    # self.cancel_all_order()
                    prepare_order['mode'] = 'init'
                    don_lot = init_don_lot
                    piramidding_channel=0

            ## piramidding
            if prepare_order['mode'] == 'donb':
                if self.cross_over(last_switch,piramidding_channel):
                    if abs(don_lot) < abs(don_max_lot): 
                        don_lot = don_lot + don_pira_lot
                        piramidding_channel = piramidding_channel+prm[0]/2

            if prepare_order['mode'] == 'dons':
                if self.cross_under(last_switch,piramidding_channel):       
                    if abs(don_lot) < abs(don_max_lot):
                        don_lot = don_lot + don_pira_lot
                        piramidding_channel = piramidding_channel-prm[0]/2

            ## switch mode(mm) 
            if prepare_order['mode'] != 'donb'\
                and prepare_order['mode'] != 'dons'\
                and prepare_order['mode'] != 'closeb'\
                and prepare_order['mode'] != 'closes':
                prepare_order['mode'] = 'mm'

            # set switch
            last_switch = self.make_my_fifo(last_switch,ticker['last'])            
            status_switch = self.make_my_fifo(status_switch,prepare_order['mode']) 

            # order!!        
            ## prepare order
            execute_order==[]
            if last_switch[0] != last_switch[1]\
                and prepare_order['execute'] == 'no':
                if prepare_order['mode'] == 'mm':
                    if ticker['last'] == ticker['buy']: 
                        set_order['price'] = ticker['buy']-1
                    else:
                        set_order['price'] = ticker['buy']-0.5
                    #set_order['price'] = ticker['buy'] 
                    set_order['orderQty'] = mm_lot
                    set_order['side'] = 'Buy'
                    execute_order.append(set_order)
                    # import pdb; pdb.set_trace()
                    set_order = {}

                    if ticker['last'] == ticker['sell']: 
                        set_order['price'] = ticker['sell']+1
                    else:
                        set_order['price'] = ticker['sell']+0.5
                    #set_order['price'] = ticker['sell'] 
                    set_order['orderQty'] = mm_lot
                    set_order['side'] = 'Sell'
                    execute_order.append(set_order)
    
                if prepare_order['mode'] == 'donb':
                    set_order['price'] = ticker['last'] 
                    set_order['orderQty'] = don_lot - ticker['pos']
                    set_order['side'] = 'Buy'
                    execute_order.append(set_order)
    
                if prepare_order['mode'] == 'dons': 
                    set_order['price'] = ticker['last'] 
                    set_order['orderQty'] = don_lot + ticker['pos']
                    set_order['side'] = 'Sell'
                    execute_order.append(set_order)
    
                if prepare_order['mode'] == 'closeb':
                    set_order['price'] = ticker['last'] 
                    set_order['orderQty'] = -ticker['pos']
                    set_order['side'] = 'Sell'
                    execute_order.append(set_order)
    
                if prepare_order['mode'] == 'closes':
                    set_order['price'] = ticker['last'] 
                    set_order['orderQty'] = -ticker['pos']
                    set_order['side'] = 'Buy'
                    execute_order.append(set_order)

            ## control order
            if status_switch[0] != status_switch[1]:
                if len(execute_order)>0:
                    prepare_order['execute'] = 'yes'
            else:
                if last_switch[0] != last_switch[1]:       
                    if len(execute_order)>0:
                        prepare_order['execute'] = 'yes'

            if prepare_order['execute'] == 'yes':
                while True:
                    try:
                        # import pdb; pdb.set_trace()
                        self.exchange.create_bulk_orders(execute_order)
                        
                        ticker = self.get_info_bitmex()
                        last_switch = [ticker['last'],ticker['last']]
                        
                        #print(last_switch)
                        sleep(self.Sleep_Interval)
                    except:
                        logger.info("HTTPError raised. Retrying in 10 seconds...")
                        sleep(self.Long_Interval)
                        continue
                    break
                # init prm
                execute_order = []
                set_order = {}
                set_order.update(price=0,orderQty=0,side='init')
                prepare_order['execute'] = 'no'

            ## cancel control!!
           	## prepare cancel order
            cancel_execute_order=[]

            if prepare_order['mode'] == 'donb':
                for order in existing_orders:
                    if order['side'] == 'sell': 
                        cancel_execute_order.append(order)

            if prepare_order['mode'] == 'dons':
                for order in existing_orders:
                    if order['side'] == 'buy': 
                        cancel_execute_order.append(order)
                
            if prepare_order['mode'] == 'closeb':
                for order in existing_orders:
                    if order['side'] == 'buy': 
                        cancel_execute_order.append(order)

            if prepare_order['mode'] == 'closes':
                for order in existing_orders:
                    if order['side'] == 'sell': 
                        cancel_execute_order.append(order)

            if prepare_order['mode'] == 'mm':
                if abs(ticker['pos']) > mm_max_lot:
                    if ticker['pos'] > 0:
                        for order in existing_orders:
                            if order['side'] == 'buy': 
                                cancel_execute_order.append(order)

                    if ticker['pos'] < 0:
                        for order in existing_orders:
                            if order['side'] == 'sell': 
                                cancel_execute_order.append(order)

            if status_switch[0] != status_switch[1]\
                and status_switch[1] != 'init'\
                and status_switch[1] != 'cancel':
                    
                if cancel_execute_order != []:
                    ##cancel!!
                    self.exchange.cancel_bulk_orders(cancel_execute_order)
                    ticker = self.get_info_bitmex()
                    last_switch = [ticker['last'],ticker['last']]

                    cancel_execute_order = []
                    sleep(self.Sleep_Interval)
                    cancel_execute_order=[]

            ## prepare cancel order
            cancel_execute_order=[]

            ## control order amount
            if order_count > 150:

                if existing_orders:
                    max_price=0
                    min_price=0
                    for order in existing_orders:
                        if order['price'] > max_price:
                            max_price=order['price']
                            set_cancel_order=order
                    cancel_execute_order.append(set_cancel_order)
                    min_price=max_price
                    set_cancel_order={}
                    for order in existing_orders:
                        if order['price'] < min_price:
                            min_price=order['price']
                            set_cancel_order=order
                    cancel_execute_order.append(set_cancel_order)
                    status_switch = self.make_my_fifo(status_switch,'cancel')

            if status_switch[0] != status_switch[1]:                    
                if cancel_execute_order != []:
                    ##cancel!!
                    while True:
                        try:
                            # import pdb; pdb.set_trace()
                            self.exchange.cancel_bulk_orders(cancel_execute_order)
                            ticker = self.get_info_bitmex()
                            last_switch = [ticker['last'],ticker['last']]

                            cancel_execute_order = []
                            status_switch = ['init','init']
                            sleep(self.Sleep_Interval)
                        except:
                            logger.info("HTTPError raised. Retrying in 1 seconds...")
                            sleep(self.Sleep_Interval)
                            continue
                        break
            # sleep(self.Short_Interval) # while true
            
            # This will restart on very short downtime, but if it's longer,
            # the MM will crash entirely as it is unable to connect to the WS on boot.
            if not self.check_connection():
                logger.error("Realtime data connection unexpectedly closed, restarting.")
                self.restart()

            # per long term
            now = round(int(datetime.now().timestamp()))

            # per 1minutes order count check
            if ((now - self.Reference_Time_Value ) % self.Long_Interval) == 0: 
                prm = self.get_info_crypto_watch()
                self.market_report(sys._getframe().f_code.co_name,ticker,last_switch,prm)
                sleep(self.Sleep_Interval) # because Short_Interval is too short 
                
            # import pdb; pdb.set_trace()

            # per more long term setup_custom_logger
            if ((now - self.Reference_Time_Value ) % self.Sanity_Check_Term) == 0:
                self.wallet_report(sys._getframe().f_code.co_name)
                sleep(self.Sleep_Interval) # because Short_Interval is too short
                
    def test(self):
        print("----start----")
        price = self.get_info_crypto_watch()
        print("----prm:----"+str(price))
        
    def restart(self):
        logger.info("Restarting the market maker...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

#
# Helpers
#

def XBt_to_XBT(XBt):
    return float(XBt) / constants.XBt_TO_XBT
                
def run():
    logger.info('BitMEX Market Maker Version: %s\n' % constants.VERSION)

    om = OrderManager()
    # Try/except just keeps ctrl-c from printing an ugly stacktrace
    try:
        om.run_loop()
        # om.test()
        
    except (KeyboardInterrupt, SystemExit):
        sys.exit()
