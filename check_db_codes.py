# check_db_codes.py
import asyncio
import asyncpg
from config import PG_CONFIG

async def check_database_codes():
    try:
        conn = await asyncpg.connect(**PG_CONFIG)

        print("🔍 Checking m_classifier_hs1 table for missing codes...\n")

        total = await conn.fetchval("SELECT COUNT(*) FROM m_classifier_hs1")
        print(f"Total entries: {total:,}")

        null_codes = await conn.fetchval("""
            SELECT COUNT(*) FROM m_classifier_hs1
            WHERE cs_code IS NULL
        """)
        print(f"Entries with NULL codes: {null_codes:,}")

        empty_codes = await conn.fetchval("""
            SELECT COUNT(*) FROM m_classifier_hs1
            WHERE cs_code = '' OR LENGTH(TRIM(cs_code)) = 0
        """)
        print(f"Entries with empty codes: {empty_codes:,}")

        if null_codes > 0 or empty_codes > 0:
            print("\n⚠️ Examples of entries without proper codes:")
            examples = await conn.fetch("""
                SELECT cs_id, cs_code, LEFT(cs_name, 100) as name_preview
                FROM m_classifier_hs1
                WHERE cs_code IS NULL OR cs_code = '' OR LENGTH(TRIM(cs_code)) = 0
                LIMIT 5
            """)

            for row in examples:
                print(f"ID: {row['cs_id']}, Code: '{row['cs_code']}', Name: {row['name_preview']}...")

        print("\n📊 Code format analysis:")
        code_lengths = await conn.fetch("""
            SELECT LENGTH(cs_code) as len, COUNT(*) as count
            FROM m_classifier_hs1
            WHERE cs_code IS NOT NULL AND cs_code != ''
            GROUP BY LENGTH(cs_code)
            ORDER BY len
        """)

        for row in code_lengths:
            print(f"  Length {row['len']}: {row['count']:,} codes")

        await conn.close()

        if null_codes > 0 or empty_codes > 0:
            print("\n❗ RECOMMENDATION: Some entries have missing codes.")
            print("   The bot will skip these entries during search.")
        else:
            print("\n✅ All entries have valid codes!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_database_codes())