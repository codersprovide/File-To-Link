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
from pyrogram import idle, Client, errors
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
# Option 1: Monkey-patch time.time to avoid Pyrogram BadMsgNotification
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
# Safe message sending wrapper
# -------------------------------------------------------------------
async def safe_send_message(client: Client, chat_id, text, **kwargs):
    try:
        return await client.send_message(chat_id, text, **kwargs)
    except errors.PeerIdInvalid:
        logging.warning(f"[SafeSend] PeerIdInvalid: Could not send message to {chat_id}")
    except errors.RPCError as e:
        logging.error(f"[SafeSend] Telegram RPCError: {e}")
    except Exception as e:
        logging.error(f"[SafeSend] Unexpected error: {e}")
    return None

# -------------------------------------------------------------------
# Load plugins
# -------------------------------------------------------------------
ppath = "Adarsh/bot/plugins/*.py"
files = glob.glob(ppath)

async def start_services():
    # ------------------- Handle SIGTERM / SIGINT -------------------
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown_signal():
        logging.info("Stop signal received (SIGTERM / SIGINT). Exiting...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_signal)

    # ------------------- Start Telegram Bot -------------------
    while True:
        try:
            logging.info('------------------- Initializing Telegram Bot -------------------')
            await StreamBot.start()
            break  # Success, exit retry loop
        except errors.BadMsgNotification as e:
            logging.error(f"[Pyrogram Startup] BadMsgNotification: {e}. Retrying in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"[Pyrogram Startup] Failed: {e}. Retrying in 5s...")
            await asyncio.sleep(5)

    bot_info = await StreamBot.get_me()
    StreamBot.username = bot_info.username
    logging.info("------------------------------ DONE ------------------------------\n")

    # ------------------- Initialize additional clients -------------------
    logging.info('---------------------- Initializing Clients ----------------------')
    await initialize_clients()
    logging.info("------------------------------ DONE ------------------------------\n")

    # ------------------- Import plugins -------------------
    logging.info('--------------------------- Importing Plugins --------------------')
    for name in files:
        patt = Path(name)
        plugin_name = patt.stem.replace(".py", "")
        plugins_dir = Path(f"Adarsh/bot/plugins/{plugin_name}.py")
        import_path = f".plugins.{plugin_name}"
        spec = importlib.util.spec_from_file_location(import_path, plugins_dir)
        load = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(load)
        sys.modules["Adarsh.bot.plugins." + plugin_name] = load
        logging.info(f"Imported => {plugin_name}")

    # ------------------- Keepalive for Heroku -------------------
    if Var.ON_HEROKU:
        logging.info("------------------ Starting Keep Alive Service ------------------")
        asyncio.create_task(ping_server())

    # ------------------- Start aiohttp web server -------------------
    logging.info('-------------------- Initializing Web Server --------------------')
    runner = web.AppRunner(await web_server())
    await runner.setup()
    bind_address = "0.0.0.0"
    site = web.TCPSite(runner, bind_address, Var.PORT)
    await site.start()
    logging.info('----------------------------- DONE ------------------------------\n')

    # ------------------- Summary Info -------------------
    logging.info('---------------------------------------------------------------------------------------------------------')
    logging.info(' follow me for more such exciting bots! https://github.com/aadhi000')
    logging.info('---------------------------------------------------------------------------------------------------------')
    logging.info('----------------------- Service Started -----------------------------------------------------------------')
    logging.info(f'   bot        =>> {bot_info.first_name}')
    logging.info(f'   server ip  =>> {bind_address}:{Var.PORT}')
    logging.info(f'   Owner      =>> {Var.OWNER_USERNAME}')
    if Var.ON_HEROKU:
        logging.info(f'   App URL    =>> {Var.FQDN}')
    logging.info('---------------------------------------------------------------------------------------------------------')

    # Wait until SIGTERM / SIGINT
    await stop_event.wait()

    # Graceful shutdown
    await StreamBot.stop()
    await runner.cleanup()
    logging.info('----------------------- Service Stopped -----------------------')

# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------
if __name__ == '__main__':
    try:
        asyncio.run(start_services())
    except Exception as e:
        logging.error(f"Unexpected error in main: {e}")
