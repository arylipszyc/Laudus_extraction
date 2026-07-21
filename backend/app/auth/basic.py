"""HTTP Basic auth — reemplaza el OAuth de Google (reset base-limpia).

Una sola credencial compartida (env `APP_BASIC_AUTH_USER` / `APP_BASIC_AUTH_PASSWORD`).
No hay roles: quien tiene la credencial queda autenticado con acceso completo. Si en
el futuro se necesita RBAC, se reintroduce acá.
"""
import os
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_security = HTTPBasic()


@dataclass(frozen=True)
class Principal:
    """Usuario autenticado vía basic-auth."""
    username: str


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> Principal:
    """Valida las credenciales basic contra el env. 401 si no coinciden."""
    expected_user = os.getenv("APP_BASIC_AUTH_USER")
    expected_pwd = os.getenv("APP_BASIC_AUTH_PASSWORD")
    if not expected_user or not expected_pwd:
        raise HTTPException(status_code=503, detail="Auth no configurada")
    ok_user = secrets.compare_digest(credentials.username, expected_user)
    ok_pwd = secrets.compare_digest(credentials.password, expected_pwd)
    if not (ok_user and ok_pwd):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return Principal(username=credentials.username)
