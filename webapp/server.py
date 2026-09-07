"""Web demo (PRD §3 — the optional demo page).

The product is the SDK. This exists so the gate can be *seen*: paste an
address or URL, watch real Telegraph miners answer, open the receipt.

    python webapp/server.py           # http://127.0.0.1:8402

Every verdict served here is a live screening over x402. There is no
demo mode and no cached inference — if the wallet is empty, the page says
so rather than showing a canned result.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from telegraph_guard import Guard, GuardConfig, __version__  # noqa: E402
from telegraph_guard.classify import classify  # noqa: E402
from telegraph_guard.engine import PaymentUnavailable, signer_address  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent

#: Calibrated miner set — see docs. The auto-router prefers a miner that
#: returns identical prose for a clean router and a sanctioned mixer.
MINERS = ["9002", "95822412", "20260828", "5001"]

app = FastAPI(title="TelegraphGuard", docs_url=None, redoc_url=None)

_cfg = GuardConfig(deadline_ms=30000, miners=MINERS, miners_per_intent=2)
_guard = Guard(_cfg)
_lock = asyncio.Lock()


class ScreenRequest(BaseModel):
    target: str


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (HERE / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
async def status() -> JSONResponse:
    try:
        addr = signer_address()
    except PaymentUnavailable:
        addr = None
    try:
        reg = await _guard.registry()
        miners = {i: len(ms) for i, ms in reg.by_intent.items()}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc), "signer": addr})
    return JSONResponse(
        {
            "ok": True,
            "signer": addr,
            "miners": miners,
            "version": __version__,
            "thresholds": {"allow_below": _cfg.allow_below, "block_above": _cfg.block_above},
        }
    )


@app.post("/api/screen")
async def screen(req: ScreenRequest) -> JSONResponse:
    target = (req.target or "").strip()
    if not target:
        return JSONResponse({"error": "no target supplied"}, status_code=400)
    if classify(target) == "unknown":
        return JSONResponse(
            {
                "error": (
                    "Not a recognised target. Give an EVM address (0x + 40 hex), "
                    "a transaction hash (0x + 64 hex), an ENS name, or a URL."
                )
            },
            status_code=400,
        )

    # Screenings are serialised: concurrent x402 authorizations from one
    # signer race at settlement, and a demo page is not worth the flake.
    async with _lock:
        try:
            verdict = await _guard.screen(target, _cfg)
        except PaymentUnavailable as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)
        except Exception as exc:
            return JSONResponse(
                {"error": f"{type(exc).__name__}: {exc}"}, status_code=502
            )

    data = verdict.to_dict()
    data["evidence"] = sum(1 for s in verdict.signals if s.ok and s.signal_hash)
    return JSONResponse(data)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await _guard.aclose()


def main() -> None:
    import uvicorn

    from telegraph_guard.cli import _load_dotenv

    _load_dotenv()
    try:
        print(f"\n  signer  {signer_address()}")
    except PaymentUnavailable:
        print("\n  WARNING: TELEGRAPH_GUARD_KEY not set — screenings will fail.")
    print("  open    http://127.0.0.1:8402\n")
    uvicorn.run(app, host="127.0.0.1", port=8402, log_level="warning")


if __name__ == "__main__":
    main()
