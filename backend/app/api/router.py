from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user

# Public routes (e.g. login, register, health)
public_router = APIRouter()

# Protected routes (chat, user profile, retrieval) requiring valid JWT
protected_router = APIRouter(dependencies=[Depends(get_current_user)])
