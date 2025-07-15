# add_language_column.py
import asyncio
import asyncpg
from config import PG_CONFIG

async def add_language_column():
    try:
        conn = await asyncpg.connect(**PG_CONFIG)

        column_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='users'
                AND column_name='language'
            )
        """)

        if not column_exists:
            print("Adding language column to users table...")
            await conn.execute("""
                ALTER TABLE users
                ADD COLUMN language VARCHAR(2) DEFAULT 'ru'
            """)
            print("✅ Language column added successfully!")
        else:
            print("ℹ️ Language column already exists.")

        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'users'
            ORDER BY ordinal_position
        """)

        print("\nCurrent users table structure:")
        for col in columns:
            print(f"  - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']}, default: {col['column_default']})")

        await conn.close()
        print("\n✅ Database update complete!")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_language_column())