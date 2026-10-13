from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.auth.security import decode_token
bearer=HTTPBearer(auto_error=False)

def get_current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer), db:Session=Depends(get_db)):
    if not credentials: raise HTTPException(401,'Not authenticated')
    payload=decode_token(credentials.credentials)
    if not payload or payload.get('type')!='access': raise HTTPException(401,'Invalid or expired access token')
    user=db.get(User,int(payload['sub']))
    if not user or not user.is_active: raise HTTPException(401,'User is inactive or missing')
    return user

def require_roles(*roles):
    def checker(user:User=Depends(get_current_user)):
        if user.role not in roles: raise HTTPException(403,'Insufficient permissions')
        return user
    return checker
