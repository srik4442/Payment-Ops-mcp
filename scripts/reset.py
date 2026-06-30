"""
Reset script: drops and recreates all DB tables for a clean demo slate.
Does NOT touch Stripe — test customers/charges remain in Stripe dashboard.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from src.db.database import engine
from src.models.models import Base


def reset():
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Reset complete. Run scripts/seed.py to repopulate.")


if __name__ == "__main__":
    reset()
