"""Minimal role-gated access control.

The existing architecture has NO authentication or authorization layer at
all — every endpoint is wide open. This adds one, scoped to exactly what
the demo needs: a hardcoded set of demo users with a role each (no identity
provider integration — deliberately out of scope under hackathon time
pressure, per the follow-up spec's own guidance that a stubbed set of users
is fine here), and a FastAPI dependency that reads a role from a header and
gates each endpoint.

Ownership scoping note: "Agent — own calls only" from the spec assumes a
human agent is assigned to specific calls. This build's calls are all
placed autonomously by the AI orchestrator — there is no per-agent call
assignment anywhere in the data model, and inventing one would be adding a
concept the rest of the app doesn't support. So the scoping actually
implemented is by RESOURCE TYPE, not per-call ownership: any authenticated
Agent can view transcripts (call_records), Team Lead and above can also
view recordings (call_recordings), and only Admin can delete one. If a real
per-agent assignment model is added later, tighten AGENT's transcript
access to a WHERE clause on that column — the dependency shape here
(`require_role`) doesn't change.
"""

from enum import IntEnum
from typing import Optional

from fastapi import Header, HTTPException
from pydantic import BaseModel


class Role(IntEnum):
    AGENT = 1
    TEAM_LEAD = 2
    ADMIN = 3


class DemoUser(BaseModel):
    username: str
    display_name: str
    role: Role


# Hardcoded demo directory — a real build swaps this for an identity
# provider lookup; the token header stays the same shape either way. Named
# individuals (not just "agent.demo") so each role clearly has its own real
# login, including a distinct Agent account — the login form below checks a
# username+password pair against this table and hands back the matching
# token, rather than the frontend just knowing the token values upfront.
DEMO_USERS: dict[str, DemoUser] = {
    "agent-demo-token": DemoUser(username="alex.kim", display_name="Alex Kim", role=Role.AGENT),
    "lead-demo-token": DemoUser(username="priya.nair", display_name="Priya Nair", role=Role.TEAM_LEAD),
    "admin-demo-token": DemoUser(username="sam.torres", display_name="Sam Torres", role=Role.ADMIN),
}

# username -> (password, token). Demo-only, plaintext, on purpose — a real
# build replaces this whole module with an identity provider; nothing here
# is meant to survive contact with production credentials.
DEMO_CREDENTIALS: dict[str, tuple[str, str]] = {
    "alex.kim": ("agent123", "agent-demo-token"),
    "priya.nair": ("lead123", "lead-demo-token"),
    "sam.torres": ("admin123", "admin-demo-token"),
}


def login(username: str, password: str) -> Optional[str]:
    """Returns the matching demo token, or None for a bad username/password
    — the actual credential check for POST /auth/login."""
    entry = DEMO_CREDENTIALS.get(username)
    if entry is None or entry[0] != password:
        return None
    return entry[1]


def get_current_user(x_demo_token: Optional[str] = Header(default=None)) -> DemoUser:
    if not x_demo_token or x_demo_token not in DEMO_USERS:
        raise HTTPException(
            status_code=401,
            detail="missing_or_invalid_demo_token — set the X-Demo-Token header "
            "(try 'agent-demo-token', 'lead-demo-token', or 'admin-demo-token')",
        )
    return DEMO_USERS[x_demo_token]


def require_role(minimum: Role):
    """Dependency factory: `Depends(require_role(Role.TEAM_LEAD))` — raises
    403 for an authenticated user below the required role, 401 for no/bad
    token at all (via get_current_user)."""

    def _checker(x_demo_token: Optional[str] = Header(default=None)) -> DemoUser:
        user = get_current_user(x_demo_token)
        if user.role < minimum:
            raise HTTPException(
                status_code=403,
                detail=f"requires role {minimum.name} or above — {user.username} is {user.role.name}",
            )
        return user

    return _checker
