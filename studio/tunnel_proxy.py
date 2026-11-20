"""Local-only proxy for a PeakCut server exposed through an ngrok tunnel."""
import os
from urllib.parse import urlparse
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse

TARGET = os.environ.get("PEAKCUT_REMOTE_URL", "").rstrip("/")
LISTEN_HOST = os.environ.get("PEAKCUT_PROXY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("PEAKCUT_PROXY_PORT", "8765"))
WEB = Path(__file__).resolve().parent.parent / "web"

if not TARGET:
    raise SystemExit("Set PEAKCUT_REMOTE_URL to the Kaggle ngrok URL.")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
               "transfer-encoding", "upgrade"}


def _headers(headers):
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP and k.lower() != "host"}


def _local_file(path: str):
    """Return a safe local UI asset, or None when the request belongs upstream."""
    if path == "" or path == "app" or path.startswith("app/"):
        return WEB / "index.html"
    if path == "brand" or path.startswith("brand/"):
        relative = path
    elif "/" not in path:
        relative = path
    else:
        return None
    candidate = (WEB / relative).resolve()
    try:
        candidate.relative_to(WEB.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


@app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(request: Request, path: str):
    local = _local_file(path) if request.method in ("GET", "HEAD") else None
    if local:
        return FileResponse(local)
    url = TARGET + "/" + path
    if request.url.query:
        url += "?" + request.url.query
    headers = _headers(request.headers)
    # httpx normally derives this from the URL, but set it explicitly so ngrok
    # never sees the browser's local Host header.
    headers["host"] = urlparse(TARGET).netloc
    # The browser is same-origin with this local gateway. Tell the remote
    # server the request came from its configured public origin.
    if headers.get("origin", "").rstrip("/") == f"http://{LISTEN_HOST}:{LISTEN_PORT}":
        headers["origin"] = TARGET
    client = httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=30.0), follow_redirects=False)
    upstream = await client.send(
        client.build_request(request.method, url, headers=headers, content=request.stream()),
        stream=True,
    )

    async def content():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(content(), status_code=upstream.status_code, headers=_headers(upstream.headers))


if __name__ == "__main__":
    uvicorn.run(app, host=LISTEN_HOST, port=LISTEN_PORT, log_level="warning")
