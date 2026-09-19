from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import DEMO_USERS, DemoUser, get_current_user, login

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: DemoUser


@router.post("/login", response_model=LoginResponse)
def do_login(req: LoginRequest) -> LoginResponse:
    token = login(req.username, req.password)
    if token is None:
        raise HTTPException(status_code=401, detail="invalid_username_or_password")
    return LoginResponse(token=token, user=DEMO_USERS[token])


@router.get("/me", response_model=DemoUser)
def get_me(user: DemoUser = Depends(get_current_user)) -> DemoUser:
    return user
