from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fixit_api.config import settings
from fixit_api.database import get_auth_db
from fixit_api.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    token_query: Optional[str] = Query(None, alias="token"),
    auth_db: Session = Depends(get_auth_db)
) -> Optional[User]:
    auth_token = token or token_query
    if not auth_token:
        return None

    secrets_to_try = [
        settings.SECRET_KEY,
        settings.TRIP_CLOSER_SECRET_KEY,
        settings.FALLBACK_TRIP_KEY
    ]
    
    payload = None
    for secret in secrets_to_try:
        try:
            payload = jwt.decode(auth_token, secret, algorithms=[settings.ALGORITHM])
            if payload:
                break
        except JWTError:
            continue

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 인증 토큰입니다."
        )

    email: str = payload.get("sub") or payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="토큰에 사용자 정보가 없습니다.")

    user = auth_db.query(User).filter(User.email == email).first()
    return user
