# Not Found Queries Logging System

This feature automatically logs all product searches that don't return any results, helping you understand what products users are looking for but your database doesn't have.

## 📋 Table Structure

The `not_found_queries` table contains:
- `id` - Primary key
- `user_id` - Telegram user ID (foreign key to users table)
- `query` - The search query that didn't return results
- `language` - User's language (ru/uz/en)
- `search_timestamp` - When the search was performed
- `search_source` - Source of the search (default: 'bot')

## 🚀 Setup

1. **Create the table** (run once):
   ```bash
   python init_not_found_table.py
   ```

2. **The bot automatically logs** failed searches when users search for products that aren't found.

## 📊 Viewing Data

Use the analyzer script to view and analyze the data:

```bash
python view_not_found_queries.py
```

Options:
- **View recent queries** - See the latest not found searches with user info
- **View statistics** - See summary statistics (total count, by language, most common queries)
- **Export to file** - Export all queries to a text file

## 🔍 Example Output

```
📊 Recent 5 Not Found Queries:
================================================================================
 1. [2024-01-15 14:30:25] [RU] 'смартфон айфон' - John Doe
 2. [2024-01-15 14:28:10] [UZ] 'kompyuter' - User123
 3. [2024-01-15 14:25:45] [EN] 'laptop computer' - Jane Smith

================================================================================
📈 Total not found queries: 125

🌐 By Language:
   RU: 89 queries
   UZ: 25 queries
   EN: 11 queries

🔥 Most Common Not Found Queries:
    1. 'смартфон' (15 times)
    2. 'компьютер' (12 times)
    3. 'телефон' (8 times)

📅 Last 7 days: 23 not found queries
```

## 💡 Use Cases

1. **Database Improvement** - Identify missing products to add to your TN VED database
2. **Analytics** - Understand user search patterns and common requests
3. **Business Intelligence** - See what products are in demand but not covered
4. **Quality Assurance** - Find search queries that might need better matching algorithms

## 🛠️ Database Queries

Some useful SQL queries for manual analysis:

```sql
-- Most common not found queries
SELECT query, COUNT(*) as frequency
FROM not_found_queries
GROUP BY query
ORDER BY frequency DESC
LIMIT 20;

-- Not found queries by date
SELECT DATE(search_timestamp) as date, COUNT(*) as count
FROM not_found_queries
GROUP BY DATE(search_timestamp)
ORDER BY date DESC;

-- User with most not found queries
SELECT u.full_name, u.username, COUNT(*) as not_found_count
FROM not_found_queries nfq
JOIN users u ON nfq.user_id = u.telegram_id
GROUP BY u.telegram_id, u.full_name, u.username
ORDER BY not_found_count DESC
LIMIT 10;
```

## 🔧 Maintenance

- The table automatically captures failed searches
- Consider periodic cleanup of old records if needed
- Monitor the table size and add indexes if performance becomes an issue
- Review the data regularly to improve your product database 