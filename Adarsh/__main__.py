# (c) adarsh-goel (improved for Heroku by ChatGPT)
import os
import sys
import glob
import asyncio
import logging
import importlib
import time
from pathlib import Path
from pyrogram import idle
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
# Check for potential Heroku time drift (Pyrogram msg_id issue)
# -------------------------------------------------------------------
if "DYNO" in os.environ:
    now = int(time.time())
    logging.info(f"[Heroku Check] Current UNIX time: {now}")
    # Simple warning, not a hard fail
    if abs(now - int(time.time())) > 5:
        logging.warning("⚠️ Possible time drift detected in dyno clock. "
                        "Pyrogram may reject messages (BadMsgNotification).")

# -------------------------------------------------------------------
# Load plugins
# -------------------------------------------------------------------
ppath = "Adarsh/bot/plugins/*.py"
files = glob.glob(ppath)


async def start_services():
    print('\n')
    print('------------------- Initializing Telegram Bot -------------------')
    await StreamBot.start()
    bot_info = await StreamBot.get_me()
    StreamBot.username = bot_info.username
    print("------------------------------ DONE ------------------------------")
    print()

    print('---------------------- Initializing Clients ----------------------')
    await initialize_clients()
    print("------------------------------ DONE ------------------------------")
    print('\n')

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

    # ----------------------------------------------------------------
    # Start keepalive ping on Heroku
    # ----------------------------------------------------------------
    if Var.ON_HEROKU:
        print("------------------ Starting Keep Alive Service ------------------")
        asyncio.create_task(ping_server())

    # ----------------------------------------------------------------
    # Start aiohttp web server
    # ----------------------------------------------------------------
    print('-------------------- Initializing Web Server --------------------')
    runner = web.AppRunner(await web_server())
    await runner.setup()
    # Always bind to 0.0.0.0 on Heroku
    bind_address = "0.0.0.0"
    site = web.TCPSite(runner, bind_address, Var.PORT)
    await site.start()
    print('----------------------------- DONE ------------------------------')
    print()

    # ----------------------------------------------------------------
    # Summary Info
    # ----------------------------------------------------------------
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

    await idle()
    await StreamBot.stop()


# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------
if __name__ == '__main__':
    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        logging.info('----------------------- Service Stopped -----------------------')
