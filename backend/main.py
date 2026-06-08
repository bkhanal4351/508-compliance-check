# main.py — The entry point for the FastAPI backend server.
#
# FastAPI is a modern Python web framework that automatically handles:
#   • Routing: mapping URL paths (/api/scan/url) to Python functions
#   • Request parsing: turning JSON bodies / form uploads into Python objects
#   • Response serialisation: converting Python dicts into JSON responses
#   • CORS: letting the React dev server (port 5173) talk to this server (port 8000)
#
# To start the server: cd backend && uvicorn main:app --reload
# --reload means the server restarts automatically whenever you save a file.

import sys
from pathlib import Path

# ── Path setup ───────────────────────────────────────────────────────────────
# When uvicorn starts from the backend/ directory, Python automatically adds
# backend/ to sys.path, so "from scanners.web import ..." resolves correctly.
#
# The one extra entry needed is url_checker/ itself: the modules inside it use
# relative-style imports like "from extractors.base import ..." which only work
# when url_checker/ is directly on sys.path (not just backend/).
sys.path.insert(0, str(Path(__file__).parent / "url_checker"))

from fastapi import FastAPI                  # the core web framework class
from fastapi.middleware.cors import CORSMiddleware  # handles cross-origin requests

# Import our two route groups — each is defined in its own file
from routers import scanner_508, url_checker

# ── Create the FastAPI application ───────────────────────────────────────────
# This 'app' object is what uvicorn starts.  All routes are registered on it.
app = FastAPI(
    title="508 Compliance & URL Checker API",
    version="2.0.0",
)

# ── CORS middleware ───────────────────────────────────────────────────────────
# Browsers block JavaScript from talking to a different origin (host+port).
# Our React app runs on localhost:5173 and needs to call localhost:8000.
# CORSMiddleware tells the browser "yes, that cross-origin request is allowed".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # React dev servers
    allow_credentials=True,     # allow cookies / auth headers if needed later
    allow_methods=["*"],        # allow GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],        # allow any request headers
)

# ── Register route groups ─────────────────────────────────────────────────────
# include_router() mounts all the routes defined in each router module.
# prefix="/api/scan" means every route in scanner_508.router starts with /api/scan
# (e.g. the "/url" route becomes /api/scan/url).
app.include_router(scanner_508.router, prefix="/api/scan",     tags=["508 Scanner"])
app.include_router(url_checker.router, prefix="/api/urlcheck", tags=["URL Checker"])


# ── Health-check endpoint ─────────────────────────────────────────────────────
# A simple GET /api/health that returns {"status": "ok"}.
# Useful for monitoring or to verify the server is running.
@app.get("/api/health")
async def health():
    return {"status": "ok"}
