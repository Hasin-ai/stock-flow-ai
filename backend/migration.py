# Create a script like update_schema.py
from app.database import engine
from sqlalchemy import text

def add_name_column_to_trade_requests():
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE trade_requests ADD COLUMN name VARCHAR;"))
        conn.commit()

if __name__ == "__main__":
    add_name_column_to_trade_requests()
    print("Column 'name' added to trade_requests table")