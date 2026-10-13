from datetime import datetime, timedelta, timezone
from uuid import uuid4
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import settings
pwd_context=CryptContext(schemes=['bcrypt'], deprecated='auto')

def hash_password(password:str)->str: return pwd_context.hash(password)
def verify_password(password:str, hashed:str)->bool: return pwd_context.verify(password, hashed)
def create_token(user_id:int, role:str, token_type:str, expires_delta:timedelta):
    now=datetime.now(timezone.utc)
    payload={'sub':str(user_id),'role':role,'type':token_type,'jti':uuid4().hex,'iat':now,'exp':now+expires_delta}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm), payload

def decode_token(token:str):
    try: return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError: return None
