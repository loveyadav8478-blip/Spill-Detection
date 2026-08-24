from db import engine
from alchemy import Base


Base.metadata.create_all(
    bind=engine
)

print("Database tables created successfully.")