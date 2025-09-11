# (c) adarsh-goel (improved for Heroku by ChatGPT)
import os
import sys
import glob
import asyncio
import logging
import importlib
import time
import requests
from pathlib import Path
from pyrogram import idle, Client
from pyrogram.errors import BadMsgNotification
from .bot import StreamBot
from .vars import Var
from aiohttp import web
from .server import web_server
from .utils.keepalive import ping_server
from Adarsh.bot.clients import initialize_clients

# -------------------------------------------------------------------
# Logging configuration
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("aiohttp.web").setLevel(logging.ERROR)

# -------------------------------------------------------------------
# Time Sync Patch to avoid BadMsgNotification
# -------------------------------------------------------------------
def sync_time_and_patch(retries=3):
    for attempt in range(retries):
        try:
            r = requests.get("http://worldtimeapi.org/api/ip", timeout=5)
            if r.status_code == 200:
                unixtime = r.json()["unixtime"]
                drift = unixtime - int(time.time())
                if abs(drift) > 2:
                    logging.warning(f"[Time Sync] Adjusted drift by {drift} seconds")
                    real_time = time.time
                    time.time = lambda: real_time() + drift
                else:
                    logging.info("[Time Sync] System time is accurate")
                return
        except Exception as e:
            logging.error(f"[Time Sync] Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    logging.warning("[Time Sync] Could not synchronize time, using system clock")

# Patch time before Pyrogram starts
sync_time_and_patch()

# -------------------------------------------------------------------
# Load plugin paths
# -------------------------------------------------------------------
ppath = "Adarsh/bot/plugins/*.py"
files = glob.glob(ppath)

# -------------------------------------------------------------------
# Main async services
# -------------------------------------------------------------------
async def start_services():
    # ------------------- Start Telegram Bot with retry -------------------
    while True:
        try:
            print('------------------- Initializing Telegram Bot -------------------')
            await StreamBot.start()
            bot_info = await StreamBot.get_me()
            StreamBot.username = bot_info.username
            break
        except BadMsgNotification:
            logging.error("[Pyrogram Startup] BadMsgNotification: Client time not synced. Retrying in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"[Pyrogram Startup] Failed: {e}. Retrying in 5s...")
            await asyncio.sleep(5)

    print("------------------------------ DONE ------------------------------\n")

    # ------------------- Initialize Additional Clients -------------------
    print('---------------------- Initializing Clients ----------------------')
    await initialize_clients()
    print("------------------------------ DONE ------------------------------\n")

    # ------------------- Import Plugins -------------------
    print('--------------------------- Importing Plugins --------------------')
    for name in files:
        patt = Path(name)
        plugin_name = patt.stem.replace(".py", "")
        plugins_dir = Path(f"Adarsh/bot/plugins/{plugin_name}.py")
        import_path = f".plugins.{plugin_name}"
        spec = importlib.util.spec_from_file_location(import_path, plugins_dir)
        load = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(load)
        sys.modules["Adarsh.bot.plugins." + plugin_name] = load
        print("Imported => " + plugin_name)
    print()

    # ------------------- Start Keepalive -------------------
    if Var.ON_HEROKU:
        print("------------------ Starting Keep Alive Service ------------------")
        asyncio.create_task(ping_server())

    # ------------------- Start aiohttp Web Server -------------------
    print('-------------------- Initializing Web Server --------------------')
    runner = web.AppRunner(await web_server())
    await runner.setup()
    bind_address = "0.0.0.0"
    site = web.TCPSite(runner, bind_address, Var.PORT)
    await site.start()
    print('----------------------------- DONE ------------------------------\n')

    # ------------------- Summary -------------------
    print('---------------------------------------------------------------------------------------------------------')
    print(' follow me for more such exciting bots! https://github.com/aadhi000')
    print('---------------------------------------------------------------------------------------------------------')
    print('----------------------- Service Started -----------------------------------------------------------------')
    print(f'   bot        =>> {bot_info.first_name}')
    print(f'   server ip  =>> {bind_address}:{Var.PORT}')
    print(f'   Owner      =>> {Var.OWNER_USERNAME}')
    if Var.ON_HEROKU:
        print(f'   App URL    =>> {Var.FQDN}')
    print('---------------------------------------------------------------------------------------------------------')
    print('Give a star to my repo https://github.com/adarsh-goel/filestreambot-pro  also follow me for new bots')
    print('---------------------------------------------------------------------------------------------------------')

    # ------------------- Keep Alive -------------------
    await idle()

    # ------------------- Stop Bot Cleanly -------------------
    await StreamBot.stop()
    print('----------------------- Service Stopped -----------------------')

# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------
if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
        
        # ------------------- SIGTERM/SIGINT Handling for Heroku -------------------
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(StreamBot.stop()))
        
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        logging.info('----------------------- Service Stopped -----------------------')
    finally:
        loop.close()
