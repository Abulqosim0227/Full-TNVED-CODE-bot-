# utils/db_search.py
import asyncpg
from typing import List, Dict, Any, Optional
from utils.db import get_connection
import re
import logging

logger = logging.getLogger(__name__)

def is_valid_hs_code(code):
    if not isinstance(code, str):
        return False
    code = code.strip()
    return bool(re.fullmatch(r"\d{4}|\d{6}|\d{8}|\d{10}", code))


async def search_classifier_db(query: str, limit: int = 4) -> List[Dict[str, Any]]:
    conn = None
    results = []

    query_clean = query.strip().lower()

    try:
        conn = await get_connection()

        if re.match(r'^\d{2,10}$', query_clean):
            exact_code = await conn.fetch("""
                SELECT cs_code as code, cs_fullname as description
                FROM m_classifier_hs1
                WHERE cs_code = $1
                AND cs_code IS NOT NULL
                AND LENGTH(cs_code) > 0
                LIMIT $2
            """, query_clean, limit)

            valid_exact_matches = [
                 {"code": row['code'], "description": row['description']}
                 for row in exact_code if is_valid_hs_code(row['code'])
            ]
            if valid_exact_matches:
                results.extend(valid_exact_matches)
                logger.info(f"Found {len(valid_exact_matches)} results by exact code match for: {query}")
                if results:
                    return results

            prefix_code = await conn.fetch("""
                 SELECT cs_code as code, cs_fullname as description
                 FROM m_classifier_hs1
                 WHERE cs_code LIKE $1 || '%'
                 AND cs_code != $1
                 AND cs_code IS NOT NULL
                 AND LENGTH(cs_code) > 0
                 ORDER BY LENGTH(cs_code) ASC, cs_code ASC
                 LIMIT $2
             """, query_clean, limit - len(results))

            valid_prefix_matches = [
                {"code": row['code'], "description": row['description']}
                for row in prefix_code if is_valid_hs_code(row['code'])
            ]
            results.extend(valid_prefix_matches)
            logger.info(f"Found {len(valid_prefix_matches)} results by code prefix match for: {query}")
            if results:
                 return results

        text_results = await conn.fetch("""
            SELECT cs_code as code, cs_fullname as description,
                   ts_rank(to_tsvector('russian', cs_fullname),
                          plainto_tsquery('russian', $1)) as rank
            FROM m_classifier_hs1
            WHERE to_tsvector('russian', cs_fullname) @@ plainto_tsquery('russian', $1)
            AND cs_code IS NOT NULL
            AND LENGTH(cs_code) > 0
            ORDER BY rank DESC
            LIMIT $2
        """, query_clean, limit)

        if text_results:
            results = [
                {"code": row['code'], "description": row['description']}
                for row in text_results if is_valid_hs_code(row['code'])
            ]
            logger.info(f"Found {len(results)} results by full-text search for: {query}")
        else:
            words = query_clean.split()
            if not words:
                 return []

            like_clauses = [f"LOWER(cs_fullname) LIKE '%' || ${i+1} || '%'" for i in range(len(words))]
            where_clause_and = " AND ".join(like_clauses)

            partial_query = f"""
                SELECT cs_code as code, cs_fullname as description
                FROM m_classifier_hs1
                WHERE {where_clause_and}
                AND cs_code IS NOT NULL
                AND LENGTH(cs_code) > 0
                ORDER BY LENGTH(cs_fullname) ASC
                LIMIT ${len(words) + 1}
            """
            params = [*words, limit]
            partial_results = await conn.fetch(partial_query, *params)

            if not partial_results and len(words) > 1:
                # Try OR logic for all words
                where_clause_or = " OR ".join(like_clauses)
                partial_query = f"""
                    SELECT cs_code as code, cs_fullname as description
                    FROM m_classifier_hs1
                    WHERE {where_clause_or}
                    AND cs_code IS NOT NULL
                    AND LENGTH(cs_code) > 0
                    ORDER BY LENGTH(cs_fullname) ASC
                    LIMIT ${len(words) + 1}
                """
                params = [*words, limit]
                partial_results = await conn.fetch(partial_query, *params)

            # NEW: If still nothing, try searching for each word individually and combine results
            if (not partial_results or len(partial_results) == 0) and len(words) > 1:
                combined_results = []
                seen_codes = set()
                for w in words:
                    single_word_query = f"""
                        SELECT cs_code as code, cs_fullname as description
                        FROM m_classifier_hs1
                        WHERE LOWER(cs_fullname) LIKE '%' || $1 || '%'
                        AND cs_code IS NOT NULL
                        AND LENGTH(cs_code) > 0
                        ORDER BY LENGTH(cs_fullname) ASC
                        LIMIT $2
                    """
                    word_results = await conn.fetch(single_word_query, w, limit)
                    for row in word_results:
                        if is_valid_hs_code(row['code']) and row['code'] not in seen_codes:
                            combined_results.append({"code": row['code'], "description": row['description']})
                            seen_codes.add(row['code'])
                if combined_results:
                    results = combined_results[:limit]
                    logger.info(f"Found {len(results)} results by individual word partial match for: {query}")
            elif partial_results:
                results = [
                    {"code": row['code'], "description": row['description']}
                    for row in partial_results if is_valid_hs_code(row['code'])
                ]
                logger.info(f"Found {len(results)} results by partial match for: {query}")

    except Exception as e:
        logger.error(f"Database search error: {e}", exc_info=True)
        results = []

    finally:
        if conn:
            await conn.close()

    return results

async def quick_code_lookup(code: str) -> Optional[Dict[str, str]]:
    conn = None
    try:
        conn = await get_connection()
        # Convert to string and strip to handle both int and str inputs
        code_str = str(code).strip()
        
        result = await conn.fetchrow("""
            SELECT cs_code as code, cs_fullname as description
            FROM m_classifier_hs1
            WHERE cs_code = $1
            AND cs_code IS NOT NULL
            AND LENGTH(cs_code) > 0
        """, code_str)

        if result and is_valid_hs_code(result['code']):
            return {"code": result['code'], "description": result['description']}
        return None
    except Exception as e:
        logger.error(f"Database quick code lookup error for {code}: {e}", exc_info=True)
        return None
    finally:
        if conn:
            await conn.close() 