from app.auth.security import hash_password, verify_password, create_token, decode_token
from datetime import timedelta

def test_password_hash_roundtrip():
    hashed=hash_password("StrongPassword123!")
    assert hashed != "StrongPassword123!"
    assert verify_password("StrongPassword123!",hashed)

def test_token_roundtrip():
    token,payload=create_token(1,"Patient","access",timedelta(minutes=5))
    decoded=decode_token(token)
    assert decoded["sub"]=="1" and decoded["type"]=="access"
