"""Create tables (local convenience) and seed demo data. Alembic is the production path."""
from app.db.base import Base
from app.db.session import engine
from app.services.seed import seed
from app.db.session import SessionLocal

# Ensure all models are registered before create_all.
import app.models  # noqa: F401


def init(seed_demo: bool = True) -> None:
    Base.metadata.create_all(bind=engine)
    if seed_demo:
        db = SessionLocal()
        try:
            result = seed(db)
            print(f"[PLI] Seed: {result}")
        finally:
            db.close()
    print("[PLI] Database siap.")


if __name__ == "__main__":
    init()
