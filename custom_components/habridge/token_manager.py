from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets, string, jwt
from typing import Any, Dict, Optional

from .const import ACCESS_TOKEN_TTL, REFRESH_TOKEN_TTL, JWT_ALG, CONF_CLIENT_SECRET

@dataclass
class TokenData:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int

class TokenManager:
    def __init__(self, hass, store, client_secret: str):
        self.hass = hass
        self.store = store
        self.client_secret = client_secret or "dev-secret"
        self._data: Dict[str, Any] = {"auth_codes": {}, "refresh_tokens": {}}

    async def async_load(self):
        stored = await self.store.async_load()
        if stored:
            self._data = stored

    async def _persist(self):
        await self.store.async_save(self._data)

    def _gen_code(self, length=40) -> str:
        return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

    def create_auth_code(self, user_id: str) -> str:
        code = self._gen_code(50)
        self._data["auth_codes"][code] = {"user_id": user_id, "created": datetime.utcnow().isoformat()}
        return code

    async def exchange_code(self, code: str) -> Optional[TokenData]:
        info = self._data["auth_codes"].pop(code, None)
        if not info:
            return None
        user_id = info["user_id"]
        access_token = jwt.encode({"sub": user_id, "iat": datetime.utcnow(), "exp": datetime.utcnow() + timedelta(seconds=ACCESS_TOKEN_TTL)}, self.client_secret, algorithm=JWT_ALG)
        refresh_token = self._gen_code(60)
        self._data["refresh_tokens"][refresh_token] = {"user_id": user_id, "created": datetime.utcnow().isoformat()}
        await self._persist()
        return TokenData(access_token=access_token, refresh_token=refresh_token, token_type="Bearer", expires_in=ACCESS_TOKEN_TTL)

    async def refresh(self, refresh_token: str) -> Optional[TokenData]:
        meta = self._data["refresh_tokens"].get(refresh_token)
        if not meta:
            return None
        user_id = meta["user_id"]
        access_token = jwt.encode({"sub": user_id, "iat": datetime.utcnow(), "exp": datetime.utcnow() + timedelta(seconds=ACCESS_TOKEN_TTL)}, self.client_secret, algorithm=JWT_ALG)
        return TokenData(access_token=access_token, refresh_token=refresh_token, token_type="Bearer", expires_in=ACCESS_TOKEN_TTL)
