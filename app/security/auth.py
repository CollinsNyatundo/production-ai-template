import datetime
import logging
from typing import List, Optional

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger("app.security.auth")

# FastAPI security schemes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# JWT Constants
SECRET_KEY = settings.jwt_secret
ALGORITHM = settings.jwt_algorithm


class User(BaseModel):
    username: str
    role: str = "user"
    permission_level: str = "low"  # "low" or "high"
    scopes: List[str] = Field(default_factory=list)
    tenant_id: str = "default-tenant"


# EXAMPLE credentials only - replace with a real user/API-key store (DB table,
# IdP, secrets manager) before using this outside local development. The
# admin key below is published in this repo's README as a curl example;
# treat it as compromised by definition and never reuse it anywhere real.
DEMO_API_KEYS = {
    "api-key-admin-12345": User(
        username="admin_user",
        role="admin",
        permission_level="high",
        scopes=["read", "write", "admin"],
        tenant_id="tenant-alpha",
    ),
    "api-key-user-54321": User(
        username="standard_user",
        role="user",
        permission_level="low",
        scopes=["read"],
        tenant_id="tenant-beta",
    ),
}

# EXAMPLE credentials for the standard OAuth token-exchange path - same caveat as above.
DEMO_USERS = {
    "admin": User(
        username="admin",
        role="admin",
        permission_level="high",
        scopes=["read", "write", "admin"],
        tenant_id="tenant-alpha",
    ),
    "user": User(
        username="user",
        role="user",
        permission_level="low",
        scopes=["read"],
        tenant_id="tenant-beta",
    ),
}


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    """Generates a signed JWT bearer token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.now(datetime.UTC) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Security(api_key_header),
) -> User:
    """
    Main dependency resolver for FastAPI authentication.
    Resolves caller identity using either JWT Bearer OAuth2 or X-API-Key headers.
    """
    # 1. API Key Authentication Check (Standard for service-to-service AI calls)
    if api_key and isinstance(api_key, str):
        user = DEMO_API_KEYS.get(api_key)
        if user:
            logger.info(f"Authenticated user '{user.username}' via API Key (Tenant: {user.tenant_id})")
            return user
        logger.warning("Invalid API Key header provided.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key.")

    # 2. JWT Bearer Token Authentication Check
    if token and isinstance(token, str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            sub = payload.get("sub")
            if sub is None or not isinstance(sub, str):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token: missing subject.",
                )
            username = sub

            # Fetch user profile from database
            user = DEMO_USERS.get(username)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User profile not found.",
                )

            logger.info(f"Authenticated user '{user.username}' via JWT Bearer (Tenant: {user.tenant_id})")
            return user
        except jwt.PyJWTError as e:
            logger.warning(f"JWT decode error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
            )

    # Fallback to local anonymous developer access if in development environment
    if settings.app_env == "development":
        logger.warning("No auth header provided. Falling back to default developer user profile.")
        return User(
            username="dev_anon",
            role="admin",
            permission_level="high",
            scopes=["read", "write", "admin"],
            tenant_id="dev-tenant-local",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide JWT token or X-API-Key.",
    )
