import sys
from app.database import SessionLocal
from app.models import User
from app.auth.security import hash_password
if len(sys.argv)!=5:
    raise SystemExit('Usage: python scripts/create_admin.py email full_name 10_digit_phone password')
email,name,phone,password=sys.argv[1:]
if not phone.isdigit() or len(phone)!=10: raise SystemExit('Phone must be exactly 10 digits')
db=SessionLocal()
try:
    if db.query(User).filter_by(email=email.lower()).first(): raise SystemExit('Email already exists')
    user=User(email=email.lower(),full_name=name,phone=phone,password_hash=hash_password(password),role='Admin',is_active=True)
    db.add(user); db.commit(); print(f'Admin created: {email}')
finally: db.close()
