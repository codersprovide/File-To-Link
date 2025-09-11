# (c) adarsh-goel (improved for Heroku by ChatGPT)
import os
import sys
import glob
import asyncio
import logging
import importlib
import time
import requests
import signal
from pathlib import Path
from pyrogram import idle, Client
from pyrogram.errors import PeerIdInvalid, BadMsgNotification
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
# Monkey-patch time.time to avoid Pyrogram BadMsgNotification
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
# Load plugins
# -------------------------------------------------------------------
ppath = "Adarsh/bot/plugins/*.py"
files = glob.glob(ppath)

async def start_services():
    # -------------------- Telegram Bot --------------------
    while True:
        try:
            print('------------------- Initializing Telegram Bot -------------------')
            await StreamBot.start()
            break
        except BadMsgNotification:
            logging.error("[Pyrogram Startup] BadMsgNotification: retrying in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"[Pyrogram Startup] Failed: {e}")
            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)

    bot_info = await StreamBot.get_me()
    StreamBot.username = bot_info.username
    print("------------------------------ DONE ------------------------------\n")

    # -------------------- Initialize Clients --------------------
    print('---------------------- Initializing Clients ----------------------')
    await initialize_clients()
    print("------------------------------ DONE ------------------------------\n")

    # -------------------- Import Plugins --------------------
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

    # -------------------- Start Keepalive --------------------
    if Var.ON_HEROKU:
        print("------------------ Starting Keep Alive Service ------------------")
        asyncio.create_task(ping_server())

    # -------------------- Web Server --------------------
    print('-------------------- Initializing Web Server --------------------')
    runner = web.AppRunner(await web_server())
    await runner.setup()
    bind_address = "0.0.0.0"
    site = web.TCPSite(runner, bind_address, Var.PORT)
    await site.start()
    print('----------------------------- DONE ------------------------------\n')

    # -------------------- Service Summary --------------------
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

    # -------------------- Idle --------------------
    await idle()
    await StreamBot.stop()

# -------------------------------------------------------------------
# Safe shutdown for Heroku SIGTERM
# -------------------------------------------------------------------
def init_shutdown(loop):
    def stop_signal_handler():
        logging.info("Stop signal received (SIGTERM/SIGINT). Shutting down...")
        loop.call_soon_threadsafe(lambda: asyncio.create_task(StreamBot.stop()))
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_signal_handler)

# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------
if __name__ == '__main__':
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        init_shutdown(loop)
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        logging.info('----------------------- Service Stopped -----------------------')
