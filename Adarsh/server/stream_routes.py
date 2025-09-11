# Taken from megadlbot_oss <https://github.com/eyaadh/megadlbot_oss/blob/master/mega/webserver/routes.py>
# Thanks to Eyaadh <https://github.com/eyaadh>

import re
import time
import math
import logging
import secrets
import mimetypes
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from Adarsh.bot import multi_clients, work_loads, StreamBot
from Adarsh.server.exceptions import FIleNotFound, InvalidHash
from Adarsh import StartTime, __version__
from ..utils.time_format import get_readable_time
from ..utils.custom_dl import ByteStreamer, offset_fix, chunk_size
from Adarsh.utils.render_template import render_page
from Adarsh.vars import Var

routes = web.RouteTableDef()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ------------------------------
# Root status
# ------------------------------
@routes.get("/", allow_head=True)
async def root_route_handler(_):
    return web.json_response(
        {
            "server_status": "running",
            "uptime": get_readable_time(time.time() - StartTime),
            "telegram_bot": "@" + StreamBot.username,
            "connected_bots": len(multi_clients),
            "loads": dict(
                ("bot" + str(c + 1), l)
                for c, (_, l) in enumerate(
                    sorted(work_loads.items(), key=lambda x: x[1], reverse=True)
                )
            ),
            "version": __version__,
        }
    )


# ------------------------------
# /watch/{path} route
# ------------------------------
@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def watch_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            file_id = int(match.group(2))
        else:
            file_id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")

        content = await render_page(file_id, secure_hash)
        return web.Response(text=content, content_type="text/html")

    except InvalidHash as e:
        return web.HTTPForbidden(text=str(e))
    except FIleNotFound as e:
        return web.HTTPNotFound(text=str(e))
    except (AttributeError, BadStatusLine, ConnectionResetError) as e:
        logger.warning(f"Ignored exception: {e}")
        return web.Response(text="Temporary error occurred", status=503)
    except Exception as e:
        logger.exception("Unexpected error in watch_handler")
        return web.HTTPInternalServerError(text=str(e))


# ------------------------------
# /{path} route for file streaming
# ------------------------------
@routes.get(r"/{path:\S+}", allow_head=True)
async def file_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            file_id = int(match.group(2))
        else:
            file_id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")

        return await media_streamer(request, file_id, secure_hash)

    except InvalidHash as e:
        return web.HTTPForbidden(text=str(e))
    except FIleNotFound as e:
        return web.HTTPNotFound(text=str(e))
    except (AttributeError, BadStatusLine, ConnectionResetError) as e:
        logger.warning(f"Ignored exception: {e}")
        return web.Response(text="Temporary error occurred", status=503)
    except Exception as e:
        logger.exception("Unexpected error in file_handler")
        return web.HTTPInternalServerError(text=str(e))


# ------------------------------
# Media streaming logic
# ------------------------------
class_cache = {}


async def media_streamer(request: web.Request, file_id: int, secure_hash: str):
    range_header = request.headers.get("Range", None)

    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]

    if Var.MULTI_CLIENT:
        logger.info(f"Client {index} is now serving {request.remote}")

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
        logger.debug(f"Using cached ByteStreamer object for client {index}")
    else:
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect
        logger.debug(f"Created new ByteStreamer object for client {index}")

    file_info = await tg_connect.get_file_properties(file_id)

    if file_info.unique_id[:6] != secure_hash:
        logger.debug(f"Invalid hash for message ID {file_id}")
        raise InvalidHash

    file_size = file_info.file_size

    # Handle Range header safely
    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = 0
        until_bytes = file_size - 1

    req_length = until_bytes - from_bytes
    new_chunk_size = await chunk_size(req_length)
    offset = await offset_fix(from_bytes, new_chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = (until_bytes % new_chunk_size) + 1
    part_count = math.ceil(req_length / new_chunk_size)

    body = tg_connect.yield_file(
        file_info, index, offset, first_part_cut, last_part_cut, part_count, new_chunk_size
    )

    mime_type = file_info.mime_type or "application/octet-stream"
    file_name = file_info.file_name or f"{secrets.token_hex(2)}.unknown"
    disposition = "attachment"

    # Try to guess extension if missing
    if mime_type != "application/octet-stream" and "." not in file_name:
        try:
            file_name += f".{mime_type.split('/')[1]}"
        except Exception:
            pass

    resp_headers = {
        "Content-Type": mime_type,
        "Range": f"bytes={from_bytes}-{until_bytes}",
        "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
        "Content-Disposition": f'{disposition}; filename="{file_name}"',
        "Accept-Ranges": "bytes",
    }

    return_resp = web.Response(status=206 if range_header else 200, body=body, headers=resp_headers)

    if return_resp.status == 200:
        return_resp.headers.add("Content-Length", str(file_size))

    return return_resp
