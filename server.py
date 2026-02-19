"""Swiss Caselaw MCP Server — FastAPI with OAuth 2.0 + Streamable HTTP transport."""
import base64
import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

import aiosqlite
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from starlette.types import Scope, Receive, Send

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from stub_mcp_server import mcp as mcp_instance

DB_PATH = Path(__file__).parent / "keys.db"
STATIC_DIR = Path(__file__).parent / "static"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8090")

# In-memory stores
auth_codes: dict[str, dict] = {}  # code -> {api_key, code_challenge, code_challenge_method}
clients: dict[str, dict] = {}  # client_id -> registration info
authenticated_sessions: set[str] = set()  # session IDs that have been authenticated


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                last_used TEXT,
                requests_today INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1
            )
        """)
        await db.commit()


def get_base_url():
    url = os.environ.get("BASE_URL")
    if url:
        return url.rstrip("/")
    try:
        return Path("/tmp/caselaw-base-url").read_text().strip().rstrip("/")
    except FileNotFoundError:
        return "http://localhost:8090"


# ─── Authenticated MCP ASGI App (mounted at /mcp) ───
class AuthenticatedMCPApp:
    def __init__(self):
        self._session_manager = None
        self._asgi_app = None

    def setup(self, session_manager):
        self._session_manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()
            session_id = headers.get(b"mcp-session-id", b"").decode()
            query_string = scope.get("query_string", b"").decode()

            if session_id and session_id in authenticated_sessions:
                pass  # already authenticated
            else:
                key = None
                if auth.startswith("Bearer "):
                    key = auth[7:]
                else:
                    for part in query_string.split("&"):
                        if part.startswith("key="):
                            key = part[4:]

                # Async DB check
                row = None
                if key:
                    async with aiosqlite.connect(DB_PATH) as db:
                        cursor = await db.execute("SELECT active FROM api_keys WHERE key = ?", (key,))
                        row = await cursor.fetchone()

                if not row or not row[0]:
                    await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
                    await send({"type": "http.response.body", "body": b'{"error":"Unauthorized"}', "more_body": False})
                    return

            # Intercept send to capture session ID
            original_send = send

            async def capturing_send(message):
                if message["type"] == "http.response.start":
                    resp_headers = dict(message.get("headers", []))
                    sid = resp_headers.get(b"mcp-session-id", b"").decode()
                    if sid and message.get("status") == 200:
                        authenticated_sessions.add(sid)
                    if scope.get("method") == "DELETE" and session_id:
                        authenticated_sessions.discard(session_id)
                await original_send(message)

            await self._session_manager.handle_request(scope, receive, capturing_send)
        else:
            await self._session_manager.handle_request(scope, receive, send)


mcp_app = AuthenticatedMCPApp()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    base = get_base_url()
    Path("/tmp/caselaw-base-url").write_text(base)

    session_manager = StreamableHTTPSessionManager(
        app=mcp_instance._mcp_server,
        json_response=True,
        stateless=False,
    )
    mcp_app.setup(session_manager)

    async with session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)

# Mount MCP app
app.mount("/mcp", mcp_app)


# Raw ASGI middleware to rewrite /mcp -> /mcp/ (avoid Starlette 307 redirect)
class SlashRewriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
        await self.app(scope, receive, send)

app.add_middleware(SlashRewriteMiddleware)


# ─── OAuth 2.0 Discovery ───
@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_protected_resource():
    base = get_base_url()
    return JSONResponse({
        "resource": base,
        "authorization_servers": [base],
    })


@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    base = get_base_url()
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
    })


# ─── OAuth Dynamic Client Registration ───
@app.post("/register")
async def register_client(request: Request):
    body = await request.json()
    client_id = str(uuid.uuid4())
    clients[client_id] = {
        "client_id": client_id,
        "client_secret": "not-used",
        "redirect_uris": body.get("redirect_uris", []),
    }
    return JSONResponse({
        "client_id": client_id,
        "client_secret": "not-used",
        "redirect_uris": body.get("redirect_uris", []),
    })


# ─── OAuth Authorization ───
@app.get("/authorize")
async def authorize(
    client_id: str,
    redirect_uri: str,
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
    response_type: str = "code",
    scope: str = "",
):
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Swiss Caselaw — Authorize</title>
<style>
body {{ font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f7f8fa; }}
.card {{ background: white; border-radius: 12px; padding: 2rem; max-width: 420px; width: 100%; box-shadow: 0 2px 12px rgba(0,0,0,0.1); text-align: center; }}
h2 {{ color: #1a2744; margin-bottom: 0.5rem; }}
p {{ color: #5a6070; margin-bottom: 1.5rem; font-size: 0.95rem; }}
input {{ width: 100%; padding: 0.75rem; border: 1.5px solid #e2e6ed; border-radius: 7px; font-size: 1rem; margin-bottom: 1rem; }}
button {{ width: 100%; padding: 0.75rem; background: #1a2744; color: white; border: none; border-radius: 7px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
button:hover {{ background: #243560; }}
</style></head><body>
<div class="card">
<h2>🏛️ Swiss Caselaw</h2>
<p>Enter your API key to connect</p>
<form method="POST" action="/authorize/submit">
<input type="hidden" name="client_id" value="{client_id}">
<input type="hidden" name="redirect_uri" value="{redirect_uri}">
<input type="hidden" name="state" value="{state}">
<input type="hidden" name="code_challenge" value="{code_challenge}">
<input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
<input type="password" name="api_key" placeholder="sk-claw-..." required>
<button type="submit">Verbinden</button>
</form>
</div></body></html>"""
    return HTMLResponse(html)


@app.post("/authorize/submit")
async def authorize_submit(request: Request):
    form = await request.form()
    api_key = form.get("api_key", "")
    redirect_uri = form.get("redirect_uri", "")
    state = form.get("state", "")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT active FROM api_keys WHERE key = ?", (api_key,))
        row = await cur.fetchone()
    if not row or not row[0]:
        return HTMLResponse("<h2>Invalid API key</h2><p>Please go back and try again.</p>", status_code=401)

    code_challenge = form.get("code_challenge", "")
    code_challenge_method = form.get("code_challenge_method", "")

    code = secrets.token_urlsafe(32)
    auth_codes[code] = {
        "api_key": api_key,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }

    params = {"code": code}
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)


# ─── OAuth Token Exchange ───
@app.post("/token")
async def token_exchange(request: Request):
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        body = await request.json()
    else:
        form = await request.form()
        body = dict(form)

    code = body.get("code", "")
    auth_record = auth_codes.pop(code, None)
    if not auth_record:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    api_key = auth_record["api_key"]
    stored_challenge = auth_record.get("code_challenge", "")
    challenge_method = auth_record.get("code_challenge_method", "")

    # PKCE verification
    if stored_challenge and challenge_method == "S256":
        code_verifier = body.get("code_verifier", "")
        if not code_verifier:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        if computed != stored_challenge:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

    return JSONResponse({
        "access_token": api_key,
        "token_type": "Bearer",
        "scope": "",
    })


# ─── API key management ───
class KeyRequest(BaseModel):
    email: str

@app.post("/api/keys")
async def create_key(req: KeyRequest):
    key = "sk-claw-" + secrets.token_urlsafe(18)[:24]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO api_keys (key, email) VALUES (?, ?)", (key, req.email))
        await db.commit()
    return {"key": key, "email": req.email}


@app.get("/api/keys/{key}/verify")
async def verify_key_endpoint(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT active FROM api_keys WHERE key = ?", (key,))
        row = await cur.fetchone()
    if row and row[0]:
        return {"valid": True}
    raise HTTPException(404, "Key not found or inactive")


@app.get("/api/config")
async def api_config():
    return JSONResponse({"base_url": get_base_url()})


# ─── Config download ───
@app.get("/download/config")
async def download_config(key: str):
    base = get_base_url()
    config = {
        "mcpServers": {
            "swiss-caselaw": {
                "url": f"{base}/mcp",
                "headers": {"Authorization": f"Bearer {key}"}
            }
        }
    }
    return JSONResponse(config, headers={"Content-Disposition": 'attachment; filename="swiss-caselaw-config.json"'})


# ─── Landing page ───
@app.get("/", response_class=HTMLResponse)
async def landing():
    return (STATIC_DIR / "index.html").read_text()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
