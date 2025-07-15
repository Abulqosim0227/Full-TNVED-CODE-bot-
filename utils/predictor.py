
import numpy as np
import pandas as pd
import faiss
import re
import unicodedata
from sentence_transformers import SentenceTransformer
from pathlib import Path
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import os
from fuzzywuzzy import fuzz
import asyncio
# Enhanced search system with database integration
import collections
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from functools import lru_cache
import hashlib
import gc
import psutil

from config import MODEL_NAME
from utils.text_processing import normalize_and_lemmatize_pipeline, contains_valid_word, clean_description_for_output, normalize_text, lemmatize_text, WORD_VARIATIONS

# Setup logging first
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import db_search functions with error handling
try:
    from utils.db_search import search_classifier_db, quick_code_lookup
    logger.info("Successfully imported db_search functions")
except ImportError as e:
    logger.error(f"Failed to import db_search functions: {e}")
    # Define fallback functions
    async def search_classifier_db(query: str, limit: int = 4):
        logger.error("search_classifier_db not available - using fallback")
        return []
    
    async def quick_code_lookup(code: str):
        logger.error("quick_code_lookup not available - using fallback")
        return None

# Enhanced thresholds with dynamic adjustment
SEMANTIC_THRESHOLD = 0.45
SCORE_THRESHOLD_BEST_MATCH = 0.55
SCORE_THRESHOLD_TOP_SIMILAR = 0.3
MIN_RELEVANCE_FOR_ANY_MATCH = 0.10

# Multi-stage search parameters
TOP_K_BEST_MATCH_SIMILAR = 4
TOP_K_NOT_FOUND_SUGGESTIONS = 6
EXPECTED_DIMENSION = 768

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PREPARED_DATA_PATH = DATA_DIR / "processed_data.csv"
EMBEDDING_PATH = DATA_DIR / "embeddings.npy"

# Common misspellings and corrections
COMMON_CORRECTIONS = {
    # Clothing
    'майка': ['майки', 'маика', 'майке', 'маики'],
    'футболка': ['футболки', 'футболке', 'фудболка'],
    'рубашка': ['рубашки', 'рубашке', 'рубажка'],
    'брюки': ['брюк', 'брюках', 'бруки'],
    'джинсы': ['джинс', 'джинсах', 'жинсы'],
    
    # Fruits/Vegetables
    'слива': ['сливы', 'слив', 'сливи', 'сливе'],
    'яблоко': ['яблоки', 'яблок', 'яблако'],
    'апельсин': ['апельсины', 'апелсин', 'апельсинов'],
    'банан': ['бананы', 'банани', 'бананов'],
    'морковь': ['моркови', 'морков', 'марковь'],
    'картофель': ['картофеля', 'картошка', 'картофел'],
    'огурец': ['огурцы', 'огурци', 'огурцов'],
    'помидор': ['помидоры', 'помидори', 'томат', 'томаты'],
    
    # Common typos
    'свежий': ['свежие', 'свежее', 'свижий', 'свежый'],
    'новый': ['новые', 'новий', 'новая'],
    'хлопок': ['хлопка', 'хлопак', 'хлопковый'],
    'шерсть': ['шерсти', 'шерст', 'шерстяной'],
}

# Multi-language stopwords
STOPWORDS = {
    'ru': set(['и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 
               'она', 'так', 'его', 'но', 'да', 'ты', 'к', 'у', 'же', 'вы', 'за', 'бы', 'по', 
               'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще', 'нет', 'о', 'из', 
               'ему', 'теперь', 'когда', 'даже', 'ну', 'вдруг', 'ли', 'если', 'уже', 'или', 
               'ни', 'быть', 'был', 'него', 'до', 'вас', 'нибудь', 'опять', 'уж', 'вам', 'ведь']),
    'uz': set(['va', 'yoki', 'lekin', 'agar', 'chunki', 'uchun', 'bilan', 'da', 'ham', 'esa', 
               'bu', 'u', 'shu', 'ana', 'mana', 'ular', 'biz', 'siz', 'men', 'sen']),
    'en': set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 
               'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
               'after', 'above', 'below', 'between', 'under', 'again', 'further', 'then'])
}

def expand_query_with_corrections(query: str) -> List[str]:
    """
    Expand query with common corrections and clean administrative terms
    """
    if not query or len(query.strip()) < 2:
        return [query]
    
    query_clean = query.strip().lower()
    expanded_queries = []
    
    # Administrative/legal terms that should be removed or deprioritized
    administrative_terms = [
        'критерий происхождения', 'критерии происхождения',
        'товарное происхождение', 'страна происхождения',
        'сертификат происхождения', 'декларация происхождения',
        'подтверждение происхождения', 'документ происхождения',
        'гост', 'ту ', 'тн вэд', 'код тн вэд', 'классификация',
        'таможенное оформление', 'таможенная процедура',
        'импорт', 'экспорт', 'ввоз', 'вывоз',
        'сертификат качества', 'сертификат соответствия',
        'санитарно-эпидемиологическое заключение',
        'фитосанитарный сертификат', 'ветеринарный сертификат'
    ]
    
    # Clean query by removing administrative terms
    cleaned_query = query_clean
    for term in administrative_terms:
        # Remove the term and clean up extra spaces
        cleaned_query = cleaned_query.replace(term, ' ')
    
    # Clean up multiple spaces and normalize
    cleaned_query = ' '.join(cleaned_query.split()).strip()
    
    # Product name synonyms and corrections
    product_synonyms = {
        'помидоры': 'томаты',
        'помидор': 'томаты',
        'картошка': 'картофель',
        'капуста белокочанная': 'капуста',
        'лук репчатый': 'лук',
        'лук-репка': 'лук',
        'морковка': 'морковь',
        'свёкла': 'свекла',
        'огурчики': 'огурцы',
        'яблочки': 'яблоки',
        'грушки': 'груши'
    }
    
    # Apply product synonyms
    normalized_query = cleaned_query
    for synonym, canonical in product_synonyms.items():
        if synonym in normalized_query:
            normalized_query = normalized_query.replace(synonym, canonical)
    
    # Extract core product terms (focus on main product, ignore modifiers)
    words = normalized_query.split()
    
    # Prioritize product-specific words over general descriptors
    priority_words = []
    descriptor_words = []
    
    product_indicators = [
        'томаты', 'помидоры', 'картофель', 'капуста', 'лук', 'морковь',
        'огурцы', 'свекла', 'яблоки', 'груши', 'виноград', 'изюм',
        'бананы', 'апельсины', 'лимоны', 'мандарины', 'орех', 'арахис'
    ]
    
    for word in words:
        if any(product in word for product in product_indicators):
            priority_words.append(word)
        elif word in ['свежий', 'свежие', 'сушеный', 'сушеные', 'охлажденный', 'охлажденные']:
            descriptor_words.append(word)
    
    # Create focused query with main product terms first
    if priority_words:
        focused_query = ' '.join(priority_words + descriptor_words)
        if focused_query != normalized_query:
            expanded_queries.append(focused_query)
    
    # Add the normalized query
    if normalized_query and normalized_query != query_clean:
        expanded_queries.append(normalized_query)
    
    # Add original query as fallback
    expanded_queries.append(query_clean)
    
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for q in expanded_queries:
        if q and q not in seen and len(q.strip()) > 1:
            seen.add(q)
            result.append(q.strip())
    
    return result if result else [query]

def remove_stopwords(text: str, lang: str = 'ru') -> str:
    """Remove stopwords from text based on language"""
    words = text.lower().split()
    stopwords = STOPWORDS.get(lang, STOPWORDS['ru'])
    filtered_words = [word for word in words if word not in stopwords and len(word) > 1]
    return ' '.join(filtered_words)

# Cache for search results
def _get_cache_key(query: str, lang: str) -> str:
    """Generate cache key for query"""
    return hashlib.md5(f"{query}:{lang}".encode()).hexdigest()

# LRU cache for frequent queries
_search_cache = {}
_cache_max_size = 200  # Reduced from 1000 to 200
_last_cache_cleanup = time.time()

def cleanup_memory_cache():
    """Clean up search cache and force garbage collection"""
    global _search_cache, _last_cache_cleanup
    
    current_time = time.time()
    # Clean cache every 15 minutes
    if current_time - _last_cache_cleanup > 900:  # 15 minutes
        old_size = len(_search_cache)
        # Keep only the most recent 50 cache entries
        if len(_search_cache) > 50:
            # Convert to list of items with timestamps
            cache_items = list(_search_cache.items())
            # Keep only last 50 items (most recent)
            _search_cache = dict(cache_items[-50:])
        
        # Force garbage collection
        collected = gc.collect()
        _last_cache_cleanup = current_time
        
        logger.info(f"🧹 Memory cache cleaned: {old_size} -> {len(_search_cache)} entries, collected {collected} objects")

def get_memory_usage():
    """Get current memory usage in MB"""
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except:
        return 0

def get_cached_result(query: str, lang: str) -> Optional[dict]:
    """Get cached search result if available"""
    cleanup_memory_cache()  # Clean cache periodically
    cache_key = _get_cache_key(query, lang)
    if cache_key in _search_cache:
        logger.info(f"Cache hit for query: {query}")
        return _search_cache[cache_key].copy()
    return None

def cache_result(query: str, lang: str, result: dict):
    """Cache search result with memory optimization"""
    cache_key = _get_cache_key(query, lang)
    
    # Simple LRU: remove oldest if cache is full
    if len(_search_cache) >= _cache_max_size:
        # Remove first (oldest) item
        oldest_key = next(iter(_search_cache))
        del _search_cache[oldest_key]
    
    _search_cache[cache_key] = result.copy()

# Enhanced relevance calculation with more sophisticated features
def calculate_enhanced_relevance_score(
    query_norm: str, 
    query_lemmas_joined: str, 
    desc_norm: str, 
    desc_lemmas_joined: str, 
    semantic_similarity: float,
    query_length: int,
    desc_length: int,
    exact_matches: int = 0,
    product_code: str = ""
) -> float:
    """
    Enhanced relevance calculation with multiple factors and category awareness
    """
    query_norm = str(query_norm)
    query_lemmas_joined = str(query_lemmas_joined)
    desc_norm = str(desc_norm)
    desc_lemmas_joined = str(desc_lemmas_joined)

    # Category-based filtering and boosting
    category_boost = 0.0
    category_penalty = 0.0
    
    # Detect product category from query
    query_lower = query_norm.lower()
    code_prefix = str(product_code)[:4] if product_code else ""
    
    # Enhanced keywords for better categorization
    food_keywords = ['виноград', 'изюм', 'орех', 'арахис', 'нут', 'сушен', 'свеж', 'фрукт', 'овощ', 'ягод']
    meat_keywords = ['мясо', 'свин', 'говяд', 'птиц', 'жир', 'сало', 'бекон']
    vegetable_keywords = ['томат', 'помидор', 'картофел', 'капуст', 'лук', 'морков', 'огурц', 'свекл', 'овощ']
    fruit_keywords = ['виноград', 'изюм', 'яблок', 'груш', 'банан', 'апельсин', 'лимон', 'мандарин', 'фрукт']
    
    # FIXED: Enhanced metal/construction keywords
    metal_keywords = ['метал', 'стал', 'профил', 'железо', 'алюмин', 'оцинков', 'гипсокартон', 'строительный', 'конструкци', 'балка', 'уголок', 'швеллер', 'арматур']
    construction_keywords = ['гипсокартон', 'строительный', 'строительн', 'конструкци', 'каркас', 'монтаж', 'профиль', 'профили']
    
    textile_keywords = ['ткан', 'хлопок', 'шерст', 'син', 'волокн', 'пряж']
    
    is_food_query = any(keyword in query_lower for keyword in food_keywords)
    is_meat_query = any(keyword in query_lower for keyword in meat_keywords)
    is_vegetable_query = any(keyword in query_lower for keyword in vegetable_keywords)
    is_fruit_query = any(keyword in query_lower for keyword in fruit_keywords)
    
    # FIXED: Enhanced metal/construction detection
    is_metal_query = any(keyword in query_lower for keyword in metal_keywords)
    is_construction_query = any(keyword in query_lower for keyword in construction_keywords)
    is_textile_query = any(keyword in query_lower for keyword in textile_keywords)
    
    # Category code mappings (first 2-4 digits)
    food_codes = ['08', '07', '04', '12', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24']  # Food chapters
    vegetable_codes = ['07']  # Vegetables chapter
    fruit_codes = ['08']  # Fruit and nuts chapter
    meat_codes = ['02', '03', '16']  # Meat, fish, meat preparations
    metal_codes = ['72', '73', '74', '75', '76', '78', '79', '80', '81']  # Base metals
    construction_codes = ['72', '73']  # Iron and steel - main construction materials
    textile_codes = ['50', '51', '52', '53', '54', '55', '56', '57', '58', '59', '60', '61', '62', '63']  # Textiles
    
    # Apply category-based logic with more specific vegetable/fruit handling
    if is_vegetable_query:
        # For vegetable queries (tomatoes, potatoes, etc.)
        if any(code_prefix.startswith(vc) for vc in vegetable_codes):
            category_boost = 0.4  # Strong boost for vegetable codes
        elif any(code_prefix.startswith(fc) for fc in fruit_codes):
            category_penalty = 0.6  # Heavy penalty for fruit codes when searching vegetables
        elif any(code_prefix.startswith(mc) for mc in meat_codes):
            category_penalty = 0.7  # Very heavy penalty for meat codes
    
    elif is_fruit_query:
        # For fruit queries (grapes, apples, etc.)
        if any(code_prefix.startswith(fc) for fc in fruit_codes):
            category_boost = 0.4  # Strong boost for fruit codes
        elif any(code_prefix.startswith(vc) for vc in vegetable_codes):
            category_penalty = 0.3  # Moderate penalty for vegetable codes when searching fruits
        elif any(code_prefix.startswith(mc) for mc in meat_codes):
            category_penalty = 0.7  # Very heavy penalty for meat codes
    
    elif is_food_query and not is_meat_query:
        # For general food queries (except meat), boost food codes and penalize meat codes heavily
        if any(code_prefix.startswith(fc) for fc in food_codes):
            category_boost = 0.3  # Increased boost for correct food codes
        elif any(code_prefix.startswith(mc) for mc in meat_codes):
            category_penalty = 0.6  # Increased penalty for meat codes in non-meat food queries
    
    elif is_meat_query:
        # For meat queries, boost meat codes
        if any(code_prefix.startswith(mc) for mc in meat_codes):
            category_boost = 0.25
        elif any(code_prefix.startswith(fc) for fc in food_codes):
            category_boost = 0.1  # Smaller boost for other food codes
    
    elif is_metal_query:
        # For metal queries, boost metal codes
        if any(code_prefix.startswith(mc) for mc in metal_codes):
            category_boost = 0.25
        else:
            category_penalty = 0.3  # Increased penalty for non-metal codes
    
    elif is_construction_query:
        # For construction queries, boost construction codes
        if any(code_prefix.startswith(cc) for cc in construction_codes):
            category_boost = 0.25
        else:
            category_penalty = 0.3  # Increased penalty for non-construction codes
    
    elif is_textile_query:
        # For textile queries, boost textile codes
        if any(code_prefix.startswith(tc) for tc in textile_codes):
            category_boost = 0.25
        else:
            category_penalty = 0.3  # Increased penalty

    # ENHANCED: Special handling for combined construction + metal queries
    if is_construction_query or (is_metal_query and any(word in query_lower for word in ['профил', 'гипсокартон', 'строительн'])):
        # Strong boost for construction metal codes (72xx, 73xx)
        if any(code_prefix.startswith(cc) for cc in construction_codes):
            category_boost = max(category_boost, 0.4)  # Strong boost for construction metals
        elif any(code_prefix.startswith(mc) for mc in metal_codes):
            category_boost = max(category_boost, 0.2)  # Moderate boost for other metals
        else:
            # Heavy penalty for non-metal codes in construction queries
            category_penalty = max(category_penalty, 0.5)

    # Specific fixes for common misclassifications
    if 'виноград' in query_lower or 'изюм' in query_lower:
        if code_prefix.startswith('08'):  # Correct fruit codes
            category_boost = 0.4  # Strong boost for fruit codes
        elif code_prefix.startswith('02'):  # Wrong meat codes
            category_penalty = 0.8  # Very heavy penalty for meat codes
    
    # Specific fixes for tomato misclassifications
    if 'томат' in query_lower or 'помидор' in query_lower:
        if code_prefix.startswith('0702'):  # Correct tomato codes
            category_boost = 0.5  # Very strong boost for exact tomato codes
        elif code_prefix.startswith('0707'):  # Wrong cucumber codes
            category_penalty = 0.5  # Heavy penalty for cucumbers when searching tomatoes
        elif code_prefix.startswith('07'):  # Other vegetable codes
            category_boost = 0.1  # Small boost for other vegetable codes
        elif code_prefix.startswith('08'):  # Wrong fruit codes
            category_penalty = 0.7  # Heavy penalty for fruit codes
        elif code_prefix.startswith('02'):  # Wrong meat codes
            category_penalty = 0.8  # Very heavy penalty
            
    # Specific fixes for cucumber misclassifications  
    if 'огурец' in query_lower or 'корнишон' in query_lower:
        if code_prefix.startswith('0707'):  # Correct cucumber codes
            category_boost = 0.5  # Very strong boost for exact cucumber codes
        elif code_prefix.startswith('0702'):  # Wrong tomato codes
            category_penalty = 0.5  # Heavy penalty for tomatoes when searching cucumbers
        elif code_prefix.startswith('07'):  # Other vegetable codes
            category_boost = 0.1  # Small boost for other vegetable codes

    # ENHANCED: Specific fixes for construction materials
    if 'гипсокартон' in query_lower or ('профил' in query_lower and 'оцинков' in query_lower):
        if code_prefix.startswith('72') or code_prefix.startswith('73'):  # Construction steel codes
            category_boost = max(category_boost, 0.5)  # Very strong boost for steel construction codes
        elif code_prefix.startswith('07'):  # Agriculture codes - wrong!
            category_penalty = max(category_penalty, 0.8)  # Very heavy penalty for agriculture when looking for construction
        elif code_prefix.startswith('08'):  # Fruit codes - wrong!
            category_penalty = max(category_penalty, 0.8)  # Very heavy penalty for fruits when looking for construction
    
    # Additional penalties for obviously wrong categories
    if any(food_word in query_lower for food_word in ['виноград', 'изюм', 'фрукт', 'ягод', 'орех']):
        if code_prefix.startswith('02'):  # Meat codes for fruit queries
            category_penalty = max(category_penalty, 0.7)  # Ensure heavy penalty
    
    if any(veg_word in query_lower for veg_word in ['томат', 'помидор', 'картофел', 'капуст', 'овощ']):
        if code_prefix.startswith('08'):  # Fruit codes for vegetable queries
            category_penalty = max(category_penalty, 0.6)  # Heavy penalty for fruits when searching vegetables
        elif code_prefix.startswith('02'):  # Meat codes for vegetable queries
            category_penalty = max(category_penalty, 0.8)  # Very heavy penalty

    # Dynamic weights based on query characteristics
    if query_length <= 2:  # Short queries - prioritize exact matches
        weight_semantic = 0.60
        weight_fuzzy = 0.25
        weight_word_overlap = 0.15
    elif query_length <= 4:  # Medium queries - balanced approach
        weight_semantic = 0.70
        weight_fuzzy = 0.15
        weight_word_overlap = 0.15
    else:  # Long queries - prioritize semantic understanding
        weight_semantic = 0.75
        weight_fuzzy = 0.10
        weight_word_overlap = 0.15

    # Enhanced fuzzy matching with multiple algorithms
    fuzzy_ratio = fuzz.ratio(query_norm, desc_norm) / 100.0
    fuzzy_partial = fuzz.partial_ratio(query_norm, desc_norm) / 100.0
    fuzzy_token_sort = fuzz.token_sort_ratio(query_norm, desc_norm) / 100.0
    fuzzy_token_set = fuzz.token_set_ratio(query_norm, desc_norm) / 100.0
    
    # Best fuzzy score
    best_fuzzy = max(fuzzy_ratio, fuzzy_partial, fuzzy_token_sort, fuzzy_token_set)

    # Enhanced word overlap with positional awareness
    query_lemmas_set = set(query_lemmas_joined.split())
    desc_lemmas_set = set(desc_lemmas_joined.split())
    
    # CRITICAL FIX: Weighted word overlap - give much higher weight to product terms
    product_terms = {'томат', 'помидор', 'огурец', 'корнишон', 'картофел', 'капуст', 'лук', 'морков', 'свекл', 'арбуз', 'дын', 'яблок', 'груш', 'виноград', 'изюм', 'банан', 'апельсин', 'лимон', 'мандарин', 'орех', 'арахис'}
    
    # Calculate weighted overlap
    overlap = query_lemmas_set.intersection(desc_lemmas_set)
    
    # Separate product terms from descriptors
    product_overlap = overlap.intersection(product_terms)
    descriptor_overlap = overlap - product_terms
    
    # If query contains product terms, heavily weight them
    query_product_terms = query_lemmas_set.intersection(product_terms)
    
    if query_product_terms:
        # For queries with product terms, heavily penalize missing product terms
        if not product_overlap:
            # No product terms match - this should be heavily penalized
            word_overlap_score = 0.0
        else:
            # Calculate weighted score: product terms = 0.8, descriptors = 0.2
            product_weight = len(product_overlap) / len(query_product_terms) * 0.8
            descriptor_weight = len(descriptor_overlap) / max(len(query_lemmas_set - product_terms), 1) * 0.2
            word_overlap_score = product_weight + descriptor_weight
    else:
        # No product terms in query, use regular overlap
        word_overlap_score = len(overlap) / max(len(query_lemmas_set), 1.0)
    
    # Bonus for exact phrase matches
    phrase_bonus = 0.0
    if len(query_lemmas_joined) > 3 and query_lemmas_joined in desc_lemmas_joined:
        phrase_bonus = 0.2
    
    # Position-based bonus (important words at beginning)
    position_bonus = 0.0
    query_words = query_lemmas_joined.split()
    desc_words = desc_lemmas_joined.split()
    if query_words and desc_words:
        for i, word in enumerate(query_words[:3]):  # First 3 words are most important
            if word in desc_words[:5]:  # Found in first 5 words of description
                position_bonus += 0.1 * (1.0 - i * 0.2)  # Diminishing returns
    
    # Length penalty for very long descriptions (they might be too generic)
    length_penalty = 0.0
    if desc_length > 100:
        length_penalty = min(0.1, (desc_length - 100) / 500)

    # Combine all scores
    combined_score = (
        max(0.0, semantic_similarity) * weight_semantic +
        best_fuzzy * weight_fuzzy +
        (word_overlap_score + phrase_bonus + position_bonus) * weight_word_overlap
    )

    # Apply category boost/penalty first
    combined_score += category_boost
    
    # Apply penalties
    penalty = length_penalty + category_penalty
    
    # Penalty for low semantic similarity
    if semantic_similarity < SEMANTIC_THRESHOLD - 0.35:
        penalty += 0.25

    # Penalty for unmatched query terms in multi-word queries
    if len(query_lemmas_set) > 1:
        unmatched_query_lemmas_ratio = len(query_lemmas_set - desc_lemmas_set) / len(query_lemmas_set)
        if unmatched_query_lemmas_ratio > 0.5:
            penalty += unmatched_query_lemmas_ratio * 0.2

    final_score = max(0.0, min(combined_score - penalty, 1.0))
    return final_score

class EnhancedProductSearchSystem:
    """Enhanced product search with multiple search strategies - Database only version"""
    
    _instance: Optional['EnhancedProductSearchSystem'] = None
    _initialized = False
    _embedding_model: Optional[SentenceTransformer] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            logger.info("Initializing Enhanced Product Search System...")
            self.model = None
            self.index = None
            self.index_to_data = {}
            self.df_system = None
            self.tfidf_vectorizer = None
            self.tfidf_matrix = None
            
            try:
                # Initialize in async context - will be called from async methods
                self._initialized = False  # Will be set to True after async init
            except Exception as e:
                logger.error(f"Failed to initialize Enhanced ProductSearchSystem: {e}")
                self._initialized = False

    async def _async_init(self):
        """Async initialization - loads data from database"""
        if self._initialized:
            return
        
        try:
            init_start = time.time()
            
            # Load model with CUDA error handling
            logger.info(f"Loading model: {MODEL_NAME}")
            if self._embedding_model is None:
                try:
                    self._embedding_model = SentenceTransformer(MODEL_NAME)
                    # Force CPU mode if CUDA is problematic
                    import torch
                    if torch.cuda.is_available():
                        try:
                            # Test CUDA with a simple operation
                            test_tensor = torch.tensor([1.0]).cuda()
                            test_result = test_tensor * 2
                            logger.info("CUDA is available and working")
                        except Exception as cuda_error:
                            logger.warning(f"CUDA test failed, forcing CPU mode: {cuda_error}")
                            self._embedding_model = self._embedding_model.to('cpu')
                    else:
                        logger.info("CUDA not available, using CPU")
                        self._embedding_model = self._embedding_model.to('cpu')
                except Exception as model_error:
                    logger.error(f"Error loading model: {model_error}")
                    # Try to reload with explicit CPU mode
                    import torch
                    self._embedding_model = SentenceTransformer(MODEL_NAME, device='cpu')
                    logger.info("Model loaded with explicit CPU mode")
            self.model = self._embedding_model
            
            # Load data from database instead of CSV
            logger.info("Loading data from PostgreSQL database...")
            await self._load_data_from_database()
            
            if len(self.df_system) == 0:
                logger.error("No data loaded from database!")
                return
            
            logger.info(f"Loaded {len(self.df_system)} entries from database.")
            
            # Build FAISS index from database data
            await self._build_faiss_index()
            
            # Build TF-IDF index
            logger.info("Building TF-IDF index with language-specific stopwords...")
            await self._build_tfidf_index()
            
            init_time = time.time() - init_start
            logger.info(f"Enhanced search system initialized in {init_time:.4f}s")
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to initialize enhanced search system: {e}", exc_info=True)
            self._initialized = False

    async def _load_data_from_database(self):
        """Load all HS codes and descriptions from PostgreSQL database"""
        conn = None
        try:
            from utils.db import get_connection
            conn = await get_connection()
            
            # Load all valid HS codes from database
            rows = await conn.fetch("""
                SELECT cs_code as code, cs_fullname as description
                FROM m_classifier_hs1
                WHERE cs_code IS NOT NULL 
                AND LENGTH(TRIM(cs_code)) >= 6
                AND cs_fullname IS NOT NULL
                AND LENGTH(TRIM(cs_fullname)) > 10
                ORDER BY cs_code
            """)
            
            if not rows:
                logger.error("No data found in m_classifier_hs1 table!")
                self.df_system = pd.DataFrame(columns=['code', 'description'])
                return
            
            # Convert to pandas DataFrame
            data = []
            for row in rows:
                # Ensure code is 10 digits
                code = str(row['code']).strip().zfill(10)
                description = str(row['description']).strip()
                
                if len(code) == 10 and len(description) > 10:
                    data.append({
                        'code': code,
                        'description': description
                    })
            
            self.df_system = pd.DataFrame(data)
            logger.info(f"Successfully loaded {len(self.df_system)} valid entries from database")
            
        except Exception as e:
            logger.error(f"Error loading data from database: {e}", exc_info=True)
            self.df_system = pd.DataFrame(columns=['code', 'description'])
        finally:
            if conn:
                await conn.close()

    async def _build_faiss_index(self):
        """Build FAISS index from database descriptions"""
        try:
            logger.info("Building FAISS index...")
            
            if len(self.df_system) == 0:
                logger.error("No data to build FAISS index!")
                return
            
            # Prepare descriptions for embedding
            descriptions = []
            for idx, row in self.df_system.iterrows():
                # Normalize and prepare description for embedding
                desc_normalized = normalize_text(row['description'])
                desc_lemmatized = lemmatize_text(desc_normalized)
                desc_clean = remove_stopwords(desc_lemmatized, 'ru')
                
                descriptions.append(desc_clean)
                
                # Store mapping for quick lookup
                self.index_to_data[idx] = {
                    "code": row['code'],
                    "description": row['description'],
                    "normalized_description": desc_normalized,
                    "lemmatized_description": desc_clean
                }
            
            # Generate embeddings using safe encoding
            logger.info(f"Generating embeddings for {len(descriptions)} descriptions...")
            try:
                embeddings = self.model.encode(
                    descriptions,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False  # Disable to avoid CUDA issues
                )
            except Exception as e:
                logger.warning(f"Batch encoding failed: {e}, falling back to individual encoding")
                # Fallback: encode individually with safe method
                embeddings = []
                for i, desc in enumerate(descriptions):
                    if i % 100 == 0:
                        logger.info(f"Encoding description {i+1}/{len(descriptions)}")
                    try:
                        emb = self._safe_encode(desc)
                        embeddings.append(emb)
                    except Exception as desc_error:
                        logger.error(f"Failed to encode description {i}: {desc_error}")
                        # Use zero vector as fallback
                        embeddings.append(np.zeros(768, dtype=np.float32))
                
                if embeddings:
                    embeddings = np.vstack(embeddings)
                else:
                    logger.error("No embeddings generated!")
                    return
            
            # Build FAISS index
            dimension = embeddings.shape[1]
            logger.info(f"Building FAISS index with dimension {dimension}")
            
            # Use IndexFlatIP for cosine similarity (since embeddings are normalized)
            self.index = faiss.IndexFlatIP(dimension)
            self.index.add(embeddings.astype("float32"))
            
            logger.info(f"FAISS index built successfully with {self.index.ntotal} vectors")
            
        except Exception as e:
            logger.error(f"Error building FAISS index: {e}", exc_info=True)

    async def _build_tfidf_index(self):
        """Build TF-IDF index from database descriptions"""
        try:
            if len(self.df_system) == 0:
                return
            
            # Prepare descriptions for TF-IDF
            descriptions = []
            for _, row in self.df_system.iterrows():
                desc_normalized = normalize_text(row['description'])
                desc_lemmatized = lemmatize_text(desc_normalized)
                desc_clean = remove_stopwords(desc_lemmatized, 'ru')
                descriptions.append(desc_clean)
            
            # Build TF-IDF vectorizer
            self.tfidf_vectorizer = TfidfVectorizer(
                max_features=10000,
                ngram_range=(1, 3),
                min_df=2,
                max_df=0.95,
                analyzer='word'
            )
            
            self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(descriptions)
            logger.info(f"TF-IDF index built with {self.tfidf_matrix.shape[0]} documents and {self.tfidf_matrix.shape[1]} features")
            
        except Exception as e:
            logger.error(f"Error building TF-IDF index: {e}", exc_info=True)

    def _tfidf_search(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        """Perform TF-IDF based search"""
        if not self.tfidf_vectorizer or self.tfidf_matrix is None:
            return []
        
        try:
            # Normalize query for TF-IDF
            query_norm = normalize_text(query)
            query_lemmas = lemmatize_text(query_norm)
            
            # Remove stopwords from query
            query_cleaned = remove_stopwords(query_lemmas, 'ru')
            
            # Transform query
            query_tfidf = self.tfidf_vectorizer.transform([query_cleaned])
            
            # Calculate similarities
            similarities = cosine_similarity(query_tfidf, self.tfidf_matrix).flatten()
            
            # Get top results
            top_indices = similarities.argsort()[-top_k:][::-1]
            results = [(idx, similarities[idx]) for idx in top_indices if similarities[idx] > 0.1]
            
            return results
        except Exception as e:
            logger.error(f"TF-IDF search error: {e}")
            return []

    def _safe_encode(self, text: str, max_retries: int = 2):
        """Safely encode text with CUDA error handling and CPU fallback"""
        for attempt in range(max_retries + 1):
            try:
                # Try encoding with current device
                embedding = self.model.encode(
                    text,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False  # Disable progress bar to avoid CUDA issues
                )
                return embedding.astype("float32")
                
            except Exception as e:
                logger.warning(f"Encoding attempt {attempt + 1} failed: {e}")
                
                if "CUDA" in str(e) or "cuda" in str(e):
                    logger.warning("CUDA error detected during encoding, switching to CPU")
                    try:
                        # Force model to CPU
                        import torch
                        self.model = self.model.to('cpu')
                        # Clear CUDA cache
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        logger.info("Model moved to CPU successfully")
                        
                        # Retry with CPU
                        if attempt < max_retries:
                            continue
                        else:
                            # Last attempt with explicit CPU settings
                            embedding = self.model.encode(
                                text,
                                convert_to_numpy=True,
                                normalize_embeddings=True,
                                show_progress_bar=False,
                                device='cpu'
                            )
                            return embedding.astype("float32")
                            
                    except Exception as cpu_error:
                        logger.error(f"CPU fallback failed: {cpu_error}")
                        if attempt == max_retries:
                            raise e
                else:
                    # Non-CUDA error
                    if attempt == max_retries:
                        raise e
        
        # Should not reach here
        raise RuntimeError("All encoding attempts failed")

    def _exact_match_search(self, query: str) -> List[Dict[str, Any]]:
        """Search for exact matches in product codes and descriptions"""
        exact_matches = []
        query_norm = normalize_text(query).lower()
        
        # Search by code
        if query.isdigit() and len(query) == 10:
            matches = self.df_system[self.df_system['code'].astype(str) == query]
            for _, row in matches.iterrows():
                exact_matches.append({
                    'code': row['code'],
                    'description': row['description'],
                    'relevance_score': 1.0,
                    'match_type': 'exact_code'
                })
        
        # Search for exact phrase matches in descriptions
        for idx, row in self.df_system.iterrows():
            desc_norm = normalize_text(row['description']).lower()
            if query_norm in desc_norm:
                # Calculate position-based score
                position = desc_norm.find(query_norm)
                position_score = 1.0 - (position / max(len(desc_norm), 1)) * 0.3
                
                exact_matches.append({
                    'code': row['code'],
                    'description': row['description'],
                    'relevance_score': min(1.0, 0.9 + position_score * 0.1),
                    'match_type': 'exact_phrase'
                })
        
        return exact_matches

    async def _validate_with_database(self, codes: List[str]) -> Dict[str, bool]:
        """Validate codes against the database m_classifier_hs1 table"""
        validation_results = {}
        
        for code in codes:
            try:
                # Use quick_code_lookup to check if code exists in DB
                db_result = await quick_code_lookup(code)
                validation_results[code] = db_result is not None
            except Exception as e:
                logger.error(f"Error validating code {code}: {e}")
                validation_results[code] = False
        
        return validation_results

    async def _enrich_with_database_info(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich results with fresh data from database"""
        enriched_results = []
        
        for result in results:
            code = result.get('code')
            if code:
                try:
                    # Get fresh data from database
                    db_data = await quick_code_lookup(code)
                    if db_data:
                        # Compare description lengths
                        csv_description = result.get('description', '')
                        db_description = db_data.get('description', '')
                        
                        # Keep the original CSV description as backup
                        result['description_from_csv'] = csv_description
                        result['description_from_db'] = db_description
                        
                        # Use the longer, more complete description
                        # CSV usually has the full hierarchical path
                        if len(csv_description) > len(db_description) * 2:
                            # CSV description is significantly longer, use it
                            result['description'] = csv_description
                            result['description_source'] = 'csv_full'
                        else:
                            # Use DB description but check if it's too short
                            if len(db_description) < 50 and len(csv_description) > len(db_description):
                                # DB description is too short, use CSV
                                result['description'] = csv_description
                                result['description_source'] = 'csv_preferred'
                            else:
                                # DB description is adequate
                                result['description'] = db_description
                                result['description_source'] = 'database'
                        
                        result['validated'] = True
                    else:
                        # Code not found in database - mark as invalid
                        result['validated'] = False
                        result['validation_warning'] = 'Code not found in official database'
                except Exception as e:
                    logger.error(f"Error enriching code {code}: {e}")
                    result['validated'] = False
                    result['validation_error'] = str(e)
            
            enriched_results.append(result)
        
        # Filter out invalid codes unless no valid ones exist
        valid_results = [r for r in enriched_results if r.get('validated', False)]
        if valid_results:
            return valid_results
        else:
            # Return all results with warnings if no valid ones
            return enriched_results

    async def enhanced_predict_code(self, query: str, lang: str = "ru") -> Dict[str, Any]:
        """Enhanced prediction with multi-stage search and database validation"""
        predict_start_time = time.time()

        # Check cache first
        cached_result = get_cached_result(query, lang)
        if cached_result:
            cached_result['from_cache'] = True
            cached_result['processing_time_ms'] = 1  # Virtually instant
            return cached_result

        if not self._initialized:
            return {
                "status": "system_error", 
                "message": "System not initialized",
                "best_match": None, 
                "top_similar": [], 
                "confidence": 0.0
            }

        if not query or not query.strip():
            return {
                "status": "error", 
                "message": "Empty query",
                "best_match": None, 
                "top_similar": [], 
                "confidence": 0.0
            }

        query_clean = query.strip()
        
        # Expand query with common corrections
        expanded_queries = expand_query_with_corrections(query_clean)
        
        all_results = []
        
        for expanded_query in expanded_queries:
            query_norm, query_translit, query_lemmas_joined = normalize_and_lemmatize_pipeline(expanded_query)
            
            # Remove stopwords for better matching
            query_lemmas_no_stop = remove_stopwords(query_lemmas_joined, lang)
            
            logger.info(f"Processing query: '{expanded_query}' -> '{query_lemmas_no_stop}'")

            # Input validation
            if not contains_valid_word(query_norm):
                continue

            # Stage 1: Exact matches
            exact_matches = self._exact_match_search(expanded_query)
            if exact_matches:
                logger.info(f"Found {len(exact_matches)} exact matches for '{expanded_query}'")
                all_results.extend(exact_matches)

            # Stage 2: Hybrid search (TF-IDF + Semantic)
            try:
                # TF-IDF search
                tfidf_results = self._tfidf_search(query_lemmas_no_stop, top_k=100)
                
                # Semantic search with safe encoding
                query_embedding = self._safe_encode(query_lemmas_no_stop)
                if query_embedding is None:
                    logger.error(f"Failed to encode query: {query_lemmas_no_stop}")
                    continue
                query_embedding = query_embedding.reshape(1, -1)

                search_k = min(200, self.index.ntotal)
                D, I = self.index.search(query_embedding, k=search_k)
                semantic_results = [(idx, score) for score, idx in zip(D[0], I[0]) if idx != -1]

                # Combine and score results
                candidate_matches = {}
                query_length = len(query_lemmas_no_stop.split())
                
                # Process TF-IDF results
                for idx, tfidf_score in tfidf_results:
                    if idx in self.index_to_data:
                        item_data = self.index_to_data[idx]
                        # Find corresponding semantic score
                        semantic_score = 0.0
                        for sem_idx, sem_score in semantic_results:
                            if sem_idx == idx:
                                semantic_score = sem_score
                                break
                        
                        # Calculate enhanced relevance
                        relevance_score = calculate_enhanced_relevance_score(
                            query_norm=query_norm,
                            query_lemmas_joined=query_lemmas_no_stop,
                            desc_norm=item_data["normalized_description"],
                            desc_lemmas_joined=item_data["lemmatized_description"],
                            semantic_similarity=semantic_score,
                            query_length=query_length,
                            desc_length=len(item_data["description"]),
                            product_code=item_data["code"]
                        )
                        
                        # Boost score if found in both TF-IDF and semantic
                        if semantic_score > 0.3:
                            relevance_score *= 1.1  # 10% boost for hybrid matches
                        
                        # Additional boost if this is a corrected query match
                        if expanded_query != query_clean:
                            relevance_score *= 0.95  # Slight penalty for corrections
                        
                        candidate_matches[idx] = {
                            "code": item_data["code"],
                            "description": item_data["description"],
                            "relevance_score": relevance_score,
                            "semantic_sim": float(semantic_score),
                            "tfidf_score": tfidf_score,
                            "search_type": "hybrid"
                        }

                # Process semantic-only results
                for idx, semantic_score in semantic_results:
                    if idx not in candidate_matches and idx in self.index_to_data:
                        item_data = self.index_to_data[idx]
                        
                        relevance_score = calculate_enhanced_relevance_score(
                            query_norm=query_norm,
                            query_lemmas_joined=query_lemmas_no_stop,
                            desc_norm=item_data["normalized_description"],
                            desc_lemmas_joined=item_data["lemmatized_description"],
                            semantic_similarity=semantic_score,
                            query_length=query_length,
                            desc_length=len(item_data["description"]),
                            product_code=item_data["code"]
                        )
                        
                        candidate_matches[idx] = {
                            "code": item_data["code"],
                            "description": item_data["description"],
                            "relevance_score": relevance_score,
                            "semantic_sim": float(semantic_score),
                            "tfidf_score": 0.0,
                            "search_type": "semantic"
                        }

                all_results.extend(candidate_matches.values())

            except Exception as e:
                logger.error(f"Error during search for '{expanded_query}': {e}")

        # Deduplicate and sort all results
        seen_codes = set()
        unique_results = []
        for result in all_results:
            if result['code'] not in seen_codes:
                seen_codes.add(result['code'])
                unique_results.append(result)
        
        # Sort by relevance score
        scored_matches = sorted(unique_results, key=lambda x: x["relevance_score"], reverse=True)
        
        # IMPORTANT: Validate and enrich results with database
        if scored_matches:
            logger.info(f"Validating {len(scored_matches)} results against database...")
            scored_matches = await self._enrich_with_database_info(scored_matches[:20])  # Validate top 20
            logger.info(f"After validation: {len(scored_matches)} valid results")
        
        # Determine result quality
        best_match = None
        top_similar_list = []
        status = "not_found"
        confidence = 0.0
        message = "No matches found"

        if scored_matches:
            highest_score = scored_matches[0]["relevance_score"]
            
            if highest_score >= SCORE_THRESHOLD_BEST_MATCH:
                best_match = scored_matches[0]
                confidence = highest_score
                
                if confidence >= 0.85:
                    status = "high_confidence"
                    message = "High confidence match found"
                elif confidence >= 0.70:
                    status = "medium_confidence"
                    message = "Medium confidence match found"
                else:
                    status = "low_confidence"
                    message = "Low confidence match found"
                
                # Add similar matches
                seen_codes = {best_match["code"]}
                for item in scored_matches[1:]:
                    if (item["relevance_score"] >= SCORE_THRESHOLD_TOP_SIMILAR and 
                        item["code"] not in seen_codes):
                        top_similar_list.append(item)
                        seen_codes.add(item["code"])
                    if len(top_similar_list) >= TOP_K_BEST_MATCH_SIMILAR:
                        break
            
            elif highest_score >= MIN_RELEVANCE_FOR_ANY_MATCH:
                status = "not_found_with_suggestions"
                message = "No exact match, but here are some suggestions"
                
                seen_codes = set()
                for item in scored_matches:
                    if (item["relevance_score"] >= MIN_RELEVANCE_FOR_ANY_MATCH and 
                        item["code"] not in seen_codes):
                        top_similar_list.append(item)
                        seen_codes.add(item["code"])
                    if len(top_similar_list) >= TOP_K_NOT_FOUND_SUGGESTIONS:
                        break

        # Clean descriptions
        if best_match:
            best_match["description"] = clean_description_for_output(best_match["description"])
        for item in top_similar_list:
            item["description"] = clean_description_for_output(item["description"])

        result = {
            "status": status,
            "message": message,
            "best_match": best_match,
            "top_similar": top_similar_list,
            "confidence": confidence,
            "query_processed": query_clean,
            "processing_time_ms": (time.time() - predict_start_time) * 1000,
            "total_candidates": len(scored_matches),
            "expanded_queries": expanded_queries if len(expanded_queries) > 1 else None,
            "database_validated": True  # All results are now validated
        }

        # Cache the result
        cache_result(query_clean, lang, result)

        logger.info(f"Query: '{query_clean}' -> Status: {status}, Confidence: {confidence:.2f}, "
                   f"Candidates: {len(scored_matches)}")

        return result

    def cleanup_memory(self):
        """Clean up memory used by the search system"""
        try:
            memory_before = get_memory_usage()
            objects_collected = 0
            
            # Force garbage collection
            objects_collected += gc.collect()
            
            # Clear CUDA cache if available
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("🧹 CUDA cache cleared")
            except:
                pass
            
            # Clear TF-IDF cache if it gets too large
            if hasattr(self, 'tfidf_matrix') and self.tfidf_matrix is not None:
                # If TF-IDF matrix is very large, consider clearing it
                if hasattr(self.tfidf_matrix, 'shape') and self.tfidf_matrix.shape[0] > 50000:
                    logger.warning("TF-IDF matrix is large, consider rebuilding with reduced features")
            
            # Clean up search cache
            cleanup_memory_cache()
            
            # Force another garbage collection
            objects_collected += gc.collect()
            
            memory_after = get_memory_usage()
            memory_saved = memory_before - memory_after
            
            logger.info(f"🧹 Memory cleanup completed: {memory_saved:.1f}MB saved, {objects_collected} objects collected")
            
        except Exception as e:
            logger.error(f"Error during memory cleanup: {e}")

    def get_memory_stats(self):
        """Get detailed memory statistics"""
        try:
            stats = {
                'total_memory_mb': get_memory_usage(),
                'cache_size': len(_search_cache),
                'system_initialized': self._initialized,
                'model_loaded': self.model is not None,
                'index_loaded': self.index is not None,
                'data_loaded': self.df_system is not None and len(self.df_system) > 0,
                'tfidf_loaded': self.tfidf_matrix is not None
            }
            
            if self.df_system is not None:
                stats['data_entries'] = len(self.df_system)
            
            if self.index is not None:
                stats['index_vectors'] = self.index.ntotal
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting memory stats: {e}")
            return {'error': str(e)}

# Global instance management
_enhanced_prediction_system_instance: Optional['EnhancedProductSearchSystem'] = None

def get_enhanced_prediction_system() -> Optional['EnhancedProductSearchSystem']:
    """Get the enhanced prediction system instance (async init required)"""
    global _enhanced_prediction_system_instance
    if _enhanced_prediction_system_instance is None:
        logger.info("Creating Enhanced ProductSearchSystem instance...")
        try:
            _enhanced_prediction_system_instance = EnhancedProductSearchSystem()
            logger.info("Enhanced ProductSearchSystem instance created (async init required)")
        except Exception as e:
            logger.critical(f"Failed to create Enhanced ProductSearchSystem: {e}", exc_info=True)
            _enhanced_prediction_system_instance = None

    return _enhanced_prediction_system_instance

async def enhanced_search_product(query: str, lang: str = "ru") -> dict:
    """Main entry point for enhanced product search"""
    predictor = get_enhanced_prediction_system()
    if not predictor or not predictor._initialized:
        return {
            "status": "system_error",
            "message": "System not available",
            "best_match": None,
            "top_similar": [],
            "confidence": 0.0,
            "query_processed": query
        }
    return await predictor.enhanced_predict_code(query, lang)

# Backward compatibility functions - keep original function names
async def search_product(query: str, lang: str = "ru") -> dict:
    """Original search_product function for backward compatibility"""
    return await enhanced_search_product(query, lang)

def _description_relevance(query, description, product_code=""):
    """Enhanced description relevance with category awareness for fallback compatibility"""
    from utils.text_processing import normalize_text
    q = normalize_text(query)
    d = normalize_text(description)
    
    # Basic fuzzy match and weighted word overlap
    fuzzy = fuzz.partial_ratio(q, d) / 100.0
    q_words = set(q.split())
    d_words = set(d.split())
    
    # CRITICAL FIX: Weighted word overlap for fallback compatibility
    product_terms = {'томат', 'помидор', 'огурец', 'корнишон', 'картофел', 'капуст', 'лук', 'морков', 'свекл', 'арбуз', 'дын', 'яблок', 'груш', 'виноград', 'изюм', 'банан', 'апельсин', 'лимон', 'мандарин', 'орех', 'арахис'}
    
    overlap_words = q_words & d_words
    product_overlap = overlap_words.intersection(product_terms)
    query_product_terms = q_words.intersection(product_terms)
    
    if query_product_terms:
        # For queries with product terms, heavily penalize missing product terms
        if not product_overlap:
            overlap = 0.0  # No product terms match
        else:
            # Calculate weighted overlap: product terms = 0.8, descriptors = 0.2
            product_weight = len(product_overlap) / len(query_product_terms) * 0.8
            descriptor_overlap = overlap_words - product_terms
            descriptor_weight = len(descriptor_overlap) / max(len(q_words - product_terms), 1) * 0.2
            overlap = product_weight + descriptor_weight
    else:
        # No product terms in query, use regular overlap
        overlap = len(overlap_words) / max(len(q_words), 1)
    
    # Base score
    base_score = 0.7 * fuzzy + 0.3 * overlap
    
    # Apply category-based adjustments
    query_lower = q.lower()
    code_prefix = str(product_code)[:4] if product_code else ""
    
    category_adjustment = 0.0
    
    # Food vs meat vs vegetable vs fruit category logic
    food_keywords = ['виноград', 'изюм', 'орех', 'арахис', 'нут', 'сушен', 'свеж', 'фрукт', 'овощ', 'ягод']
    meat_keywords = ['мясо', 'свин', 'говяд', 'птиц', 'жир', 'сало', 'бекон']
    vegetable_keywords = ['томат', 'помидор', 'картофел', 'капуст', 'лук', 'морков', 'огурц', 'свекл', 'овощ']
    fruit_keywords = ['виноград', 'изюм', 'яблок', 'груш', 'банан', 'апельсин', 'лимон', 'мандарин', 'фрукт']
    
    is_food_query = any(keyword in query_lower for keyword in food_keywords)
    is_meat_query = any(keyword in query_lower for keyword in meat_keywords)
    is_vegetable_query = any(keyword in query_lower for keyword in vegetable_keywords)
    is_fruit_query = any(keyword in query_lower for keyword in fruit_keywords)
    
    # Enhanced category-based adjustments
    if is_vegetable_query:
        # For vegetable queries (tomatoes, potatoes, etc.)
        if code_prefix.startswith('07'):  # Vegetable codes
            category_adjustment = 0.3   # Strong boost
        elif code_prefix.startswith('08'):  # Fruit codes
            category_adjustment = -0.5  # Heavy penalty for fruits when searching vegetables
        elif code_prefix.startswith('02'):  # Meat codes
            category_adjustment = -0.6  # Very heavy penalty
    
    elif is_fruit_query:
        # For fruit queries (grapes, apples, etc.)
        if code_prefix.startswith('08'):  # Fruit codes
            category_adjustment = 0.3   # Strong boost
        elif code_prefix.startswith('07'):  # Vegetable codes
            category_adjustment = -0.2  # Moderate penalty
        elif code_prefix.startswith('02'):  # Meat codes
            category_adjustment = -0.6  # Very heavy penalty
    
    elif is_food_query and not is_meat_query:
        # For general food queries (except meat)
        if code_prefix.startswith('02'):  # Meat codes for food queries
            category_adjustment = -0.4  # Heavy penalty
        elif code_prefix.startswith('08') or code_prefix.startswith('07'):  # Food codes
            category_adjustment = 0.2   # Boost
    
    # Specific enhancements for common products
    if 'виноград' in query_lower or 'изюм' in query_lower:
        if code_prefix.startswith('08'):  # Fruit codes
            category_adjustment = max(category_adjustment, 0.3)  # Strong boost
        elif code_prefix.startswith('02'):  # Meat codes
            category_adjustment = min(category_adjustment, -0.5)  # Very heavy penalty
    
    # Specific enhancements for tomato queries
    if 'томат' in query_lower or 'помидор' in query_lower:
        if code_prefix.startswith('0702'):  # Exact tomato codes
            category_adjustment = max(category_adjustment, 0.4)  # Very strong boost
        elif code_prefix.startswith('07'):  # Other vegetable codes
            category_adjustment = max(category_adjustment, 0.2)  # Good boost
        elif code_prefix.startswith('08'):  # Fruit codes
            category_adjustment = min(category_adjustment, -0.4)  # Heavy penalty
        elif code_prefix.startswith('02'):  # Meat codes
            category_adjustment = min(category_adjustment, -0.5)  # Very heavy penalty
    
    final_score = max(0.0, min(base_score + category_adjustment, 1.0))
    return final_score

def _query_tokens(query):
    """Original helper function for backward compatibility"""
    norm = normalize_text(query)
    lem = lemmatize_text(norm)
    return set(norm.split()), set(lem.split())

def extract_product_name(description):
    """Original helper function for backward compatibility"""
    # Extract last segment after '->' or ':'
    if '->' in description:
        return description.split('->')[-1].strip().lower()
    elif ':' in description:
        return description.split(':')[-1].strip().lower()
    return description.strip().lower()

def product_segments(description):
    """Original helper function for backward compatibility"""
    # Split by '->' and ':', strip and lower each segment
    segments = [seg.strip().lower() for seg in description.replace(':', '->').split('->')]
    return segments

def is_good_match(query, segments):
    """Original helper function for backward compatibility"""
    # Tokenize the query once
    norm_query_tokens = set(normalize_text(query).split())
    lemma_query_tokens = set(lemmatize_text(normalize_text(query)).split())

    # If the query is empty after normalization, it can't be a good match
    if not norm_query_tokens:
        return False

    # Collect all tokens from all segments (excluding generic ones)
    all_seg_norm_tokens = set()
    all_seg_lem_tokens = set()
    for seg in segments:
        if seg.strip() in ['прочие', 'прочее']:
            continue
        all_seg_norm_tokens.update(normalize_text(seg).split())
        all_seg_lem_tokens.update(lemmatize_text(normalize_text(seg)).split())

    # 1. Strong match: all query tokens are present anywhere in the description
    if norm_query_tokens.issubset(all_seg_norm_tokens) or lemma_query_tokens.issubset(all_seg_lem_tokens):
        return True

    # 2. Fallback: at least one query token is present anywhere in the description
    if norm_query_tokens & all_seg_norm_tokens or lemma_query_tokens & all_seg_lem_tokens:
        return True

    return False

async def search_by_sentence_words(query, limit=5):
    """Original search_by_sentence_words function for backward compatibility"""
    from utils.text_processing import normalize_text, lemmatize_text

    # Normalize and lemmatize the query, remove stopwords (if any)
    norm_query = normalize_text(query)
    words = [w for w in norm_query.split() if len(w) > 2]  # skip very short words
    if not words:
        return []

    results_by_code = collections.defaultdict(lambda: {'code': '', 'description': '', 'match_count': 0})

    for word in words:
        try:
            from utils.db_search import search_classifier_db as db_search_func
            word_results = await db_search_func(word, limit=20)
        except (ImportError, NameError) as e:
            logger.error(f"Error importing/using search_classifier_db in search_by_sentence_words: {e}")
            word_results = []
        
        for item in word_results:
            code = item['code']
            if not results_by_code[code]['code']:
                results_by_code[code]['code'] = code
                results_by_code[code]['description'] = item['description']
            results_by_code[code]['match_count'] += 1

    sorted_results = sorted(results_by_code.values(), key=lambda x: (-x['match_count'], x['code']))
    return sorted_results[:limit]

def extract_key_product_terms(query: str):
    """Extract key product terms from query for better search results"""
    query_lower = query.lower()
    
    # For glass queries, create specific search terms
    if 'стекло' in query_lower or 'glass' in query_lower:
        glass_terms = ['стекло']
        
        if 'листовое' in query_lower or 'листов' in query_lower:
            glass_terms.append('стекло листовое')
            
        if 'полированное' in query_lower or 'полирован' in query_lower:
            glass_terms.append('стекло полированное')
            glass_terms.append('полированное стекло')
            
        if 'окрашенное' in query_lower or 'окрашен' in query_lower:
            glass_terms.append('стекло окрашенное')
            
        return glass_terms
    
    # For metal queries
    if any(word in query_lower for word in ['металл', 'сталь', 'профиль', 'metal', 'steel']):
        metal_terms = []
        if 'металл' in query_lower or 'metal' in query_lower:
            metal_terms.append('металл')
        if 'сталь' in query_lower or 'steel' in query_lower:
            metal_terms.append('сталь')
        if 'профиль' in query_lower:
            metal_terms.append('профиль металлический')
        return metal_terms or ['металл']
    
    return [query]

async def enhanced_db_search(query: str, limit: int = 10):
    """Enhanced database search that finds correct codes by searching key terms"""
    logger.info(f"🔍 Enhanced search for: {query}")
    
    # Extract key terms
    key_terms = extract_key_product_terms(query)
    logger.info(f"🎯 Extracted key terms: {key_terms}")
    
    all_results = []
    seen_codes = set()
    
    # Search for each key term
    for term in key_terms:
        try:
            term_results = await search_classifier_db(term, limit=20)
            for result in term_results:
                code = result.get('code', '')
                if code not in seen_codes:
                    seen_codes.add(code)
                    result['search_term'] = term
                    all_results.append(result)
        except Exception as e:
            logger.warning(f"Error searching for term '{term}': {e}")
    
    # If no results from key terms, fallback to original query
    if not all_results:
        logger.info("No results from key terms, using original query")
        try:
            all_results = await search_classifier_db(query, limit=limit)
        except Exception as e:
            logger.error(f"Error in fallback search: {e}")
            return []
    
    # Prioritize results based on query type
    if any('стекло' in term for term in key_terms):
        # For glass queries, prioritize 70xxx codes
        glass_results = [r for r in all_results if str(r.get('code', '')).startswith('70')]
        other_results = [r for r in all_results if not str(r.get('code', '')).startswith('70')]
        logger.info(f"Glass search: found {len(glass_results)} glass codes, {len(other_results)} other codes")
        return (glass_results + other_results)[:limit]
    
    elif any(word in query.lower() for word in ['металл', 'сталь', 'профиль']):
        # For metal queries, prioritize 72xxx, 73xxx codes
        metal_results = [r for r in all_results if str(r.get('code', '')).startswith(('72', '73'))]
        other_results = [r for r in all_results if not str(r.get('code', '')).startswith(('72', '73'))]
        logger.info(f"Metal search: found {len(metal_results)} metal codes, {len(other_results)} other codes")
        return (metal_results + other_results)[:limit]
    
    return all_results[:limit]

async def smart_search(query: str, lang: str = "ru", limit: int = 5) -> dict:
    """Enhanced smart_search with database-only architecture and category filtering"""
    # Import category filter
    try:
        from utils.category_filter import filter_results_by_category, validate_result_relevance
        category_filter_available = True
    except ImportError:
        logger.warning("Category filter not available")
        category_filter_available = False
    
    # Get enhanced search system and ensure initialization
    predictor = get_enhanced_prediction_system()
    if predictor:
        # Ensure database initialization is complete
        await predictor._async_init()
        
        if predictor._initialized:
            # First try the enhanced search
            enhanced_result = await enhanced_search_product(query, lang)
            
            # If enhanced search found good results, return them
            if enhanced_result.get('status') in ['high_confidence', 'medium_confidence']:
                # Convert to smart_search format
                results = []
                if enhanced_result.get('best_match'):
                    results.append({
                        'code': enhanced_result['best_match']['code'],
                        'description': enhanced_result['best_match']['description'],
                        'desc_score': enhanced_result['best_match']['relevance_score']
                    })
                
                for item in enhanced_result.get('top_similar', []):
                    results.append({
                        'code': item['code'],
                        'description': item['description'],
                        'desc_score': item['relevance_score']
                    })
                
                # Apply category filter if available
                if category_filter_available:
                    original_count = len(results)
                    results = filter_results_by_category(results, query)
                    if original_count > 0 and len(results) == 0:
                        logger.warning(f"Category filter removed all results for query: {query}")
                        # Fall through to database search
                    else:
                        return {
                            'status': 'ok',
                            'results': results[:limit],
                            'query': query,
                            'source': 'enhanced_search_filtered'
                        }
                else:
                    return {
                        'status': 'ok',
                        'results': results[:limit],
                        'query': query,
                        'source': 'enhanced_search'
                    }
    
    # Use enhanced database search for better results
    try:
        enhanced_results = await enhanced_db_search(query, limit=20)
        logger.info(f"Enhanced search found {len(enhanced_results)} results")
        
        if enhanced_results:
            # Add relevance scores
            for result in enhanced_results:
                result['desc_score'] = _description_relevance(query, result.get('description', ''), result.get('code', ''))
            
            # Sort by relevance score
            ranked_results = sorted(enhanced_results, key=lambda x: x.get('desc_score', 0), reverse=True)
            
            # Apply category filter if available
            if category_filter_available:
                original_count = len(ranked_results)
                filtered_results = filter_results_by_category(ranked_results, query)
                logger.info(f"Category filter applied to enhanced results: {original_count} -> {len(filtered_results)}")
                
                # If category filter didn't remove everything, use filtered results
                if filtered_results:
                    return {
                        'status': 'ok',
                        'results': filtered_results[:limit],
                        'query': query,
                        'source': 'enhanced_search_filtered'
                    }
                else:
                    # If category filter removed everything, use top results with warning
                    logger.warning(f"Category filter removed all enhanced results, using top {limit} with warning")
                    return {
                        'status': 'ok', 
                        'results': ranked_results[:limit],
                        'query': query,
                        'source': 'enhanced_search_warning'
                    }
            else:
                return {
                    'status': 'ok',
                    'results': ranked_results[:limit],
                    'query': query,
                    'source': 'enhanced_search'
                }
    except Exception as e:
        logger.error(f"Error in enhanced search: {e}")
    
    # Fallback to original logic if enhanced search fails
    try:
        from utils.db_search import search_classifier_db as db_search_func
        db_results = await db_search_func(query, limit=100)
    except (ImportError, NameError) as e:
        logger.error(f"Error importing/using search_classifier_db: {e}")
        db_results = []

    text_matches = []
    if db_results:
        ten_digit_codes = [r for r in db_results if len(str(r.get('code', ''))) == 10]
        for code_data in ten_digit_codes:
            description = code_data.get('description', '')
            segments = product_segments(description)
            if is_good_match(query, segments):
                text_matches.append(code_data)

    if text_matches:
        for c in text_matches:
            c['desc_score'] = _description_relevance(query, c.get('description', ''), c.get('code', ''))
        ranked_matches = sorted(text_matches, key=lambda x: x.get('desc_score', 0), reverse=True)
        
        # Apply category filter if available
        if category_filter_available:
            original_count = len(ranked_matches)
            ranked_matches = filter_results_by_category(ranked_matches, query)
            logger.info(f"Category filter applied to fallback results: {original_count} -> {len(ranked_matches)}")
        
        return {
            'status': 'ok',
            'results': ranked_matches[:limit],
            'query': query,
            'source': 'fallback_filtered' if category_filter_available else 'fallback'
        }

    # Product name detection (original logic)
    norm_query = normalize_text(query)
    query_tokens = set(norm_query.split())
    is_product_name = False
    
    for base, forms in WORD_VARIATIONS.items():
        all_forms = set([base] + forms)
        if query_tokens & all_forms:
            is_product_name = True
            break
    
    if not is_product_name and len(query_tokens) == 1:
        for base, forms in WORD_VARIATIONS.items():
            if list(query_tokens)[0] == base or list(query_tokens)[0] in forms:
                is_product_name = True
                break

    if is_product_name:
        return {
            'status': 'not_found',
            'results': [],
            'query': query,
            'message': 'Нет результатов по вашему запросу. Проверьте формулировку или обратитесь к специалисту.'
        }

    # Final fallback - keyword search
    if not text_matches:
        keyword_results = await search_by_sentence_words(query, limit=limit)
        if keyword_results:
            for c in keyword_results:
                c['desc_score'] = c['match_count']
            
            # Apply category filter if available
            if category_filter_available:
                original_count = len(keyword_results)
                keyword_results = filter_results_by_category(keyword_results, query)
                logger.info(f"Category filter applied to keyword results: {original_count} -> {len(keyword_results)}")
            
            return {
                'status': 'ok',
                'results': keyword_results,
                'query': query,
                'source': 'keyword_fallback_filtered' if category_filter_available else 'keyword_fallback'
            }
    
    return {
        'status': 'not_found',
        'results': [],
        'query': query,
        'message': 'Нет результатов по вашему запросу. Проверьте формулировку или обратитесь к специалисту.'
    }