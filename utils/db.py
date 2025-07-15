# utils/db.py
from config import PG_CONFIG
import asyncpg

async def get_connection():
    return await asyncpg.connect(**PG_CONFIG)

async def create_not_found_table():
    """Create table for logging queries that didn't return results"""
    conn = await get_connection()
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS not_found_queries (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                query TEXT NOT NULL,
                language VARCHAR(2) DEFAULT 'ru',
                search_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                search_source VARCHAR(50) DEFAULT 'bot',
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)
        
        # Create index for better performance
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_not_found_queries_user_id 
            ON not_found_queries(user_id)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_not_found_queries_timestamp 
            ON not_found_queries(search_timestamp)
        """)
        
        print("✅ not_found_queries table created successfully")
        return True
    except Exception as e:
        print(f"❌ Error creating not_found_queries table: {e}")
        return False
    finally:
        await conn.close()

async def log_not_found_query(user_id: int, query: str, language: str = 'ru'):
    """Log a query that didn't return any results"""
    conn = await get_connection()
    try:
        await conn.execute("""
            INSERT INTO not_found_queries (user_id, query, language, search_source)
            VALUES ($1, $2, $3, $4)
        """, user_id, query, language, 'bot')
        print(f"📝 Logged not found query: '{query}' from user {user_id}")
    except Exception as e:
        print(f"❌ Error logging not found query: {e}")
    finally:
        await conn.close()

async def save_search_result(user_id: int, query: str, main_result: dict, similar_results: list = None, 
                           language: str = 'ru', total_results_found: int = 0):
    """Save successful search result to database"""
    conn = await get_connection()
    try:
        # Prepare similar results data
        similar_1_code = similar_1_description = similar_1_accuracy = None
        similar_2_code = similar_2_description = similar_2_accuracy = None
        similar_3_code = similar_3_description = similar_3_accuracy = None
        
        if similar_results:
            if len(similar_results) > 0:
                similar_1_code = similar_results[0].get('code')
                similar_1_description = similar_results[0].get('description')
                similar_1_accuracy = similar_results[0].get('accuracy')
            
            if len(similar_results) > 1:
                similar_2_code = similar_results[1].get('code')
                similar_2_description = similar_results[1].get('description')
                similar_2_accuracy = similar_results[1].get('accuracy')
            
            if len(similar_results) > 2:
                similar_3_code = similar_results[2].get('code')
                similar_3_description = similar_results[2].get('description')
                similar_3_accuracy = similar_results[2].get('accuracy')
        
        # Insert search result
        await conn.execute("""
            INSERT INTO search_results (
                user_id, query, main_code, main_description, main_accuracy,
                similar_1_code, similar_1_description, similar_1_accuracy,
                similar_2_code, similar_2_description, similar_2_accuracy,
                similar_3_code, similar_3_description, similar_3_accuracy,
                language, total_results_found
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        """, 
        user_id, query,
        main_result.get('code'), main_result.get('description'), main_result.get('accuracy'),
        similar_1_code, similar_1_description, similar_1_accuracy,
        similar_2_code, similar_2_description, similar_2_accuracy,
        similar_3_code, similar_3_description, similar_3_accuracy,
        language, total_results_found
        )
        
        print(f"✅ Saved search result: '{query}' -> {main_result.get('code')} for user {user_id}")
        
    except Exception as e:
        print(f"❌ Error saving search result: {e}")
    finally:
        await conn.close()

async def create_search_results_table():
    """Create table for storing successful search results"""
    conn = await get_connection()
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS search_results (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                query TEXT NOT NULL,
                search_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                main_code VARCHAR(255),
                main_description TEXT,
                main_accuracy NUMERIC(3,2),
                similar_1_code VARCHAR(255),
                similar_1_description TEXT,
                similar_1_accuracy NUMERIC(3,2),
                similar_2_code VARCHAR(255),
                similar_2_description TEXT,
                similar_2_accuracy NUMERIC(3,2),
                similar_3_code VARCHAR(255),
                similar_3_description TEXT,
                similar_3_accuracy NUMERIC(3,2),
                language VARCHAR(2) DEFAULT 'ru',
                total_results_found INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)
        
        # Create indexes for better performance
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_results_user_id 
            ON search_results(user_id)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_results_timestamp 
            ON search_results(search_timestamp)
        """)
        
        print("✅ search_results table created successfully")
        return True
    except Exception as e:
        print(f"❌ Error creating search_results table: {e}")
        return False
    finally:
        await conn.close()