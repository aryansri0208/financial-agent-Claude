import os
import robin_stocks.robinhood as rh
from dotenv import load_dotenv

load_dotenv()
rh.login(os.environ["ROBINHOOD_USERNAME"], os.environ["ROBINHOOD_PASSWORD"], store_session=True)
print("Login OK — session saved to ~/.tokens/robinhood.pickle")
