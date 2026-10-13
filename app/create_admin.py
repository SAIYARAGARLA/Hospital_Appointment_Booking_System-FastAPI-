
from getpass import getpass

from app.database import SessionLocal
from app.models import User
from app.auth.security import hash_password

db = SessionLocal()

try:
    full_name = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    phone = input("Admin phone (10 digits): ").strip()
    password = getpass("Create password: ")
    confirm = getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match.")
    elif len(password) < 8:
        print("Password must have at least 8 characters.")
    elif db.query(User).filter_by(role="Admin").first():
        print("An Admin account already exists.")
    elif db.query(User).filter_by(email=email).first():
        print("This email already exists. Use another email.")
    elif not full_name or not email or not phone.isdigit() or len(phone) != 10:
        print("Enter a name, valid email, and 10-digit phone number.")
    else:
        admin = User(
            full_name=full_name,
            email=email,
            phone=phone,
            password_hash=hash_password(password),
            role="Admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print("Admin account created successfully!")

except Exception as error:
    db.rollback()
    print("Error:", error)

finally:
    db.close()