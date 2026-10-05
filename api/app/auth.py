"""auth.py — aktueller Nutzer für measures.py und bridge.py.

Phase 0: Demo-User wird anhand des /demo-Pfads erkannt.
Echte Magic-Link-Authentifizierung kommt in v0.6.
"""
from __future__ import annotations
from dataclasses import dataclass
from fastapi import Request


@dataclass
class UserContext:
    id: str | None
    farm_id: str
    is_demo: bool


# Demo-Farm-ID (Musterbetrieb Flachgau aus seed_demo.py)
DEMO_FARM_ID = "demo-farm-flachgau"


def current_user(request: Request) -> UserContext:
    """
    Für Phase 0: jeder Zugriff auf /demo ist Demo-User (nur lesend).
    Alle anderen Pfade gelten als angemeldeter Landwirt des Demo-Betriebs.
    Echte Auth (Magic Link) folgt in v0.6.
    """
    is_demo = request.url.path.startswith("/demo") or \
              request.query_params.get("demo") == "1"
    return UserContext(
        id=None if is_demo else "demo-user-1",
        farm_id=DEMO_FARM_ID,
        is_demo=is_demo,
    )
