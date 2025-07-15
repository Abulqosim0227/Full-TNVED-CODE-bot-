import re
import unicodedata
from typing import Tuple, List, Set
import nltk
from nltk.stem.snowball import SnowballStemmer
from nltk.tokenize import word_tokenize
import pandas as pd
import logging
from transliterate import translit

logger = logging.getLogger(__name__)

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

# Initialize stemmers for different languages
stemmers = {
    'ru': SnowballStemmer('russian'),
    'en': SnowballStemmer('english')
}

# Common word variations and their base forms
WORD_VARIATIONS = {
    'майка': ['майки', 'майку', 'майкой', 'майке', 'майками', 'майкам', 'майках'],
    'футболка': ['футболки', 'футболку', 'футболкой', 'футболке', 'футболками', 'футболкам', 'футболках'],
    'рубашка': ['рубашки', 'рубашку', 'рубашкой', 'рубашке', 'рубашками', 'рубашкам', 'рубашках'],
    'брюки': ['брюк', 'брюкам', 'брюками', 'брюках'],
    'джинсы': ['джинс', 'джинсам', 'джинсами', 'джинсах'],
    'платье': ['платья', 'платью', 'платьем', 'платьями', 'платьям', 'платьях'],
    'костюм': ['костюмы', 'костюму', 'костюмом', 'костюмами', 'костюмам', 'костюмах'],
    'пиджак': ['пиджаки', 'пиджаком', 'пиджаку', 'пиджаками', 'пиджакам', 'пиджаках'],
    'куртка': ['куртки', 'куртку', 'курткой', 'куртками', 'курткам', 'куртках'],
    'пальто': ['пальто'],
    'шорты': ['шорт', 'шортам', 'шортами', 'шортах'],
    'юбка': ['юбки', 'юбку', 'юбкой', 'юбками', 'юбкам', 'юбках'],
    # Fruits/vegetables
    'слива': ['сливы', 'сливу', 'сливой', 'сливе', 'сливами', 'сливам', 'сливах'],
    'абрикос': ['абрикосы', 'абрикосу', 'абрикосом', 'абрикосами', 'абрикосам', 'абрикосах'],
    'вишня': ['вишни', 'вишню', 'вишней', 'вишне', 'вишнями', 'вишням', 'вишнях'],
    'черешня': ['черешни', 'черешню', 'черешней', 'черешне', 'черешнями', 'черешням', 'черешнях'],
    'персик': ['персики', 'персику', 'персиком', 'персиками', 'персикам', 'персиках'],
    'яблоко': ['яблоки', 'яблоку', 'яблоком', 'яблоками', 'яблокам', 'яблоках'],
    'груша': ['груши', 'грушу', 'грушей', 'груше', 'грушами', 'грушам', 'грушах'],
    'апельсин': ['апельсины', 'апельсину', 'апельсином', 'апельсинами', 'апельсинам', 'апельсинах'],
    'банан': ['бананы', 'банану', 'бананом', 'бананами', 'бананам', 'бананах'],
    'лимон': ['лимоны', 'лимону', 'лимоном', 'лимонами', 'лимонам', 'лимонах'],
    'морковь': ['моркови', 'морковью', 'морковью', 'морковями', 'морковям', 'морковях'],
    'картофель': ['картофеля', 'картофелю', 'картофелем', 'картофелями', 'картофелям', 'картофелях'],
    'огурец': ['огурцы', 'огурцу', 'огурцом', 'огурцами', 'огурцам', 'огурцах'],
    'помидор': ['помидоры', 'помидору', 'помидором', 'помидорами', 'помидорам', 'помидорах'],
    'капуста': ['капусты', 'капусту', 'капустой', 'капусте', 'капустами', 'капустам', 'капустах'],
    'лук': ['луки', 'луку', 'луком', 'луками', 'лукам', 'луках'],
    'чеснок': ['чесноки', 'чесноку', 'чесноком', 'чесноками', 'чеснокам', 'чесноках'],
    'свекла': ['свеклы', 'свеклу', 'свеклой', 'свекле', 'свеклами', 'свеклам', 'свеклах'],
    'редис': ['редисы', 'редису', 'редисом', 'редисами', 'редисам', 'редисах'],
    'арбуз': ['арбузы', 'арбузу', 'арбузом', 'арбузами', 'арбузам', 'арбузах'],
    'дыня': ['дыни', 'дыню', 'дыней', 'дыне', 'дынями', 'дыням', 'дынях'],
}

# Create reverse mapping for quick lookup
VARIATION_TO_BASE = {}
for base, variations in WORD_VARIATIONS.items():
    for var in variations:
        VARIATION_TO_BASE[var] = base
    VARIATION_TO_BASE[base] = base

def normalize_text(text: str) -> str:
    """Normalize text by removing special characters and converting to lowercase."""
    if not isinstance(text, str):
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove special characters but keep spaces and basic punctuation
    text = re.sub(r'[^\w\s.,;:!?-]', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def transliterate_text(text: str) -> str:
    """Transliterate text from Cyrillic to Latin."""
    if not isinstance(text, str):
        return ""
    
    # Define transliteration mapping
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    
    # Convert text to lowercase
    text = text.lower()
    
    # Transliterate each character
    result = ''
    for char in text:
        result += translit_map.get(char, char)
    
    return result

def lemmatize_text(text: str, lang: str = 'ru') -> str:
    """Lemmatize text using NLTK's SnowballStemmer and custom word variations."""
    if not isinstance(text, str):
        return ""
    
    # Tokenize text
    tokens = word_tokenize(text.lower())
    
    # Get appropriate stemmer
    stemmer = stemmers.get(lang, stemmers['ru'])
    
    # Stem each token
    stemmed_tokens = []
    for token in tokens:
        # First check if token is in our variations dictionary
        if token in VARIATION_TO_BASE:
            stemmed_tokens.append(VARIATION_TO_BASE[token])
        else:
            # Use stemmer for other words
            stemmed = stemmer.stem(token)
            # If stemmed word is in our variations, use its base form
            if stemmed in VARIATION_TO_BASE:
                stemmed_tokens.append(VARIATION_TO_BASE[stemmed])
            else:
                stemmed_tokens.append(stemmed)
    
    return ' '.join(stemmed_tokens)

def normalize_and_lemmatize_pipeline(text: str) -> Tuple[str, str, str]:
    """Process text through normalization and lemmatization pipeline."""
    if not isinstance(text, str):
        return "", "", ""
    
    # Normalize text
    normalized = normalize_text(text)
    
    # Transliterate
    transliterated = translit(normalized, 'ru', reversed=True)
    
    # Lemmatize
    lemmatized = lemmatize_text(normalized)
    
    return normalized, transliterated, lemmatized

def contains_valid_word(text: str) -> bool:
    """Check if text contains at least one valid word."""
    if not isinstance(text, str):
        return False
    
    # Normalize text
    normalized = normalize_text(text)
    
    # Split into words
    words = normalized.split()
    
    # Check if any word is in our variations dictionary or is a valid word
    return any(word in VARIATION_TO_BASE or len(word) > 1 for word in words)

def clean_description_for_output(description: str) -> str:
    """Clean description for output display."""
    if not isinstance(description, str):
        return ""
    
    # Remove extra whitespace
    description = re.sub(r'\s+', ' ', description)
    
    # Remove special characters but keep basic punctuation
    description = re.sub(r'[^\w\s.,;:!?-]', ' ', description)
    
    return description.strip()

STOPWORDS_RU = {
    "арт", "№", "по", "в", "с", "из", "на", "для", "и", "или", "а", "но", "не", "от", "до",
    "при", "без", "под", "над", "за", "перед", "около", "через", "между", "вопреки",
    "вследствие", "насчет", "помимо", "несмотря", "спустя", "сквозь", "благодаря",
    "согласно", "сообразно", "подобно", "вместо", "посреди", "о", "об", "обо", "к", "ко",
    "у", "из-за", "из-под", "по-над", "ооо", "ип", "зао", "пао", "оао", "итд", "тд", "пр"
}
STOPWORDS_SET = set(STOPWORDS_RU)

def clean_and_normalize_text(text: str) -> str:
    if not isinstance(text, str) or pd.isna(text):
        return ""

    text = text.strip().lower()
    text = unicodedata.normalize("NFKC", text).replace("\u200f", "").replace("\u00a0", " ")

    text = re.sub(r'\s*\d+[\d.,]*\s*(?:лет|см|кг|м|шт|дал|г|м2|mm|д|руб|%|мл|л|т|мм|копеек|см3|гр/м2|гр|м2|м)\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*(?:арт|№|производитель|код по тнвэд|состав|размер|плотность|артикул|тм|бренд|дизайн|цвет|тип нити|упаковка|вид полотна|количество нитей на 10 см|линейная плотность|ширина|длина|вес|формат)\s*[:;]?\s*.*$', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(\s*есть в коробке замерзшая вода\s*\)\s*', ' ', text, flags=re.IGNORECASE)

    text = re.sub(r'[:;,|/\\\-\(\)\[\]{}]', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    normalized_text = re.sub(r'\s+', ' ', text.strip())

    words = normalized_text.split()
    filtered_words = [word for word in words if word not in STOPWORDS_SET and len(word) > 1]
    normalized_text_filtered = ' '.join(filtered_words)

    return normalized_text_filtered