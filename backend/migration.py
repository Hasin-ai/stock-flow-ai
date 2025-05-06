# Create a script like update_schema.py
from app.database import engine
from sqlalchemy import text

def add_name_column():
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE stock_carts ADD COLUMN name VARCHAR;"))
        conn.commit()

if __name__ == "__main__":
    add_name_column()
    print("Column 'name' added to stock_carts table")