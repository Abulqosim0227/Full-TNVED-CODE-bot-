import asyncio
import asyncpg
from config import PG_CONFIG

async def setup_search_indexes():
    """Set up database indexes for fast searching"""
    try:
        conn = await asyncpg.connect(**PG_CONFIG)
        
        print("Setting up search indexes for hybrid search...")
        
        # Check if table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_name = 'm_classifier_hs1'
            )
        """)
        
        if not table_exists:
            print("❌ Table 'm_classifier_hs1' not found!")
            print("Please ensure the table exists with columns: cs_id, cs_code, cs_fullname")
            await conn.close()
            return
        
        # Create GIN index for full-text search (Russian language)
        print("Creating full-text search index...")
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_m_classifier_hs1_fulltext 
                ON m_classifier_hs1 
                USING gin(to_tsvector('russian', cs_fullname))
            """)
            print("✅ Full-text search index created")
        except Exception as e:
            print(f"⚠️ Full-text index might already exist: {e}")
        
        # Create index on cs_code for fast code lookups
        print("Creating code index...")
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_m_classifier_hs1_code 
                ON m_classifier_hs1(cs_code)
            """)
            print("✅ Code index created")
        except Exception as e:
            print(f"⚠️ Code index might already exist: {e}")
        
        # Create index on lowercase cs_fullname for ILIKE searches
        print("Creating lowercase name index...")
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_m_classifier_hs1_name_lower 
                ON m_classifier_hs1(LOWER(cs_fullname))
            """)
            print("✅ Lowercase name index created")
        except Exception as e:
            print(f"⚠️ Lowercase index might already exist: {e}")
        
        # Create trigram index for fuzzy matching (if pg_trgm extension is available)
        print("Checking for trigram extension...")
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_m_classifier_hs1_name_trgm
                ON m_classifier_hs1 
                USING gin(cs_fullname gin_trgm_ops)
            """)
            print("✅ Trigram index created for fuzzy matching")
        except Exception as e:
            print(f"ℹ️ Trigram index not created (extension might not be available): {e}")
        
        # Analyze table for query optimization
        print("Analyzing table for optimization...")
        await conn.execute("ANALYZE m_classifier_hs1")
        print("✅ Table analyzed")
        
        # Show table statistics
        count = await conn.fetchval("SELECT COUNT(*) FROM m_classifier_hs1")
        print(f"\n📊 Statistics:")
        print(f"   Total HS codes in database: {count:,}")
        
        # Test search performance
        print("\n🧪 Testing search performance...")
        
        # Test code search
        start = asyncio.get_event_loop().time()
        test_code = await conn.fetchval("SELECT cs_code FROM m_classifier_hs1 WHERE cs_code LIKE '02%' LIMIT 1")
        code_time = (asyncio.get_event_loop().time() - start) * 1000
        print(f"   Code search: {code_time:.2f}ms")
        
        # Test text search
        start = asyncio.get_event_loop().time()
        test_text = await conn.fetchval("""
            SELECT cs_code FROM m_classifier_hs1 
            WHERE to_tsvector('russian', cs_fullname) @@ plainto_tsquery('russian', 'мясо')
            LIMIT 1
        """)
        text_time = (asyncio.get_event_loop().time() - start) * 1000
        print(f"   Text search: {text_time:.2f}ms")
        
        await conn.close()
        print("\n✅ Database optimization complete!")
        print("   Your bot now has hybrid search: fast database lookups + smart AI fallback")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Setting up database for hybrid search...")
    asyncio.run(setup_search_indexes()) 