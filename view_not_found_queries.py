#!/usr/bin/env python3
"""
Script to view and analyze not found queries
This helps you understand what products users are searching for but can't find
"""

import asyncio
from utils.db import get_connection
from collections import Counter

async def view_not_found_queries(limit: int = 50, show_stats: bool = True):
    """View recent not found queries with statistics"""
    conn = await get_connection()
    try:
        # Get recent not found queries
        recent_queries = await conn.fetch("""
            SELECT nfq.query, nfq.language, nfq.search_timestamp, 
                   u.full_name, u.username
            FROM not_found_queries nfq
            LEFT JOIN users u ON nfq.user_id = u.telegram_id
            ORDER BY nfq.search_timestamp DESC
            LIMIT $1
        """, limit)
        
        if not recent_queries:
            print("📭 No not found queries yet!")
            return
        
        print(f"📊 Recent {len(recent_queries)} Not Found Queries:")
        print("=" * 80)
        
        for i, row in enumerate(recent_queries, 1):
            timestamp = row['search_timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            user_info = row['full_name'] or row['username'] or 'Unknown'
            print(f"{i:2d}. [{timestamp}] [{row['language'].upper()}] '{row['query']}' - {user_info}")
        
        if show_stats:
            print("\n" + "=" * 80)
            await show_statistics(conn)
            
    except Exception as e:
        print(f"❌ Error viewing not found queries: {e}")
    finally:
        await conn.close()

async def show_statistics(conn):
    """Show statistics about not found queries"""
    
    # Total count
    total_count = await conn.fetchval("SELECT COUNT(*) FROM not_found_queries")
    print(f"📈 Total not found queries: {total_count}")
    
    # Queries by language
    lang_stats = await conn.fetch("""
        SELECT language, COUNT(*) as count
        FROM not_found_queries
        GROUP BY language
        ORDER BY count DESC
    """)
    
    print("\n🌐 By Language:")
    for row in lang_stats:
        print(f"   {row['language'].upper()}: {row['count']} queries")
    
    # Most common not found queries
    common_queries = await conn.fetch("""
        SELECT query, COUNT(*) as count
        FROM not_found_queries
        GROUP BY query
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT 10
    """)
    
    if common_queries:
        print("\n🔥 Most Common Not Found Queries:")
        for i, row in enumerate(common_queries, 1):
            print(f"   {i:2d}. '{row['query']}' ({row['count']} times)")
    
    # Recent activity (last 7 days)
    recent_activity = await conn.fetchval("""
        SELECT COUNT(*)
        FROM not_found_queries
        WHERE search_timestamp >= NOW() - INTERVAL '7 days'
    """)
    
    print(f"\n📅 Last 7 days: {recent_activity} not found queries")

async def export_not_found_queries(filename: str = "not_found_queries.txt"):
    """Export all not found queries to a file"""
    conn = await get_connection()
    try:
        queries = await conn.fetch("""
            SELECT query, language, search_timestamp, COUNT(*) as frequency
            FROM not_found_queries
            GROUP BY query, language, search_timestamp
            ORDER BY search_timestamp DESC
        """)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("Not Found Queries Export\n")
            f.write("=" * 50 + "\n\n")
            
            for row in queries:
                timestamp = row['search_timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] [{row['language'].upper()}] {row['query']}\n")
        
        print(f"📄 Exported {len(queries)} queries to {filename}")
        
    except Exception as e:
        print(f"❌ Error exporting queries: {e}")
    finally:
        await conn.close()

async def main():
    print("🔍 Not Found Queries Analyzer")
    print("Choose an option:")
    print("1. View recent not found queries")
    print("2. View statistics only")
    print("3. Export all queries to file")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        limit = input("How many recent queries to show? (default 50): ").strip()
        limit = int(limit) if limit.isdigit() else 50
        await view_not_found_queries(limit=limit)
    
    elif choice == "2":
        conn = await get_connection()
        try:
            await show_statistics(conn)
        finally:
            await conn.close()
    
    elif choice == "3":
        filename = input("Export filename (default: not_found_queries.txt): ").strip()
        filename = filename if filename else "not_found_queries.txt"
        await export_not_found_queries(filename)
    
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    asyncio.run(main()) 