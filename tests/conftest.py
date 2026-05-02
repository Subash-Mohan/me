import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://me:me@localhost:5434/me_test")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
