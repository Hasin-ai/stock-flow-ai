### THIS FILE IS FOR DUMMY MIGRATING THE DATABASE SCHEMA ###

import logging
import sqlalchemy
from sqlalchemy.exc import SQLAlchemyError
from app.database import engine, Base
from app.models.user import User  # Import User model first since it's referenced by StockCart
from app.models.stock_cart import StockCart
from app.models.trade_request import TradeRequest
from app.models.activity_log import ActivityLog

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """
    Migrate the database tables in the correct order to respect foreign key constraints
    """
    try:
        # Check if stock_carts table exists and drop it
        inspector = sqlalchemy.inspect(engine)
        if 'stock_carts' in inspector.get_table_names():
            logger.info("Dropping existing stock_carts table...")
            StockCart.__table__.drop(engine)
            logger.info("Table dropped successfully")
        
        # Create all tables in the correct order
        logger.info("Creating tables in proper order...")
        
        # First, ensure the users table exists
        if 'users' not in inspector.get_table_names():
            logger.info("Creating users table...")
            User.__table__.create(engine)
            logger.info("Users table created successfully")
        
        # Now create the stock_carts table with proper foreign key
        logger.info("Creating stock_carts table with updated schema...")
        StockCart.__table__.create(engine)
        logger.info("Table created successfully with columns: id, user_id, symbol, quantity, price, trade_type")
        
        return True
    except SQLAlchemyError as e:
        logger.error(f"Error during migration: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Starting database migration...")
    success = migrate_database()
    
    if success:
        logger.info("Migration completed successfully")
    else:
        logger.error("Migration failed")