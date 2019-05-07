import logging
from market_maker.settings import settings


def setup_custom_logger(name, log_level=settings.LOG_LEVEL):


    if name == 'root': 

        # Set log output name
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        # Set log console output
        sh = logging.StreamHandler()
        logger.addHandler(sh)
        # Set log output format
        formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        sh.setFormatter(formatter)
    
        return logger

    elif name == 'market_info':
        # Set log output name
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        # Set log console output
        mh = logging.FileHandler('xx_market_info.log', 'a')
        logger.addHandler(mh)
        # Set log output format
        formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        mh.setFormatter(formatter)

        return logger

    elif name == 'order_info':
        # Set log output name
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        # Set log console output
        oh = logging.FileHandler('xx_orders_info.log', 'a')
        logger.addHandler(oh)
        # Set log output format
        formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        oh.setFormatter(formatter)

        return logger

    elif name == 'wallet_info':
        # Set log output name
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        # Set log console output
        wh = logging.FileHandler('xx_wallet_info.log', 'a')
        logger.addHandler(wh)
        # Set log output format
        formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        wh.setFormatter(formatter)

        return logger
