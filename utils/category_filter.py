#!/usr/bin/env python3
"""
Category-based filtering system for TNVED bot
Prevents wrong matches between different product categories
"""

import re
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Product category mappings with TNVED code ranges
PRODUCT_CATEGORIES = {
    "glass": {
        "keywords": ["стекло", "стеклянн", "glass", "стекол", "стекла", "листовое", "полированное", "окрашенное", "толщиной"],
        "tnved_codes": ["70"],  # Chapter 70 - Glass and glassware
        "exclude_codes": ["39", "72", "73", "76", "78", "79", "80", "81", "82", "83"],
        "description_must_contain": ["стекло", "glass", "стеклянн"]
    },
    "metal": {
        "keywords": ["метал", "сталь", "железо", "профиль", "metal", "steel", "iron"],
        "tnved_codes": ["72", "73", "76", "78", "79", "80", "81", "82", "83"],
        "exclude_codes": ["39", "70"],
        "description_must_contain": ["метал", "сталь", "железо", "metal", "steel", "iron"]
    },
    "plastic": {
        "keywords": ["пластик", "полимер", "полиэтилен", "полипропилен", "пластмасс", "полиамид", "пвх"],
        "tnved_codes": ["39"],
        "exclude_codes": ["70", "72", "73"],
        "description_must_contain": ["пластик", "полимер", "полиэтилен", "полипропилен", "пластмасс", "полиамид", "пвх"]
    },
    "textile": {
        "keywords": ["ткань", "текстиль", "хлопок", "шерсть", "fabric", "textile"],
        "tnved_codes": ["50", "51", "52", "53", "54", "55", "56", "57", "58", "59", "60", "61", "62", "63"],
        "exclude_codes": ["39", "70", "72", "73"],
        "description_must_contain": ["ткань", "текстиль", "хлопок", "шерсть", "fabric", "textile"]
    },
    "wood": {
        "keywords": ["дерев", "древес", "фанера", "wood", "timber", "lumber"],
        "tnved_codes": ["44"],
        "exclude_codes": ["39", "70", "72", "73"],
        "description_must_contain": ["дерев", "древес", "фанера", "wood", "timber", "lumber"]
    },
    "food": {
        "keywords": ["пищев", "продукт", "еда", "food", "edible"],
        "tnved_codes": ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24"],
        "exclude_codes": ["39", "70", "72", "73"],
        "description_must_contain": ["пищев", "продукт", "еда", "food", "edible"]
    }
}

def detect_query_category(query: str) -> Optional[str]:
    """
    Detect the product category from the search query
    """
    query_lower = query.lower()
    
    # Check each category
    for category, config in PRODUCT_CATEGORIES.items():
        for keyword in config["keywords"]:
            if keyword in query_lower:
                logger.info(f"Query '{query}' detected as category: {category}")
                return category
    
    return None

def filter_results_by_category(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Filter search results based on detected query category with smart fallback
    """
    if not results:
        return results
    
    query_category = detect_query_category(query)
    if not query_category:
        logger.info(f"No category detected for query: {query}")
        return results
    
    category_config = PRODUCT_CATEGORIES[query_category]
    allowed_codes = category_config["tnved_codes"]
    excluded_codes = category_config["exclude_codes"]
    must_contain = category_config["description_must_contain"]
    
    filtered_results = []
    rejected_results = []
    
    for result in results:
        code = result.get("code", "")
        description = result.get("description", "").lower()
        
        # Check if code starts with allowed prefixes
        code_allowed = False
        for allowed_prefix in allowed_codes:
            if code.startswith(allowed_prefix):
                code_allowed = True
                break
        
        # Check if code starts with excluded prefixes
        code_excluded = False
        for excluded_prefix in excluded_codes:
            if code.startswith(excluded_prefix):
                code_excluded = True
                break
        
        # Check if description contains required keywords
        desc_valid = False
        for keyword in must_contain:
            if keyword in description:
                desc_valid = True
                break
        
        # Apply filtering logic
        if code_allowed and not code_excluded and desc_valid:
            filtered_results.append(result)
            logger.info(f"✅ KEPT: {code} - {description[:50]}...")
        else:
            rejected_results.append(result)
            logger.info(f"❌ FILTERED OUT: {code} - {description[:50]}... (category mismatch)")
    
    # SMART FALLBACK: If filtering removes all results, apply relaxed filtering
    if not filtered_results and rejected_results:
        logger.warning(f"⚠️ Category filter removed all results for '{query}'. Applying relaxed filtering...")
        
        # Apply less strict filtering - only exclude obviously wrong categories
        for result in rejected_results:
            code = result.get("code", "")
            description = result.get("description", "").lower()
            
            # Only exclude clearly wrong categories
            should_exclude = False
            
            if query_category == "glass":
                # For glass queries, exclude plastics/polymers but allow uncertain codes
                if (code.startswith('39') and ('полимер' in description or 'пластик' in description or 
                    'полиамид' in description or 'силикон' in description)):
                    should_exclude = True
                elif code.startswith('47') and 'древес' in description:  # wood pulp
                    should_exclude = True
                elif code.startswith('48') and 'бумаг' in description:  # paper
                    should_exclude = True
                elif code.startswith('25') and 'графит' in description:  # graphite
                    should_exclude = True
            
            elif query_category == "metal":
                # For metal queries, exclude plastics and organic materials
                if code.startswith('39') and ('полимер' in description or 'пластик' in description):
                    should_exclude = True
                elif code.startswith('47') or code.startswith('48'):  # wood/paper
                    should_exclude = True
            
            if not should_exclude:
                filtered_results.append(result)
                logger.info(f"✓ RELAXED FILTER KEPT: {code} - {description[:50]}...")
            
            # Limit to top 5 relaxed results
            if len(filtered_results) >= 5:
                break
        
        if filtered_results:
            logger.info(f"✅ Relaxed filter rescued {len(filtered_results)} results")
        else:
            # Last resort: return top 3 original results with warning
            logger.warning(f"🔄 No suitable results after relaxed filtering, returning top 3 original results")
            filtered_results = results[:3]
    
    logger.info(f"Category filter: {len(results)} -> {len(filtered_results)} results for '{query}'")
    return filtered_results

def validate_result_relevance(result: Dict[str, Any], query: str) -> bool:
    """
    Validate if a single result is relevant to the query
    """
    query_category = detect_query_category(query)
    if not query_category:
        return True  # No category detected, allow all results
    
    category_config = PRODUCT_CATEGORIES[query_category]
    code = result.get("code", "")
    description = result.get("description", "").lower()
    
    # Check code prefix
    code_valid = False
    for allowed_prefix in category_config["tnved_codes"]:
        if code.startswith(allowed_prefix):
            code_valid = True
            break
    
    # Check description keywords
    desc_valid = False
    for keyword in category_config["description_must_contain"]:
        if keyword in description:
            desc_valid = True
            break
    
    return code_valid and desc_valid

def get_category_examples(category: str) -> List[str]:
    """
    Get example keywords for a category
    """
    if category in PRODUCT_CATEGORIES:
        return PRODUCT_CATEGORIES[category]["keywords"][:3]
    return []

def suggest_better_query(query: str, failed_results: List[Dict[str, Any]]) -> str:
    """
    Suggest a better query based on failed results
    """
    query_category = detect_query_category(query)
    if not query_category:
        return "Попробуйте использовать более конкретные термины для описания товара"
    
    examples = get_category_examples(query_category)
    if examples:
        return f"Для категории '{query_category}' попробуйте использовать ключевые слова: {', '.join(examples)}"
    
    return "Попробуйте переформулировать запрос, используя более точные технические термины" 