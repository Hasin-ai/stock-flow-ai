### THIS FILE IS FOR DUMMY MIGRATING THE DATABASE SCHEMA ###



from app.database import engine, Base, get_db
from app.models.user import User, ApprovalStatus
from app.models.activity_log import ActivityLog
from app.models.trade_request import TradeRequest
from app.models.stock_cart import StockCart
from sqlalchemy import text

# Check if column exists
def column_exists(column_name, table_name):
    with engine.connect() as connection:
        result = connection.execute(text(
            f"SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            f"WHERE table_name='users' AND column_name='{column_name}');"
        ))
        return result.scalar()

# Add column if it doesn't exist
def add_approval_status_column():
    if not column_exists('approval_status', 'users'):
        print("Adding approval_status column to users table...")
        with engine.connect() as connection:
            # Create enum type if it doesn't exist
            connection.execute(text(
                "DO $$ BEGIN "
                "    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'approvalstatus') THEN "
                "        CREATE TYPE approvalstatus AS ENUM ('pending', 'approved', 'rejected'); "
                "    END IF; "
                "END $$;"
            ))
            # Add column with default value
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN approval_status approvalstatus "
                "NOT NULL DEFAULT 'pending';"
            ))
            connection.commit()
            print("Column added successfully!")
    else:
        print("approval_status column already exists in users table")

# This will attempt to create the tables with all current model definitions
def recreate_schema():
    try:
        print("Creating tables based on current models...")
        Base.metadata.create_all(bind=engine)
        print("Schema update completed successfully!")
    except Exception as e:
        print(f"Error updating schema: {str(e)}")

if __name__ == "__main__":
    add_approval_status_column()
    recreate_schema()