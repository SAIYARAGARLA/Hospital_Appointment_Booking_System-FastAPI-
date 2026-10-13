
from sqlalchemy import text
from app.database import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DATABASE()"))
        print("Database connection successful.")
        print("Connected database:", result.scalar())
except Exception as error:
    print("Database connection failed.")
    print(error)
