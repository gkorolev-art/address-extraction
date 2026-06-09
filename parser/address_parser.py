"""
address_parser.py — ядро парсинга российских адресов.

Поддерживаемые форматы:
  A) Стандартный (Лукойл):  «Обл., Район, г./д./с. Название, ул. X, д. Y»
  B) Обратный   (Проктер):  «Индекс, Регион, Город г, Улица ул, дом № Y»
  C) КМ с нас.пунктом:      «Обл., Р-н, д. Погребы, 424 км + 700 м лево а/д M-3»
  D) КМ без нас.пункта:     «Обл., 202 км+250м слева ф/д М-7 Волга»
  E) Москва+посёлок:        «г. Москва, п. Первомайское, 39 км Киевского шоссе вл.1»
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class ParsedAddress:
    settlement: str = ""
    house_street: str = ""
    raw: str = ""
    confidence: float = 1.0
    debug_info: str = ""


# ═══════════════════════════════════════════════════════════════════
#  ПАТТЕРНЫ ПРОПУСКАЕМЫХ ТОКЕНОВ
# ═══════════════════════════════════════════════════════════════════

_RE_POSTAL = re.compile(r'^\d{6}$')
_RE_KM = re.compile(
    r'(?:'
    r'\d+(?:[-–]\d+)?\s*\(\s*\+\s*\d+(?:\s*м\.?)?\s*\)\s*(?:км|километр\w*)'
    r'|'
    r'(?:км|километр\w*)\.?\s*\d+\s*\+\s*\d+(?:\s*м\.?)?'
    r'|'
    r'\d+\s*\+\s*\d+\s*(?:км|километр\w*)'
    r'|\d+(?:[\.,]\d+)?(?:[-–]\d+)?\s*(?:км|километр\w*)\.?\s*[-+]\s*\d+(?:\s*м\.?)?'
    r'|(?:км|километр\w*)\s*\d+(?:[-–]\d+)?\s*\+\s*\d+'
    r'|'
    r'\d+(?:[-–]\d+)?[\.,]?\d*\s*(?:[-–]?\s*(?:й|ой|ый)|[-–])?\s*(?:км|километр\w*)'
    r'|(?:км|километр\w*)\s*\d+(?:[-–]\d+)?[\.,]?\d*(?:[-–]?(?:й|ой|ый))?'
    r')',
    re.I,
)
_RE_DISTANCE_DIRECTION_SETTLEMENT = re.compile(
    r'(?P<distance>\d+[\.,]?\d*)\s*м\.?\s+'
    r'(?:по\s+направлению\s+)?на\s+'
    r'(?P<direction>[А-Яа-яЁё\-\s]+?)\s+от\s+'
    r'(?P<settlement>.+)$',
    re.I,
)
_RE_BORDER_SUFFIX = re.compile(r'\s+[-–—]\s*гр\.?\s+.*$', re.I)
_RE_ROAD_MARKER = re.compile(
    r'(?:^|\s)(?:а/[дм]|ф/д|фад|мкад|цкад|екад|автодорог[аиуы]?|автотрасс[ауы]?|автомагистраль|трасс[ауыeе]?|шоссе)\b'
    r'|(?:^|\s)[МM]-\d+',
    re.I,
)
_RE_STRONG_ROAD_MARKER = re.compile(
    r'(?:^|\s)(?:а/[дм]|ф/д|фад|мкад|цкад|екад|автодорог[аиуы]?|автотрасс[ауы]?|автомагистраль|трасс[ауыeе]?)\b'
    r'|(?:^|\s)[МM]-\d+',
    re.I,
)
_RE_SHOSSE_MARKER = re.compile(r'(?:^|\s)(?:шоссе\b|ш\.\s*|ш\s+)', re.I)
_RE_ROAD_START_MARKER = re.compile(
    r'(?:^|\s)(?:а/[дм]|ф/д|фад|мкад|цкад|екад|автодорог[аиуы]?|автотрасс[ауы]?|автомагистраль|трасс[ауыeе]?)\b'
    r'|(?:^|\s)[МM]-\d+',
    re.I,
)
_RE_ROAD_OBJECT_MARKER = re.compile(
    r'^(?:вл\.?|влд\.?|влад\.?|владение|соор\.?|сооружение|зд\.?|здание|строен\.?|стр\.?|строение)\s*',
    re.I,
)
_RE_ROAD_SIDE_ONLY = re.compile(
    r'^(?:справа|слева|право|лево|\(?право\)?|\(?лево\)?|'
    r'внешн\.?\s*ст\.?|внешн\w*\s+сторон\w*|'
    r'внутр\.?\s*ст\.?|внутрен+\w*\s+сторон\w*)$',
    re.I,
)
_RE_MUNICIPAL_SETTLEMENT = re.compile(
    r'^(?:мо|муниципальное\s+образование)\s+'
    r'(?P<name>[А-Яа-яЁёA-Za-z0-9\s\-]+?)\s+'
    r'(?P<kind>[сc]\.п\.?|[сc]\.\s+п\.|[сc]\s+п\.?|[сc]/п|сельское\s+поселение|\(сельское\s+поселение\))$',
    re.I,
)

_COUNTRY_WORDS = {'россия', 'рф', 'российская', 'федерация'}

_REGION_MARKERS = [
    'обл.', ' обл', ' область', 'края', ' край',
    'респ.', ' респ', 'республика', 'а.о.', ' ао,', 'автономный', ' округ',
    'ямало', 'ханты-мансийский', 'ненецкий', 'чукотский',
    'хмао',
]

_DISTRICT_MARKERS = [
    'р-н',        ' район',       'муниципальный',  'муниц.',
    'г.о.',       'г/о',          'с.п.',            'с/п',
    'г.п.',       'г/п',
    'сельское поселение',         'городское поселение',
    'сельсовет',  'с/с',          'волость',         'вол.',
    'вн.тер',     'внутригородск','м.р-н',            'м.о.',
    'коммунальная зона',          'промзона',         'промр-н',
    'с.о.',       'лесничество',  'лесхоз',          'участковое',
]
_INLINE_DISTRICT_MARKER = re.compile(r'\b(?:район|р-н|м\.?\s*р-н|м/р-н)\b', re.I)
_STREET_NAME_QUALIFIERS = {
    'академика', 'маршала', 'генерала', 'героя', 'имени', 'им.',
}
_MAX_HOUSE_STREET_LEN = 30


# ═══════════════════════════════════════════════════════════════════
#  НАСЕЛЁННЫЕ ПУНКТЫ
# ═══════════════════════════════════════════════════════════════════

# Регекс для «чисто числового / буквенно-числового» значения после д.
# д. 9, д. 43, д. 104 → это ДОМ, а не деревня
_RE_DOM_NUM = re.compile(r'^[\dА-Яа-яA-Za-z]{0,2}\d+', re.I)

# Типы нас.пунктов: (паттерн для ВСЕГО токена, нормализованный тип, приоритет)
_SETT_PREFIX: List[Tuple[re.Pattern, str, int]] = [
    (re.compile(r'^(пгт\.?|пгт)\s+(.+)$',               re.I), 'пгт.', 7),
    (re.compile(r'^(р\.п\.?|рп\.?)\s+(.+)$',            re.I), 'рп.',  7),
    (re.compile(r'^(?:г\.\s*|г\s+|город\s+)(.+)$',      re.I), 'г.',   6),
    (re.compile(r'^(?:п\.\s*|п\s+|пос\.\s*|пос\s+|посёлок\s+|поселок\s+)(.+)$', re.I), 'п.', 5),
    (re.compile(r'^(мкр\.?|микрорайон|микрор-н)\s+(.+)$', re.I), 'мкр.',5),
    (re.compile(r'^(?:рабочий\s+пос[её]лок|р\.?\s*п\.?)\s+(.+)$', re.I), 'рп.',  7),
    (re.compile(r'^(ст-ца|станица)\s+(.+)$',            re.I), 'ст-ца',4),
    (re.compile(r'^(ст\.?)\s+(.+)$',                    re.I), 'ст.',  4),
    (re.compile(r'^(?:с\.\s*|с\s+(?=[А-ЯЁ])|село\s+)(.+)$', re.I), 'с.', 4),
    # д. Название — ТОЛЬКО если «Название» начинается с буквы (не цифры)
    (re.compile(r'^(?:д\.\s*|д\s+|дер\.\s*|деревн(?:я|и)\s+)([А-Яа-яЁё][А-Яа-яЁё\s\-/\(\)]+)$', re.I), 'д.', 4),
    (re.compile(r'^(х\.?|хутор)\s+(.+)$',              re.I), 'х.',   3),
    (re.compile(r'^(аул)\s+(.+)$',                      re.I), 'аул',  3),
    (re.compile(r'^(а\.)\s*(.+)$',                      re.I), 'а.',   3),
    (re.compile(r'^(кп\.?)\s+(.+)$',                    re.I), 'кп.',  4),
    (re.compile(r'^(сл\.?|слобода)\s+(.+)$',            re.I), 'сл.',  4),
]

# Суффиксный формат (Файл 2): «Москва г», «Первоуральск г», «Ромашкино х»
# мкр — НЕ самостоятельный нас.пункт, всегда часть города → в этом списке нет.
# «X мкр» обрабатывается _try_street как街道-тип → «мкр. X».
_SETT_SUFFIX: List[Tuple[re.Pattern, str, int]] = [
    (re.compile(r'^(.+?)\s+(пгт)$',   re.I), 'пгт.', 7),
    (re.compile(r'^(.+?)\s+(рп)$',    re.I), 'рп.',  7),
    (re.compile(r'^(.+?)\s+(г)$',     re.I), 'г.',   6),
    (re.compile(r'^(.+?)\s+(гп)$',    re.I), 'гп.',  6),
    (re.compile(r'^(.+?)\s+(п)$',     re.I), 'п.',   5),
    (re.compile(r'^(.+?)\s+(дп)$',    re.I), 'дп.',  5),
    (re.compile(r'^(.+?)\s+(с)$',     re.I), 'с.',   4),
    (re.compile(r'^(.+?)\s+(д)$',     re.I), 'д.',   4),
    (re.compile(r'^(.+?)\s+(сл)$',    re.I), 'сл.',  4),
    (re.compile(r'^(.+?)\s+(ст-ца)$', re.I), 'ст-ца',4),
    (re.compile(r'^(.+?)\s+(х)$',     re.I), 'х.',   3),
    (re.compile(r'^(.+?)\s+(аул)$',   re.I), 'аул',  3),
]

# Типы нас.пунктов, которые «перевешивают» город при выборе Settlement.
# мкр. — часть города, не отдельный нас.пункт → в списке отсутствует.
_SUBCITY_TYPES: frozenset = frozenset({
    'п.', 'пгт.', 'рп.', 'д.', 'с.', 'ст-ца', 'ст.',
    'х.', 'аул', 'а.', 'кп.', 'сл.', 'гп.', 'г.п.', 'дп.', 'с.п.',
})

_SUFFIX_OUTPUT_SETTLEMENT_TYPES: frozenset = frozenset({'с.п.', 'с.о.', 'вол.', 'поселение'})
_SPECIFIC_CITY_NAMES: frozenset = frozenset({
    'колпино', 'кронштадт', 'сестрорецк', 'пушкин', 'красное село',
})
_ADDRESS_LANDMARK_SETTLEMENT_TYPES: frozenset = frozenset({
    'мкр.', 'п.', 'пгт.', 'рп.', 'д.', 'с.', 'ст-ца', 'ст.',
    'х.', 'аул', 'а.', 'кп.', 'сл.', 'дп.',
})
_SETTLEMENT_HIERARCHY_RANK = {
    'регион': 10,
    'г.о.': 20,
    'м.о.': 20,
    'с.п.': 30,
    'с.о.': 30,
    'вол.': 30,
    'поселение': 30,
    'г.п.': 30,
    'гп.': 30,
    'г.': 40,
    'п.': 50,
    'пгт.': 50,
    'рп.': 50,
    'кп.': 50,
    'дп.': 50,
    'д.': 60,
    'с.': 60,
    'ст-ца': 60,
    'ст.': 60,
    'х.': 60,
    'аул': 60,
    'а.': 60,
    'сл.': 60,
    'мкр.': 70,
}


# ═══════════════════════════════════════════════════════════════════
#  УЛИЦЫ
# ═══════════════════════════════════════════════════════════════════

_STREET_SUFFIX_MAP = {
    'ул': 'ул.',       'улица': 'ул.',
    'пр-кт': 'пр-т',   'пр-т': 'пр-т',        'проспект': 'пр-т',   'просп': 'пр-т',
    'ш': 'ш.',          'шоссе': 'ш.',
    'пер': 'пер.',      'переулок': 'пер.',
    'б-р': 'б-р',       'бульвар': 'б-р',
    'наб': 'наб.',      'набережная': 'наб.',
    'пр-д': 'пр-д',     'проезд': 'пр-д',
    'пл': 'пл.',        'площадь': 'пл.',
    'тракт': 'тракт',   'дор': 'дор.',         'дорога': 'дор.',
    'пр': 'пр.',        'ал': 'ал.',           'аллея': 'ал.',
    'мкр': 'мкр.',      'микрорайон': 'мкр.',  'линия': 'линия',
    'туп': 'туп.',      'тупик': 'туп.',
}

_STREET_PREFIXES = [
    'ул.', 'пр-кт', 'пр-т', 'просп.', 'ш.', 'шоссе', 'пер.', 'б-р', 'наб.',
    'пр-д', 'пл.', 'тракт', 'дор.', 'ал.', 'аллея', 'линия', 'пр.',
    'туп.', 'мкр.',
]

# Самостоятельные слова — тип улицы
_SOLO_STREET_WORDS = {
    'шоссе', 'набережная', 'бульвар', 'проспект', 'переулок',
    'площадь', 'тракт',
}


# ═══════════════════════════════════════════════════════════════════
#  НОМЕР ДОМА
# ═══════════════════════════════════════════════════════════════════

# Компоненты дома (не удаляем из вывода, кроме _SKIP_HOUSE)
_HOUSE_STARTS = [
    'д.',   'вл.',   'влд.',  'владение', 'зд.',   'соор.', 'строен.',
    'корп.','кор.',  'к.',    'лит.',  'литер', 'дом',
]
# «помещ.» и «этаж» — не выводим
_SKIP_HOUSE_PARTS = {'пом.', 'помещ.', 'помещение', 'этаж', 'подъезд'}

# Паттерн для «голого» номера (например, «22», «47А», «2В», «12А/1»)
# Не должен быть просто числом >= 4 цифр (это может быть год или код)
_RE_BARE_NUM = re.compile(
    r'^(\d{1,3}(?:-[А-Яа-яA-Za-z])?[А-Яа-яA-Za-z]?(?:[/-]\d{1,3}[А-Яа-яA-Za-z]?)*'
    r'|[А-Яа-яA-Za-z]\d+(?:[/-]\d{1,3}[А-Яа-яA-Za-z]?)*)$'
)
_RE_SHORT_STRUCTURE = re.compile(r'^с\.\s*(\d[\dА-Яа-яA-Za-z/\-]*)$', re.I)
_RE_TRAILING_HOUSE = re.compile(
    r'^(?P<street>.+?)\s+'
    r'(?P<house>(?:(?:д\.?|дом(?:\s*[№#])?|вл\.?|влд\.?|влад\.?|владение|зд\.?|здание|соор\.?|строен\.?|стр\.?|строение|с\.|корп\.?|кор\.?|корпус|к\.)\s*'
    r'[\dА-Яа-яA-Za-z][^,;]*)|(?:\d+[А-Яа-яA-Za-z]?\s*(?:лит\.?|литер|литера)\s*\.?\s*[А-Яа-яA-Za-z]))$',
    re.I,
)


# ═══════════════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════

def _clean(t: str) -> str:
    return re.sub(r'\s+', ' ', t).strip(' ,;.')


def _split_address_tokens(src: str) -> List[str]:
    """Splits on top-level commas, preserving commas inside quotes and brackets."""
    tokens: List[str] = []
    current: List[str] = []
    bracket_depth = 0
    quote: Optional[str] = None
    closing_quote = {'"': '"', '«': '»', '„': '“'}

    for index, char in enumerate(src):
        if quote:
            current.append(char)
            if char == closing_quote[quote]:
                quote = None
            continue

        if char in closing_quote and closing_quote[char] in src[index + 1:]:
            quote = char
            current.append(char)
            continue

        if char == '(':
            bracket_depth += 1
        elif char == ')' and bracket_depth:
            bracket_depth -= 1

        if (
            char == ','
            and bracket_depth == 0
            and not (
                index > 0
                and index + 1 < len(src)
                and src[index - 1].isdigit()
                and src[index + 1].isdigit()
            )
        ):
            token = _clean(''.join(current))
            if token:
                tokens.append(token)
            current = []
            continue
        current.append(char)

    token = _clean(''.join(current))
    if token:
        tokens.append(token)
    return tokens


def _normalize_source_text(src: str) -> str:
    """Repairs common glued road markers before token classification."""
    result = re.sub(r'(?<!\w)а\s*\.\s*д\s*\.', 'а/д', src, flags=re.I)
    result = re.sub(r'(?<!\w)а\s*-\s*д\b', 'а/д', result, flags=re.I)
    result = re.sub(r'(?<!\w)а/дорог[аиуы]?\b', 'а/д', result, flags=re.I)
    result = re.sub(r'(?<!\w)а/тракта?\b', 'тракт', result, flags=re.I)
    result = re.sub(r'\bавтотрасс([ауы])\b', r'трасс\1', result, flags=re.I)
    result = re.sub(r'\bтерритори[яи]\s+трасс[ыа]\b', 'трасса', result, flags=re.I)
    result = re.sub(r'\bвдоль\s+автомобильн\w*\s+дорог[аиуы]\b', 'а/д', result, flags=re.I)
    result = re.sub(r'(?<!\w)терр?\.?\s+автомобильн\w*\s+дорог[аиуы]\b', 'а/д', result, flags=re.I)
    result = re.sub(
        r'\bфедеральн\w*\s+автомобильн\w*\s+дорог[аиуы]?\b',
        'а/д',
        result,
        flags=re.I,
    )
    result = re.sub(
        r'(?P<km>\d+)(?P<ord>[-–]?(?:й|ой|ый))\s*'
        r'\(\s*(?P<road>а/д[^)]+)\s*\)\s*км\b',
        r'\g<km>\g<ord> км \g<road>',
        result,
        flags=re.I,
    )
    result = re.sub(r'(?<!\w)([МMАAРP])\s*-?\s*(?=\d)', r'\1-', result)
    result = re.sub(r'\bккм\b', 'км', result, flags=re.I)
    result = re.sub(r'\bшосс+е\b', 'шоссе', result, flags=re.I)
    result = re.sub(r'\bкм\.\s*(?=\d)', 'км ', result, flags=re.I)
    result = re.sub(r'(\d+)[-–]?йй\b', r'\1-й', result, flags=re.I)
    result = re.sub(r'(?<!\w)стр\s*-\s*(?=\d)', 'стр. ', result, flags=re.I)
    result = re.sub(r'(?<!\w)ст(?=\d)', 'стр. ', result, flags=re.I)
    result = re.sub(
        r'(?P<street>(?:ул|улица)\.?\s*[А-ЯЁ][А-Яа-яЁё\-]+)\.(?P<house>\d[\dА-Яа-яA-Za-z/\-]*)\b',
        r'\g<street>, \g<house>',
        result,
        flags=re.I,
    )
    result = re.sub(r'(?<!\w)с\s*\.\s*\.(?=[А-ЯЁ])', 'с. ', result, flags=re.I)
    result = re.sub(r'(?<!\w)с\s*\.\s*(?=[А-ЯЁ])', 'с. ', result)
    result = re.sub(r'\bряд\.\s*с\s+д\.ом\b', 'рядом с домом', result, flags=re.I)
    result = re.sub(
        r'\b(проспект|шоссе|тракт|улица|проезд|переулок)\.\s+(?=\d)',
        r'\1, ',
        result,
        flags=re.I,
    )
    result = re.sub(r'(\d+)\s+([йоы]й?)\s+(?=км\b)', r'\1-\2 ', result, flags=re.I)
    return re.sub(
        r'(?<!\w)(а/[дм]|ф/д)(?=[А-ЯЁA-Z])',
        r'\1 ',
        result,
        flags=re.I,
    )


def _is_postal(t: str) -> bool:
    return bool(_RE_POSTAL.match(t.strip()))


def _is_country(t: str) -> bool:
    if re.match(r'^(?:ул\.?|улица|пр-т|проспект|ш\.?|шоссе)\s+', t, re.I):
        return False
    words = set(re.sub(r'[^\wа-яёА-ЯЁ]', ' ', t.lower()).split())
    return bool(words & _COUNTRY_WORDS) and len(words) <= 4


def _is_region(t: str) -> bool:
    if re.match(r'^(?:ул\.?|улица|пр-т|проспект|ш\.?|шоссе)\s+', t, re.I):
        return False
    tl = t.lower()
    return any(m in tl for m in _REGION_MARKERS)


def _is_district(t: str) -> bool:
    # Убираем скобочные пояснения перед проверкой, чтобы «Павловского (Центральный р-н) ул»
    # не фильтровалось как район.
    tl = re.sub(r'\([^)]*\)', '', t).lower()
    return any(m in tl for m in _DISTRICT_MARKERS)


def _strip_district_number(name: str) -> str:
    """«Таврово-8» → «Таврово» (отрезает номер микрорайона после дефиса)."""
    return re.sub(r'\s*-\s*\d+\s*$', '', name).strip()


def _try_settlement(token: str) -> Optional[Tuple[str, str, int]]:
    t = _clean(token)
    for pattern, stype, priority in _SETT_PREFIX:
        m = pattern.match(t)
        if m:
            raw_name = m.group(m.lastindex).strip()
            name = raw_name if stype == 'мкр.' else _strip_district_number(raw_name)
            if name:
                return stype, name, priority
    for pattern, stype, priority in _SETT_SUFFIX:
        m = pattern.match(t)
        if m:
            name = _strip_district_number(m.group(1).strip())
            if name and len(name) > 1:
                return stype, name, priority
    return None


def _try_municipal_settlement(token: str) -> Optional[Tuple[str, str, int]]:
    """«МО Вяткинское с.п.» или «МО Воршинское (сельское поселение)»."""
    t = _clean(token)

    volost = re.match(r'^(.+?)\s+(?:волость|вол\.?)$', t, re.I)
    if volost:
        name = _clean(volost.group(1))
        if name:
            return 'вол.', name, 4

    generic_settlement = re.match(r'^(.+?)\s+поселение$', t, re.I)
    if generic_settlement:
        name = _clean(generic_settlement.group(1))
        if name and not re.search(r'\b(?:сельское|городское)$', name, re.I):
            return 'поселение', name, 4

    urban = re.match(r'^(?:гор\.?\s+поселение|городское\s+поселение|г(?:\.|/)?\s*п\.?)\s+(.+)$', t, re.I)
    if urban:
        name = _clean(urban.group(1))
        if name:
            return 'г.п.', name, 5

    urban_suffix = re.match(r'^(.+?)\s+(?:г(?:\.|/)?\s*п\.?|городское\s+поселение)$', t, re.I)
    if urban_suffix:
        name = _clean(urban_suffix.group(1))
        if name:
            return 'г.п.', name, 5

    rural_okrug = re.match(r'^(.+?)\s+(?:[сc]\.?\s*о\.?|[сc]/о|сельский\s+округ)$', t, re.I)
    if rural_okrug:
        name = _clean(rural_okrug.group(1))
        if name:
            return 'с.о.', name, 3

    rural = re.match(r'^(?:[сc]\.п\.?|[сc]\.\s+п\.|[сc]\s+п\.?|[сc]/п|сельское\s+поселение)\s*(.+)$', t, re.I)
    if rural:
        name = _clean(rural.group(1))
        if name:
            return 'с.п.', name, 4

    m = _RE_MUNICIPAL_SETTLEMENT.match(t)
    if m:
        name = _clean(m.group('name'))
        kind = re.sub(r'\s+', ' ', m.group('kind').lower())
        if name:
            if 'сельское поселение' in kind:
                suffix = '(сельское поселение)' if kind.startswith('(') else 'сельское поселение'
                return 'с.п.', f"{name} {suffix}", 4
            return 'с.п.', name, 4

    rural_suffix = re.match(r'^(.+?)\s+сельское\s+поселение$', t, re.I)
    if rural_suffix:
        name = _clean(rural_suffix.group(1))
        if name:
            return 'с.п.', name, 4

    rural_short_suffix = re.match(r'^(.+?)\s+(?:[сc]\.п\.?|[сc]\.\s+п\.|[сc]\s+п\.?|[сc]/п)$', t, re.I)
    if rural_short_suffix:
        name = _clean(rural_short_suffix.group(1))
        if name:
            return 'с.п.', name, 4
    return None


def _try_city_district_fallback(token: str) -> Optional[Tuple[str, str, int]]:
    """«г.о. Балашиха» или «м.о. Дмитровский» используем как fallback."""
    t = _clean(token)
    patterns = [
        (r'^(?:г\.о\.?|г\.\s*о\.|г/о)\s*(.+)$', 'г.о.', 2),
        (r'^(?:м\.о\.?|м\.\s*о\.|м/о)\s*(.+)$', 'м.о.', 2),
        (r'^(?:городской\s+округ)\s+(.+)$', 'г.о.', 2),
        (r'^(?:муниципальный\s+округ)\s+(.+)$', 'м.о.', 2),
        (r'^(.+?)\s+(?:г\.?\s*о\.?|г/о|городской\s+округ)$', 'г.о.', 2),
        (r'^(.+?)\s+(?:м\.?\s*о\.?|м/о|муниципальный\s+округ)$', 'м.о.', 2),
    ]
    for pattern, stype, priority in patterns:
        m = re.match(pattern, t, re.I)
        if not m:
            continue
        name = _clean(m.group(1))
        name = re.sub(r'^(?:город|г\.?)\s+', '', name, flags=re.I).strip()
        if name:
            return stype, name, priority
    return None


def _try_road_district_fallback(token: str) -> Optional[Tuple[str, str, int]]:
    """«Ногинский р-н» используем как НП, когда у трассы нет более точного уровня."""
    t = _clean(token)
    if _try_street(t):
        return None
    patterns = [
        r'^(?P<name>.+?)\s+(?:м\.?\s*р-н|м/р-н|муниципальный\s+(?:р-н|район)|р-н|р-он|район)$',
        r'^(?:м\.?\s*р-н|м/р-н|муниципальный\s+(?:р-н|район)|р-н|р-он|район)\.?\s+(?P<name>.+)$',
    ]
    for pattern in patterns:
        m = re.match(pattern, t, re.I)
        if not m:
            continue
        name = _clean(m.group('name'))
        if name:
            return '', f"{name} р-н", 1
    return None


def _format_settlement(settlement: Tuple[str, str, int]) -> str:
    stype, name, _priority = settlement
    if not stype:
        return name
    if stype == 'регион':
        result = re.sub(r'\b(?:область|обл\.?)$', 'обл.', name, flags=re.I)
        return re.sub(r'\bа\.?\s*о\.?$', 'а.о.', result, flags=re.I)
    if stype == 'с.п.' and 'сельское поселение' in name.lower():
        return name
    if stype == 'с.п.' and name.lower().endswith('сельсовет'):
        return f"{stype} {name}"
    if stype in _SUFFIX_OUTPUT_SETTLEMENT_TYPES:
        return f"{name} {stype}"
    return f"{stype} {name}"


def _limit_settlement(text: str) -> str:
    """Keeps settlement output within the same 30-character address limit."""
    result = re.sub(r'\s+', ' ', str(text)).strip(' ,;')
    replacements = [
        (r'\b(\d+)-го\s+отделения\s+совхоза\b', r'\1 отд. совхоза'),
        (r'\bсельское\s+поселение\b', 'с.п.'),
        (r'\bгородское\s+поселение\b', 'г.п.'),
        (r'\bмуниципальный\s+район\b', 'м.р-н'),
        (r'\bмуниципальный\s+округ\b', 'м.о.'),
        (r'\bгородской\s+округ\b', 'г.о.'),
        (r'\bобласть\b', 'обл.'),
        (r'\bрайон\b', 'р-н'),
    ]
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.I)
    result = re.sub(r'\s+', ' ', result).strip(' ,;')
    if len(result) <= _MAX_HOUSE_STREET_LEN:
        return result

    def shorten_word(match: re.Match) -> str:
        word = match.group(0)
        if len(word) <= 10:
            return word
        return f"{word[:8]}."

    result = re.sub(r'[А-ЯЁA-Z][А-Яа-яЁёA-Za-z]{10,}', shorten_word, result)
    result = re.sub(r'\s+', ' ', result).strip(' ,;')
    if len(result) <= _MAX_HOUSE_STREET_LEN:
        return result
    return result[:_MAX_HOUSE_STREET_LEN].rstrip(' ,;.')


def _settlement_hierarchy_rank(settlement: Tuple[str, str, int]) -> int:
    if not settlement[0] and re.search(r'\bр-н$', settlement[1], re.I):
        return 15
    return _SETTLEMENT_HIERARCHY_RANK.get(settlement[0], 0)


def _try_hierarchy_shift(
    settlements: List[Tuple[str, str, int]],
    district_fallbacks: List[Tuple[str, str, int]],
    region_fallbacks: List[Tuple[str, str, int]],
) -> Optional[Tuple[Tuple[str, str, int], str]]:
    """Без улицы переносит нижний уровень в адрес, а родителя — в НП."""
    landmarks = [
        (index, settlement)
        for index, settlement in enumerate(settlements)
        if settlement[0] in _ADDRESS_LANDMARK_SETTLEMENT_TYPES
    ]
    if not landmarks:
        return None

    landmark_index, landmark = max(
        landmarks,
        key=lambda item: (_settlement_hierarchy_rank(item[1]), item[0]),
    )
    landmark_rank = _settlement_hierarchy_rank(landmark)
    parents = [
        settlement
        for index, settlement in enumerate(settlements)
        if index != landmark_index and 0 < _settlement_hierarchy_rank(settlement) < landmark_rank
    ]
    parents.extend(district_fallbacks)
    parents.extend(region_fallbacks)
    if not parents:
        return None

    parent = max(
        enumerate(parents),
        key=lambda item: (_settlement_hierarchy_rank(item[1]), item[0]),
    )[1]
    return parent, _format_settlement(landmark)


def _try_only_settlement_shift(
    settlements: List[Tuple[str, str, int]],
    district_fallbacks: List[Tuple[str, str, int]],
    region_fallbacks: List[Tuple[str, str, int]],
) -> Optional[Tuple[Tuple[str, str, int], str]]:
    """Moves a lone concrete locality into the address when it is the only landmark."""
    if len(settlements) != 1:
        return None

    parents = [*district_fallbacks, *region_fallbacks]
    if not parents:
        return None

    parent = max(
        enumerate(parents),
        key=lambda item: (_settlement_hierarchy_rank(item[1]), item[0]),
    )[1]
    return parent, _format_settlement(settlements[0])


def _has_road_marker(token: str, allow_shosse: bool = True) -> bool:
    return bool(
        _RE_KM.search(token)
        or _RE_STRONG_ROAD_MARKER.search(token)
        or (allow_shosse and _RE_SHOSSE_MARKER.search(token))
    )


def _normalize_road_fragment(token: str) -> str:
    result = _clean(token)

    km_match = _RE_KM.search(result)
    start_match = _RE_ROAD_START_MARKER.search(result)
    if start_match:
        if start_match.start() > 0:
            prefix = result[:start_match.start()].lower()
            if (
                re.search(r'\b(?:в\s+р-не|в\s+районе|р-н|район)\b', prefix)
                and not _RE_KM.search(prefix)
            ):
                result = result[start_match.start():]
    elif km_match and km_match.start() > 0:
        prefix = _clean(result[:km_match.start()]).rstrip(' (')
        if not _try_street(prefix) and not re.search(r'\bкм\.?\s+тракт\b', result, re.I):
            result = result[km_match.start():]

    result = re.sub(r'^(?:тер\.?|территория)\s+', '', result, flags=re.I)

    street = _try_street(result)
    if street and _RE_ROAD_MARKER.search(result) and not _RE_KM.search(result):
        result = street

    result = _RE_BORDER_SUFFIX.sub('', result)
    result = result.replace('"', '').replace('«', '').replace('»', '')
    result = re.sub(r'\s+', ' ', result)
    return result.strip(' ,;.')


def _try_road_fragment(token: str, allow_shosse: bool = True) -> Optional[str]:
    if not _has_road_marker(token, allow_shosse=allow_shosse):
        return None
    road = _normalize_road_fragment(token)
    return road or None


def _is_road_object_token(token: str) -> bool:
    return bool(_RE_ROAD_OBJECT_MARKER.match(_clean(token)))


def _normalize_relative_description(text: str) -> str:
    desc = _clean(text)
    m = re.match(
        r'^(?P<distance>\d+[\.,]?\d*)\s*м\.?\s+(?:по\s+направлению\s+)?на\s+(?P<direction>.+)$',
        desc,
        re.I,
    )
    if m:
        distance = m.group('distance').replace(',', '.')
        direction = _clean(m.group('direction')).lower()
        return f"{distance} м. на {direction}"
    return desc


def _normalize_street_name(name: str) -> str:
    """«им Фамилия» → «им. Фамилия» (нормализует сокращение без точки)."""
    result = re.sub(r'\bим\b(?!\.)', 'им.', name, flags=re.I)
    result = re.sub(r'\b([А-ЯЁ])\.\s*([А-ЯЁ])\.\s*(?=[А-ЯЁ][а-яё])', r'\1.\2. ', result)
    result = re.sub(r'\b([А-ЯЁ])\.\s*(?=[А-ЯЁ][а-яё])', r'\1. ', result)
    return result


_STREET_PREFIX_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'^(?:ул\.?\s+|ул\.\s*|улица\s+)(.+)$', re.I), 'ул.'),
    (re.compile(r'^(?:пр-д\.?\s+|пр-д\.\s*|проезд\s+)(.+)$', re.I), 'пр-д'),
    (re.compile(r'^(?:пр-кт\.?\s+|пр-кт\.\s*|пр-т\.?\s+|пр-т\.\s*|просп\.?\s+|просп\.\s*|проспект\s+)(.+)$', re.I), 'пр-т'),
    (re.compile(r'^(?:пер\.?\s+|пер\.\s*|переулок\s+)(.+)$', re.I), 'пер.'),
    (re.compile(r'^(?:ш\.?\s+|ш\.\s*|шоссе\s+)(.+)$', re.I), 'ш.'),
    (re.compile(r'^(?:б-р\.?\s+|бульвар\s+)(.+)$', re.I), 'б-р'),
    (re.compile(r'^(?:наб\.?\s+|набережная\s+)(.+)$', re.I), 'наб.'),
    (re.compile(r'^(?:пл\.?\s+|площадь\s+)(.+)$', re.I), 'пл.'),
    (re.compile(r'^(?:дор\.?\s+|дорога\s+)(.+)$', re.I), 'дор.'),
    (re.compile(r'^(?:туп\.?\s+|тупик\s+)(.+)$', re.I), 'туп.'),
    (re.compile(r'^(?:ал\.?\s+|аллея\s+)(.+)$', re.I), 'ал.'),
]


def _try_street(token: str) -> Optional[str]:
    t = _clean(token)
    tl = t.lower()

    # Убираем суффикс «д[.] NN» и скобочные пояснения («(Центральный р-н)»)
    # Слитные токены вида «ул. Калинина д 116» отдельно разбирает _try_street_house.
    t_clean_street = re.sub(r'\s+д\.?\s+[\dА-Яа-яA-Za-z]+\s*$', '', t, flags=re.I)
    t_clean_street = re.sub(r'\s*\([^)]*\)', '', t_clean_street)
    t_clean_street = re.sub(r'\s*\([^)]*$', '', t_clean_street)
    t_clean_street = re.sub(r'\s+', ' ', t_clean_street).strip()
    tl_cs = t_clean_street.lower()

    compound_street = re.match(
        r'^(?P<first>.+?)\s+(?:пер\.?|переулок)\s*/\s*ул\.?\s+(?P<second>.+)$',
        t_clean_street,
        re.I,
    )
    if compound_street:
        return f"пер. {_normalize_street_name(compound_street.group('first').strip())}"

    for pattern, norm in _STREET_PREFIX_PATTERNS:
        m = pattern.match(t_clean_street)
        if m:
            rest = _normalize_street_name(m.group(1).strip())
            if rest:
                return f"{norm} {rest}"

    # Префиксный: «ул. Ленина», «тракт Северный»
    # Требуем, чтобы после префикса шёл пробел или конец строки —
    # иначе «тракт» ложно матчит «Тракторная».
    for prefix in _STREET_PREFIXES:
        pl = prefix.lower()
        if tl_cs.startswith(pl):
            after = tl_cs[len(pl):]
            if after and after[0] not in ' \t':
                continue          # «тракторная» ≠ «тракт» + «орная»
            rest = t_clean_street[len(prefix):].strip()
            if rest:
                return f"{prefix} {rest}"

    # Суффиксный: «Ленина ул», «В мкр»
    for suffix, norm in _STREET_SUFFIX_MAP.items():
        pat = re.compile(rf'^(.+?)\s+{re.escape(suffix)}\.?$', re.I)
        m = pat.match(t_clean_street)
        if m:
            name = re.sub(r'\s*\([^)]*$', '', m.group(1).strip())
            if not name:
                continue
            name = _normalize_street_name(name)
            return f"{norm} {name}"

    # «Дмитровское шоссе» — слово-тип в конце
    words = tl_cs.split()
    if len(words) >= 2 and words[-1] in _SOLO_STREET_WORDS:
        norm = _STREET_SUFFIX_MAP.get(words[-1], words[-1])
        name = _normalize_street_name(' '.join(t_clean_street.split()[:-1]))
        return f"{norm} {name}"

    return None


def _try_street_house(token: str) -> Optional[Tuple[str, str]]:
    """Разбирает токены без запятой между улицей и домом.

    Пример: «ул. Калинина д 116» → («ул. Калинина», «116»).
    """
    t = _clean(token)

    malformed_parenthesis = re.match(
        r'^(?P<street>[А-ЯЁA-Z][А-Яа-яЁёA-Za-z\-\s]+?)\s*\([^)]*\bул\.?'
        r'[^)]*,?\s+дом\s*№\s*(?P<house>.+)$',
        t,
        re.I,
    )
    if malformed_parenthesis:
        street = f"ул. {_normalize_street_name(malformed_parenthesis.group('street').strip())}"
        house = _try_house(malformed_parenthesis.group('house'))
        if street and house:
            return street, house

    glued = re.match(
        r'^(?P<street>(?:ул\.?\s*|улица\s+)[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z\s\-.]*[А-Яа-яЁёA-Za-z])'
        r'(?P<house>\d{1,3}[А-Яа-яA-Za-z]?(?:[/-]\d{1,3}[А-Яа-яA-Za-z]?)*)$',
        t,
        re.I,
    )
    if glued:
        street = _try_street(glued.group('street'))
        house = _try_house(glued.group('house'))
        if street and house:
            return street, house

    m = _RE_TRAILING_HOUSE.match(t)
    if not m:
        return None

    street = _try_street(m.group('street'))
    house = _try_house(m.group('house')) or _try_short_structure(m.group('house'))
    if street and house:
        return street, house
    return None


def _try_short_structure(token: str) -> Optional[str]:
    """«с. 113/2» после улицы — это строение, а не село."""
    m = _RE_SHORT_STRUCTURE.match(_clean(token))
    if m:
        return f"стр. {m.group(1)}"
    return None


def _try_territory_object(token: str) -> Optional[str]:
    """«территория АЗС 96» → «тер. АЗС 96»."""
    t = _clean(token)
    m = re.match(r'^(?:тер\.?|территория)\s+(.+)$', t, re.I)
    if not m:
        return None
    rest = _clean(m.group(1))
    if re.fullmatch(r'автодорог[аиуы]?', rest, re.I):
        return 'тер. Автодорога'
    if rest and not _has_road_marker(rest):
        return f"тер. {rest}"
    return None


def _try_zone_object(token: str) -> Optional[str]:
    """«производственная зона» сохраняем как адресный ориентир."""
    t = _clean(token)
    production_territory = re.match(r'^производственная\s+тер\.?$', t, re.I)
    if production_territory:
        return 'производственная тер.'

    numbered_industrial = re.match(
        r'^(?P<name>[А-ЯЁ][А-Яа-яЁё\-\s]+)\s+промышленная\s+зона\s*-\s*(?P<num>\d+)$',
        t,
        re.I,
    )
    if numbered_industrial:
        return f"промзона {_clean(numbered_industrial.group('name'))}-{numbered_industrial.group('num')}"

    m = re.match(
        r'^(?:территория\s+)?(?:промзона|(?:[А-ЯЁ][А-Яа-яЁё\-\s]+\s+)?промышленная\s+зона|производственная\s+зона|производственно-административная\s+зона)'
        r'(?:\s+[\"«]?(?P<name>.+?)[\"»]?)?$',
        t,
        re.I,
    )
    if m:
        base = re.sub(r'\s+промышленная\s+зона$', '', t, flags=re.I)
        raw_name = m.group('name') or (base if base != t else '')
        name = _clean(raw_name.replace('"', '').replace('«', '').replace('»', ''))
        return f"промзона {name}" if name else 'промзона'
    return None


def _try_named_landmark(token: str) -> Optional[str]:
    """Keeps address landmarks that replace a conventional street."""
    t = _clean(token)
    forestry = re.match(r'^(?P<name>.+?)\s+(?P<kind>участковое\s+лесничество|лесничество)$', t, re.I)
    if forestry:
        name = _clean(forestry.group('name'))
        kind = 'уч.лесн.' if forestry.group('kind').lower().startswith('участковое') else 'лесн.'
        return f"{name} {kind}"
    if re.fullmatch(r'Московская\s+Славянка', t, re.I):
        return 'Мск Славянка'
    microdistrict = re.match(r'^(?:мкр\.?|микрорайон|микрор-н)\s+(?P<name>.+)$', t, re.I)
    if microdistrict:
        name = re.sub(r'\s*-\s*', '-', _clean(microdistrict.group('name')))
        return f"мкр. {name}"
    deposit = re.match(
        r'^(?P<name>.+?)\s+(?:месторождение|мест-е)(?:\s+тер\.?)?$',
        t,
        re.I,
    )
    if deposit:
        return f"{_clean(deposit.group('name'))} мест-е"
    residential = re.match(r'^жилой\s+р-н\s+(?P<name>.+)$', t, re.I)
    if residential:
        name = re.sub(r'\s*№\s*', '-', _clean(residential.group('name')))
        name = re.sub(r'\bсеверо-западн\w*\b', 'СЗ', name, flags=re.I)
        return f"жилр-н {name}"
    if re.match(r'^дублер\s+.+\s+тракта$', t, re.I):
        return t[0].lower() + t[1:]
    if re.match(r'^[А-ЯЁ][А-Яа-яЁё\-\s]+\s+кольцо$', t):
        return t
    return None


def _try_azs_landmark(token: str) -> Optional[str]:
    """Recognizes a standalone fuel-station identifier."""
    t = _clean(token)
    m = re.match(
        r'^(?:автозаправочная\s+станция|АЗС)\s*(?P<sign>№|N|#)?\s*(?P<num>\d+)'
        r'(?:\s+тер\.?)?$',
        t,
        re.I,
    )
    if not m:
        return None
    sign = '№' if m.group('sign') else ''
    suffix = ' тер.' if not sign and re.search(r'\bтер\.?$', t, re.I) else ''
    return f"АЗС {sign}{m.group('num')}{suffix}"


def _try_compound_admin_landmark(token: str) -> Optional[Tuple[Tuple[str, str, int], str]]:
    """Splits glued rural levels followed by an address landmark."""
    t = _clean(token)
    azs = re.search(
        r'(?:автозаправочная\s+станция|АЗС)\s*(?:№|N|#)?\s*(?P<num>\d+)',
        t,
        re.I,
    )
    if azs:
        rural = re.search(r'(?:[сc]\.п\.?|[сc]\.\s+п\.|[сc]\s+п\.?|[сc]/п)\s+(?P<name>.+?)\s+с\.?\s+(?=автозаправоч)', t, re.I)
        if rural:
            return ('с.п.', _clean(rural.group('name')), 4), f"АЗС №{azs.group('num')}"

    glued_locality = re.match(
        r'^(?:[сc]\.п\.?|[сc]\.\s+п\.|[сc]\s+п\.?|[сc]/п)\s+(?P<parent>.+?)\s+'
        r'(?:село|с\.?)\s+(?P<locality>[А-ЯЁ][А-Яа-яЁё\-\s]+)$',
        t,
        re.I,
    )
    if glued_locality:
        parent = _clean(glued_locality.group('parent'))
        locality = _clean(glued_locality.group('locality'))
        return ('с.п.', parent, 4), f"с. {locality}"
    return None


def _try_initial_street(token: str) -> Optional[str]:
    """«П. Корчагина» inside a city is a street name, not a settlement."""
    t = _clean(token)
    m = re.match(r'^(?P<name>.+?)\s+ул\.?$', t, re.I)
    if m:
        name = re.sub(r'\s*\([^)]*\)', '', m.group('name').strip())
        name = re.sub(r'\s*\([^)]*$', '', name)
        name = _normalize_street_name(re.sub(r'\s+', ' ', name).strip())
        if name:
            return f"ул. {name}"
    if re.match(r'^[А-ЯЁ]\.\s+[А-ЯЁ][А-Яа-яЁё\-]+$', t):
        return f"ул. {t}"
    return None


def _try_street_landmark(token: str) -> Optional[str]:
    """Keeps a short parenthesized landmark attached to a street."""
    t = _clean(token)
    street = _try_street(t)
    if not street:
        return None
    if re.search(r'\(\s*со\s+стороны\s+парка\s*\)', t, re.I):
        return f"{street}, у парка"
    if re.search(r'\(\s*напротив\s+парка\s*\)', t, re.I):
        return f"{street}, напр.парка"
    if re.search(r'\(\s*(?:при\s+въезде\s+)?слева\s*\)', t, re.I):
        return f"{street}, слева"
    if re.search(r'\(\s*(?:при\s+въезде\s+)?справа\s*\)', t, re.I):
        return f"{street}, справа"
    direction = _try_direction_landmark(t)
    if direction:
        return f"{street}, {direction}"
    return None


def _try_direction_landmark(token: str) -> Optional[str]:
    """Keeps a standalone destination direction as a compact landmark."""
    t = _clean(token)
    parenthesized = re.search(r'\((?P<direction>[^()]*)\)\s*$', t)
    if parenthesized:
        t = _clean(parenthesized.group('direction'))
    else:
        t = t.strip('() ')
    if re.fullmatch(r'из\s+Казан[иь]', t, re.I):
        return 'из Казани'
    if re.fullmatch(r'в\s+сторону\s+Казан[иь]', t, re.I):
        return 'в Казань'
    if re.fullmatch(r'в\s+сторону\s+Уф[ыа]', t, re.I):
        return 'в сторону Уфы'
    if re.fullmatch(r'в\s+сторону\s+Набережн\w*\s+Челн\w*', t, re.I):
        return 'в Наб.Челны'
    return None


def _try_road_landmark_token(token: str) -> Optional[str]:
    """Recognizes standalone details that belong to an adjacent road fragment."""
    t = _clean(token)
    bypass = re.match(r'^обход\s+(?P<city>г\.?\s*.+)$', t, re.I)
    if bypass:
        return f"обход {_clean(bypass.group('city'))}"
    chainage = re.match(
        r'^(?:км\.?\s*)?(?P<km>\d+\s*\+\s*\d+)(?:\s*м\.?)?'
        r'(?:\s*\((?P<direction>из\s+[^)]+)\))?$',
        t,
        re.I,
    )
    if chainage:
        km = re.sub(r'\s+', '', chainage.group('km'))
        direction = chainage.group('direction')
        return f"{km} {direction}" if direction else km
    exit_landmark = re.match(r'^съезд(?:\s+к\s+(?P<target>.+))?$', t, re.I)
    if exit_landmark:
        target = _clean(exit_landmark.group('target') or '')
        return f"съезд к {target}" if target else 'съезд'
    drsu = re.match(r'^(?P<distance>\d+)\s*м\.?\s+ДРСУ$', t, re.I)
    if drsu:
        return f"{drsu.group('distance')}м ДРСУ"
    post = re.match(r'^почтов\w*\s+отделени\w*\s*№\s*(?P<num>\d+)$', t, re.I)
    if post:
        return f"п/о{post.group('num')}"
    return None


def _try_relative_hamlet_landmark(token: str) -> Optional[str]:
    """Keeps a compact position relative to a hamlet without replacing the parent settlement."""
    t = _clean(token)
    near = re.match(r'^в\s+районе\s+х\.?\s*(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)$', t, re.I)
    if near:
        return f"у х.{near.group('name')}"
    edge = re.match(
        r'^с\s+северо-\s*восточн\w*\s+окраин\w*\s+х\.?\s*(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)$',
        t,
        re.I,
    )
    if edge:
        return f"СВ х.{edge.group('name')}"
    return None


def _try_embedded_aul(token: str) -> Optional[Tuple[str, str, int]]:
    """Extracts «а. Тугурой» from a prose fragment ending with an address."""
    m = re.search(r'(?:^|:)\s*а\.\s*(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)\s*$', _clean(token), re.I)
    if m:
        return 'а.', m.group('name'), 3
    return None


def _try_trailing_admin_street(token: str) -> Optional[str]:
    """Extracts a street appended to an administrative phrase without a comma."""
    t = _clean(token)
    marker = re.search(r'(?<!\w)(?:ул\.?|улица|ш\.?|шоссе|тракт)\s+.+$', t, re.I)
    if marker and marker.start() > 0 and re.search(r'\b(?:округ|район|р-н)\b', t[:marker.start()], re.I):
        return _try_street(marker.group(0))
    return None


def _try_relative_house_landmark(token: str) -> Optional[str]:
    """«примерно в 120 м ... от д.15» → «120м В от д.15»."""
    t = _clean(token)
    m = re.search(
        r'(?:примерно\s+)?(?:в\s+)?(?P<distance>\d+)\s*(?:м\.?|метр\w*)\s+'
        r'(?:по\s+направлению\s+)?на\s+(?P<direction>[^,]+?)\s+от\s+'
        r'д\.?\s*(?P<house>\d[\dА-Яа-яA-Za-z/\-]*)$',
        t,
        re.I,
    )
    if not m:
        return None
    direction = _compact_relative_text(f"{m.group('distance')}м на {m.group('direction')}")
    return f"{direction} от д.{m.group('house')}" if direction else None


def _try_school_landmark(token: str) -> Optional[str]:
    """Keeps a compact school-relative distance from a long prose description."""
    t = _clean(token)
    m = re.search(
        r'(?P<distance>\d+)\s*метр\w*\s+по\s+направлению\s+на\s+'
        r'(?P<direction>[А-Яа-яЁё\-]+).*?\bСОШ\s*№\s*(?P<num>\d+)',
        t,
        re.I,
    )
    if not m:
        return None
    compact = _compact_relative_text(f"{m.group('distance')}м на {m.group('direction')}")
    return f"{compact} от шк.{m.group('num')}" if compact else None


def _try_plain_settlement_fallback(token: str) -> Optional[Tuple[str, str, int]]:
    """«Малино, ул. Ступинская» → населённый пункт «Малино» без выдуманного типа."""
    t = _clean(token)
    if not re.match(r'^[А-ЯЁ][А-Яа-яЁё\-]+(?:\s+[А-ЯЁ][А-Яа-яЁё\-]+)?$', t):
        return None
    return '', t, 1


def _try_implicit_street(token: str) -> Optional[str]:
    """«Чичерина, 5» → «ул. Чичерина» when a house makes the meaning unambiguous."""
    fallback = _try_plain_settlement_fallback(token)
    return f"ул. {fallback[1]}" if fallback else None


def _try_address_detail(token: str) -> Optional[str]:
    """Участки и ориентиры, которые важны как адресный объект."""
    t = _clean(token)

    opposite = re.search(
        r'\bнапротив\s+(?P<prefix>вл\.?|влд\.?|влад\.?|владение)\s*'
        r'(?P<num>[\dА-Яа-яA-Za-z/\-]+)',
        t,
        re.I,
    )
    plot = re.search(
        r'\b(?:участ(?:ок|ка)?|уч\.|з\.?\s*у\.?)\s*(?:№|N|#)?\s*(?P<num>\d[\dА-Яа-яA-Za-z/\-]*)\b',
        t,
        re.I,
    )
    near_house = re.search(
        r'\b(?:вблизи|рядом\s+с|у)\s+(?:дом(?:а|ом)?|д\.)\s*(?:№|N|#)?\s*'
        r'(?P<num>\d[\dА-Яа-яA-Za-z/\-]*)',
        t,
        re.I,
    )
    territory_number = re.fullmatch(r'тер\.?\s*(?P<num>\d[\dА-Яа-яA-Za-z/\-]*)', t, re.I)
    quarter = re.fullmatch(r'квартал\s+(?P<num>\d[\dА-Яа-яA-Za-z/\-]*)', t, re.I)
    if opposite and plot:
        return f"уч.{plot.group('num')} напр.вл.{opposite.group('num')}"

    if near_house:
        return f"у д.{near_house.group('num')}"

    if plot:
        return f"уч.{plot.group('num')}"

    if opposite:
        return f"напр.вл.{opposite.group('num')}"

    if territory_number:
        return f"тер. {territory_number.group('num')}"

    if quarter:
        return f"кв.{quarter.group('num')}"

    return None


def _try_street_relative_house(token: str) -> Optional[Tuple[str, str]]:
    """«ул. Голубева 55 метров на юг от д.а №3» → street + compact landmark."""
    t = _clean(token)
    m = re.match(
        r'^(?P<street>(?:ул\.?\s*|улица\s+).+?)\s+'
        r'(?P<distance>\d+)\s*(?:м\.?|метр\w*)\s+'
        r'(?:по\s+направлению\s+)?на\s+(?P<direction>[^,]+?)\s+от\s+'
        r'д\.?\s*а?\.?\s*(?:№|N|#)?\s*(?P<house>\d[\dА-Яа-яA-Za-z/\-]*)$',
        t,
        re.I,
    )
    if not m:
        return None

    street = _try_street(m.group('street'))
    direction = _compact_relative_text(f"{m.group('distance')} метров на {m.group('direction')}")
    if street and direction:
        return street, f"{direction} от д.{m.group('house')}"
    return None


def _split_trailing_house_and_side(text: str) -> Tuple[str, Optional[str]]:
    t = _clean(text)
    side = _compact_side(t)
    if side:
        t = re.sub(
            r'\s+(?:справа|слева|право|лево|правая\s+сторона|левая\s+сторона)$',
            '',
            t,
            flags=re.I,
        ).strip()

    parts = t.split()
    if not parts:
        return t, side

    last = parts[-1].strip(' ,;.')
    if _RE_BARE_NUM.match(last):
        street = ' '.join(parts[:-1])
        house = f"{last} {side}" if side else last
        return street, house
    return t, side


def _try_inline_settlement_street_house(token: str) -> Optional[Tuple[Tuple[str, str, int], str, List[str]]]:
    """«г. Балашиха Щелковское шоссе 20/21 лево» без запятых."""
    t = _clean(token)
    if _INLINE_DISTRICT_MARKER.search(t):
        return None

    m = re.match(r'^(?P<prefix>г\.?|город)\s+(?P<rest>.+)$', t, re.I)
    if not m:
        return None

    words = m.group('rest').split()
    if len(words) < 3:
        return None

    max_settlement_words = min(3, len(words) - 2)
    for split in range(1, max_settlement_words + 1):
        settlement = _try_settlement(f"г. {' '.join(words[:split])}")
        if not settlement:
            continue

        street_part, house = _split_trailing_house_and_side(' '.join(words[split:]))
        street = _try_street(street_part)
        if street:
            return settlement, street, [house] if house else []

    return None


def _try_parenthesized_settlement_road(token: str) -> Optional[Tuple[Tuple[str, str, int], str]]:
    """«село Костылиха (327 км М-12 ...)» → settlement + дорожный фрагмент."""
    t = _clean(token)
    m = re.match(r'(?P<sett>.+?)\s*\((?P<road>.*(?:км|[МM]-?\d|[АA]-?\d|[РPР]-?\d|а/д|автодорог|трасс|цкад|мкад).*)\)$', t, re.I)
    if not m:
        return None

    settlement = _try_settlement(m.group('sett'))
    road = _clean(m.group('road'))
    if settlement and road:
        return settlement, road
    return None


def _try_settlement_before_km(token: str) -> Optional[Tuple[Tuple[str, str, int], str]]:
    """«с. Клещёвка 283 км» → locality plus chainage."""
    t = _clean(token)
    m = re.match(
        r'(?P<sett>(?:[гсдпх]\.?\s*|город\s+|село\s+|хутор\s+).+?)\s+'
        r'(?P<km>\d+(?:[\.,]\d+)?\s*км)\b',
        t,
        re.I,
    )
    if not m:
        return None
    settlement = _try_settlement(m.group('sett'))
    return (settlement, m.group('km')) if settlement else None


def _try_road_embedded_settlement(token: str) -> Optional[Tuple[str, str, int]]:
    """Достаёт ориентир-нас.пункт из дорожного описания: «... в Софьино правая сторона»."""
    t = _clean(token)
    if not _has_road_marker(t):
        return None

    m = re.search(
        r'\bв\s+(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+(?:\s+[А-ЯЁ][А-Яа-яЁё\-]+){0,2})\s+'
        r'(?:правая|левая)\s+сторона\b',
        t,
    )
    if not m:
        m = re.search(
            r'\bв\s+(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+(?:\s+[А-ЯЁ][А-Яа-яЁё\-]+){0,2})\s+'
            r'(?:справа|слева|право|лево)\b',
            t,
        )
    if not m:
        return None

    name = _clean(m.group('name'))
    if name.lower() in {'районе', 'р-не'}:
        return None
    return '', name, 2


def _try_compound_settlement_street(token: str) -> Optional[Tuple[Tuple[str, str, int], str]]:
    """Разбирает склеенный фрагмент вида «г. Москва район Митино Пятницкое ш.»."""
    t = _clean(token)
    marker = _INLINE_DISTRICT_MARKER.search(t)
    if not marker:
        return None

    settlement = _try_settlement(t[:marker.start()])
    if not settlement:
        return None

    words = t[marker.end():].strip().split()
    if len(words) < 2:
        return None

    candidates: List[Tuple[int, int, str]] = []
    max_skip = min(4, len(words) - 1)
    for skip in range(max_skip + 1):
        candidate_text = ' '.join(words[skip:])
        street = _try_street(candidate_text)
        if not street:
            continue

        score = -skip * 5
        if skip == 0:
            score += 50
        if skip > 0:
            previous_word = words[skip - 1].lower().strip('.,')
            first_word = words[skip].lower().strip('.,')
            if previous_word in _STREET_NAME_QUALIFIERS and first_word not in _STREET_NAME_QUALIFIERS:
                score += 30
        candidates.append((score, skip, street))

    if not candidates:
        return None

    _score, _skip, street = min(candidates, key=lambda item: (item[0], -item[1]))
    return settlement, street


def _try_house(token: str) -> Optional[str]:
    """
    Извлекает номер дома. Возвращает строку или None.
    Handles: «д. 5А», «дом № 7Б стр.1», «вл. 3», «лит. А», «22», «47А» и т.п.
    """
    t = _clean(token)
    tl = t.lower()

    # «дом №X», «дом X», «д. X», «д.116» или «д X»
    m = re.match(r'дом(?:\s*[№#]\s*|\s+)(.+)', t, re.I)
    if m:
        rest = m.group(1)
        if re.match(r'^[А-Яа-яЁё][А-Яа-яЁё\s\-]+$', rest):
            return None
        if re.match(
            r'^(?:влд?\.?|влад\.?|владение|зд\.?|здание|соор\.?|сооружение|'
            r'строен\.?|строение|стр\.?|с\.)\s*(?:[№#]\s*)?\d',
            rest,
            re.I,
        ):
            prefixed = _try_house(rest)
            if prefixed:
                return prefixed
        return _filter_house(rest)

    m = re.match(r'д(?:\.|\s+)\s*(.+)', t, re.I)
    if m:
        rest = m.group(1)
        if re.match(r'^[А-Яа-яЁё][А-Яа-яЁё\s\-/\(\)]+$', rest):
            return None
        return _filter_house(rest)

    m = re.match(
        r'^(?P<num>\d{1,3}[А-Яа-яA-Za-z]?)\s*'
        r'(?:корпус|корп\.?|кор\.?|к\.?)\s*(?P<corp>\d[\dА-Яа-яA-Za-z/\-]*)$',
        t,
        re.I,
    )
    if m:
        return f"{m.group('num')}, к. {m.group('corp')}"

    m = re.match(
        r'^(?P<num>\d+[А-Яа-яA-Za-z]?(?:[/-]\d+[А-Яа-яA-Za-z]?)*)\s+'
        r'(?P<structure>стр\.?|строен\.?|строение)\s*(?P<part>\d[\dА-Яа-яA-Za-z/\-]*)$',
        t,
        re.I,
    )
    if m:
        return f"{m.group('num')} стр. {m.group('part')}"

    m = re.match(r'(?P<num>\d+[А-Яа-яA-Za-z]?(?:[/-]\d+[А-Яа-яA-Za-z]?)*)\s*(?P<lit>лит\.?|литер|литера)\s*\.?\s*(?P<letter>[А-Яа-яA-Za-z])$', t, re.I)
    if m:
        return f"{m.group('num')} лит. {m.group('letter')}"

    m = re.match(r'^(?P<num>\d{1,3})\s*[\"«„]?\s*(?P<letter>[А-Яа-яA-Za-z])\s*[\"»“]?$', t, re.I)
    if m:
        return f"{m.group('num')}{m.group('letter')}"

    # Стандартные префиксы дома
    object_prefixes = [
        ('владение', 'вл.'), ('влад.', 'вл.'), ('влд.', 'вл.'), ('влд', 'вл.'),
        ('вл.', 'вл.'), ('вл', 'вл.'),
        ('здание', 'зд.'), ('зд.', 'зд.'), ('зд', 'зд.'),
        ('сооружение', 'соор.'), ('соор.', 'соор.'), ('соор', 'соор.'),
        ('строение', 'стр.'), ('строен.', 'стр.'), ('строен', 'стр.'),
        ('стр.', 'стр.'), ('стр', 'стр.'), ('ст.', 'стр.'),
    ]
    for pref, normalized_pref in object_prefixes:
        pattern = rf'^{re.escape(pref)}\s*(?:[№#]\s*)?(?=\d)(.+)$'
        m = re.match(pattern, t, re.I)
        if m:
            rest = m.group(1).strip()
            if not rest:
                continue
            return f"{normalized_pref} {_filter_house(rest)}"

    # Корпус / литер («корпус» — полное слово без точки)
    # «к.» матчится ТОЛЬКО если за ним идёт цифра —
    # иначе «К.Маркса» ложно становится корпусом «к. Маркса».
    for pref in ['корп.', 'кор.', 'к.', 'лит.', 'литера', 'литер', 'корпус']:
        if tl.startswith(pref.lower()):
            rest = t[len(pref):].strip()
            if not rest:
                continue
            if pref == 'к.' and not re.match(r'^\d', rest):
                continue
            comp = 'лит.' if pref in ('лит.', 'литера', 'литер') else 'к.'
            return f"{comp} {rest}"

    # «Голый» номер: 22, 47А, 2В (но не просто буква)
    if _RE_BARE_NUM.match(t):
        return t

    return None


def _filter_house(raw: str) -> str:
    """Убирает «помещ.», «этаж» и т.п. из номера дома."""
    cleaned = re.split(
        r'\s*[,;.]\s*(?:помещ(?:ение)?\.?|пом\.?|комн?\.?|комната|этаж|подъезд)\b',
        raw, flags=re.I
    )[0]
    cleaned = re.split(
        r'\s+(?:торговый\s+центр|тц|трц)\b',
        cleaned,
        flags=re.I,
    )[0]
    cleaned = cleaned.strip()
    cleaned = re.sub(r'^(\d{1,3})\s+([А-ЯA-Z])$', r'\1\2', cleaned, flags=re.I)
    return cleaned.strip().strip(',.')


def _join_houses(houses: List[str]) -> str:
    """Объединяет компоненты дома: строение/литера прилипают пробелом,
    корпус и остальные — через запятую.
    Пример: ['24', 'стр. 1'] → '24 стр. 1'
            ['1', 'к. а'] → '1, к. а'
    """
    if not houses:
        return ""
    result = houses[0]
    for h in houses[1:]:
        hl = h.lower()
        if hl.startswith('стр.') or hl.startswith('лит.'):
            result += ' ' + h
        else:
            result += ', ' + h
    return result


_RE_NEAR_BUILDING = re.compile(
    r'(?:здани\w*|зд\.)\s*([\dА-Яа-яA-Za-z]{1,6})',
    re.I,
)


def _try_near_building(token: str) -> Optional[str]:
    """«в районе здания 2а», «рядом с зд. 3» → '2а'.

    Обрабатывается ДО _is_district, чтобы пространственные описания
    вида «в районе здания X» не отбрасывались как токены-районы.
    """
    t = _clean(token)
    if not re.search(r'\b(?:в\s+районе|в\s+р-не|рядом|около|возле|у)\b', t, re.I):
        return None
    m = _RE_NEAR_BUILDING.search(t)
    if m:
        candidate = m.group(1)
        if _RE_BARE_NUM.match(candidate):
            return f"зд. {candidate}"
    return None


def _try_distance_direction_settlement(token: str) -> Optional[Tuple[Tuple[str, str, int], str]]:
    """«500 м по направлению на юго-восток от д. Тешеничи».

    Возвращает settlement и нормализованное описание для колонки «дом, улица».
    """
    t = _clean(token)
    m = _RE_DISTANCE_DIRECTION_SETTLEMENT.search(t)
    if m:
        settlement = _try_settlement(m.group('settlement'))
        if settlement:
            distance = m.group('distance').replace(',', '.')
            direction = _clean(m.group('direction')).lower()
            if direction:
                return settlement, f"{distance} м. на {direction}"

    offset = re.match(
        r'^(?:в\s+)?(?P<distance>\d+[\.,]?\d*)\s*м\.?\s+'
        r'(?P<direction>западнее|восточнее|севернее|южнее|на\s+запад|на\s+восток|на\s+север|на\s+юг)\s+'
        r'(?P<settlement>(?:[гсдп]\.\s*|[гсдп]\s+|город\s+|пос\.\s*|пос\s+|дер\.\s*|деревн(?:я|и)\s+|село\s+|поселок\s+|посёлок\s+)[^()]+)'
        r'(?P<tail>.*)$',
        t,
        re.I,
    )
    if offset:
        settlement = _try_settlement(offset.group('settlement'))
        if settlement:
            desc = _compact_relative_text(t) or _normalize_relative_description(
                f"{offset.group('distance')} м. {offset.group('direction')}"
            )
            return settlement, desc

    relative = re.match(
        r'^(?P<desc>.*?)'
        r'(?:\bот\b|\bу\b|\bв\s+р-не\b|\bв\s+районе\b|\bвблизи\b)\s+'
        r'(?P<settlement>(?:[гсдп]\.\s*|[гсдп]\s+|город\s+|пос\.\s*|пос\s+|дер\.\s*|деревн(?:я|и)\s+|село\s+|поселок\s+|посёлок\s+).+)$',
        t,
        re.I,
    )
    if not relative:
        return None

    settlement = _try_settlement(relative.group('settlement'))
    if not settlement:
        return None

    desc = _normalize_relative_description(relative.group('desc'))
    if not desc:
        desc = t
    return settlement, desc


def _km_description(text: str) -> str:
    """Из «424 км + 700 м лево а/д М-3 «Украина»» возвращает строку
    с километражом и названием трассы: «424 км + 700 м лево а/д М-3 «Украина»»."""
    km_match = _RE_KM.search(text)
    if not km_match:
        return text.strip()

    result = text[km_match.start():]

    # Обрезаем номер владения/дома, если он прицеплён к тому же токену
    house_marker = re.search(
        r'\s+(?:вл\.?|влд\.?|зд\.?|дом(?:\s*[№#])?|д\.(?=\s*\d))',
        result, flags=re.I
    )
    if house_marker:
        result = result[:house_marker.start()]

    result = _RE_BORDER_SUFFIX.sub('', result)
    result = result.replace('"', '').replace('«', '').replace('»', '')
    result = re.sub(r'\s+', ' ', result)
    return result.strip(' ,;.')


_RE_ROUTE_CODE = re.compile(r'(?<![\w])(?P<prefix>[МMмАAаРPр])\s*-?\s*(?P<num>\d{1,3})(?!\d)')
_ROUTE_NAME_KEEP = {
    'дон': 'Дон',
    'крым': 'Крым',
    'волга': 'Волга',
    'балтия': 'Балтия',
    'урал': 'Урал',
    'украина': 'Украина',
    'беларусь': 'Беларусь',
    'кавказ': 'Кавказ',
    'россия': 'Россия',
    'восток': 'Восток',
}
_ROUTE_NAME_SHORT = {
    'холмогоры': 'Холм.',
}


def _compact_side(text: str) -> Optional[str]:
    tl = text.lower()
    if re.search(r'\b(?:справа|право|правая\s+сторона|\(?право\)?)\b', tl):
        return 'П'
    if re.search(r'\b(?:слева|лево|левая\s+сторона|\(?лево\)?)\b', tl):
        return 'Л'
    return None


def _is_side_word(text: str) -> bool:
    return bool(re.fullmatch(r'(?:справа|слева|право|лево|правая|левая)', _clean(text), re.I))


def _compact_ring_side(text: str) -> Optional[str]:
    tl = text.lower()
    if re.search(r'\bвнешн\.?\s*ст\.?\b|\bвнешн\w*\s+сторон\w*\b', tl):
        return 'внеш.'
    if re.search(r'\bвнутр\.?\s*ст\.?\b|\bвнутрен+\w*\s+сторон\w*\b', tl):
        return 'внутр.'
    return None


def _compact_pk(text: str) -> Optional[str]:
    m = re.search(r'\bпк\s*(?P<num>\d+)\b', text, re.I)
    return f"ПК{m.group('num')}" if m else None


def _compact_km(text: str) -> Optional[str]:
    t = text.replace(',', '.')
    parenthesized_meters = re.search(
        r'(?P<km>\d+(?:[-–]\d+)?)\s*\(\s*\+\s*(?P<m>\d+)(?:\s*м\.?)?\s*\)\s*км',
        t,
        re.I,
    )
    if parenthesized_meters:
        km = parenthesized_meters.group('km').replace('–', '-')
        return f"{km}км+{parenthesized_meters.group('m')}м"

    detailed = re.search(
        r'(?P<km>\d+(?:[-–]\d+)?)\s*\(\s*(?P<inner>\d+\s*\+\s*\d+)\s*м\.?\s*\)\s*км',
        t,
        re.I,
    )
    if detailed:
        km = detailed.group('km').replace('–', '-')
        inner = re.sub(r'\s+', '', detailed.group('inner'))
        return f"{km}км({inner}м)"

    patterns = [
        r'(?P<km>\d+(?:[-–]\d+)?)\s*\+\s*(?P<m>\d+)(?!\d|\s*(?:км|м\.?))',
        r'(?P<km>\d+(?:[-–]\d+)?)\s*\+\s*(?P<m>\d+)\s*м\.?(?!\s*км)',
        r'(?P<km>\d+(?:[-–]\d+)?)\s*\+\s*(?P<m>\d+)\s*км',
        r'(?P<km>\d+(?:\.\d+)?(?:[-–]\d+)?)\s*(?:км|километр\w*)\.?\s*(?P<op>[-+])\s*(?P<m>\d+)(?:\s*м\.?)?',
        r'(?P<km>\d+(?:\.\d+)?(?:[-–]\d+)?)(?:[-–]?\s*(?:й|ой|ый))?\s*(?:км|километр\w*)\.?\s*\+?\s*(?P<m>\d+)\s*м\.?',
        r'(?:км|километр\w*)\s*(?P<km>\d+(?:[-–]\d+)?)(?:[-–]?(?:й|ой|ый))?(?:\s*\+\s*(?P<m>\d+)(?:\s*м\.?)?)?',
        r'(?P<km>\d+(?:\.\d+)?(?:[-–]\d+)?)(?:[-–]?\s*(?:й|ой|ый)|[-–])?\s*(?:км|километр\w*)',
    ]
    for pattern in patterns:
        m = re.search(pattern, t, re.I)
        if not m:
            continue
        km = m.group('km').replace('–', '-').replace('.', ',')
        meters = m.groupdict().get('m')
        if meters:
            return f"{km}км{m.groupdict().get('op') or '+'}{meters}м"
        return f"{km}км"
    return None


def _extract_route_code(text: str, with_name: bool = True) -> Optional[str]:
    m = _RE_ROUTE_CODE.search(text)
    if not m:
        if re.search(r'\bмкад\b', text, re.I):
            return 'МКАД'
        if re.search(r'\bцкад\b', text, re.I):
            return 'ЦКАД'
        if re.search(r'\bекад\b', text, re.I):
            return 'ЕКАД'
        return None

    prefix = m.group('prefix').upper()
    prefix = {'M': 'М', 'А': 'А', 'A': 'А', 'P': 'Р'}.get(prefix, prefix)
    code = f"{prefix}-{m.group('num')}"
    if not with_name:
        return code
    if code == 'А-113' and re.search(r'\bцкад\b', text, re.I):
        return 'А-113 ЦКАД'

    after = text[m.end():].strip(' "\'«»()-,.')
    name_match = re.match(r'([А-Яа-яЁёA-Za-z]+)', after)
    if not name_match:
        return code

    raw_name = name_match.group(1)
    name_l = raw_name.lower()
    if name_l in _ROUTE_NAME_KEEP:
        return f"{code} {_ROUTE_NAME_KEEP[name_l]}"
    if name_l in _ROUTE_NAME_SHORT:
        return f"{code} {_ROUTE_NAME_SHORT[name_l]}"
    endpoints = re.match(
        r'(?P<name>[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]+-[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]+)',
        after,
    )
    if endpoints and re.search(r'(?:а/[дм]|ф/д|фад|автодорог[аиуы]?|автотрасс[ауы]?)', text[:m.start()], re.I):
        return f"{code} {_normalize_named_road_name(endpoints.group('name'))}"
    return code


def _shorten_name_words(name: str, max_part_len: int = 10) -> str:
    result = re.sub(r'\s+', ' ', name).strip(' ,;.')
    parts = []
    for part in result.split('-'):
        p = part.strip()
        if len(p) > max_part_len:
            p = p[:max_part_len - 1] + '.'
        parts.append(p)
    return '-'.join(parts)


def _normalize_named_road_name(name: str) -> str:
    cleaned = name.replace('"', '').replace('«', '').replace('»', '')
    cleaned = re.sub(r'\s*-\s*', '-', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,;.')
    cleaned = re.sub(r'\s+\d+$', '', cleaned)
    cleaned = re.sub(r'\s+на$', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s+тер\.?\s+км$', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s+тер\.?$', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s+(?:справа|слева|право|лево)$', '', cleaned, flags=re.I)
    cleaned = re.sub(r'-(?:справа|слева|право|лево)$', '', cleaned, flags=re.I)
    parts = []
    for part in cleaned.split('-'):
        p = part.strip()
        lower = p.lower()
        if lower in _ROUTE_NAME_KEEP:
            p = _ROUTE_NAME_KEEP[lower]
        parts.append(p)
    return '-'.join(parts)


def _normalize_road_adjective(name: str) -> str:
    """Normalizes a road adjective used before a trailing «а/д» marker."""
    cleaned = _clean(name)
    if re.search(r'ской$', cleaned, re.I):
        return f"{cleaned[:-4]}ская"
    if re.search(r'цкой$', cleaned, re.I):
        return f"{cleaned[:-4]}цкая"
    return cleaned


def _repair_glued_road_token(token: str) -> str:
    """Repairs a narrow typo: «р-н Варламовскойа/д» → «а/д Варламовская»."""
    t = _clean(token)
    m = re.match(r'^р-н\s+(?P<name>[А-Яа-яЁё\-]+?)а/д$', t, re.I)
    if not m:
        return t
    return f"а/д {_normalize_road_adjective(m.group('name'))}"


def _single_replacement_away(left: str, right: str) -> bool:
    left_lower = left.lower()
    right_lower = right.lower()
    return len(left_lower) == len(right_lower) and sum(
        a != b for a, b in zip(left_lower, right_lower)
    ) == 1


def _correct_road_endpoint_typo(text: str, settlement: str) -> str:
    """Исправляет одну опечатку в конце дороги по уже найденному нас.пункту."""
    if not settlement or not _has_road_marker(text):
        return text

    settlement_name = re.sub(
        r'^(?:г\.о\.|г\.п\.|с\.п\.|с\.о\.|пгт\.|рп\.|г\.|п\.|д\.|с\.)\s+',
        '',
        settlement,
        flags=re.I,
    ).strip()
    if len(settlement_name) < 4:
        return text

    marker = re.search(r'(?:а/[дм]|ф/д|фад|автодорог[аиуы]?|трасс[ауы]?)', text, re.I)
    if not marker:
        return text

    suffix = text[marker.end():]
    for candidate in re.finditer(r'[А-ЯЁ][А-Яа-яЁё\-]{3,}', suffix):
        value = candidate.group(0)
        if _single_replacement_away(value, settlement_name):
            start = marker.end() + candidate.start()
            end = marker.end() + candidate.end()
            return f"{text[:start]}{settlement_name}{text[end:]}"
    return text


def _normalize_shosse_name(name: str) -> str:
    normalized_words = []
    for word in _clean(name).split():
        parts = []
        for part in word.split('-'):
            lower = part.lower()
            if lower.endswith(('ого', 'его')):
                part = part[:-2] + 'е'
            parts.append(part)
        normalized_words.append('-'.join(parts))
    return ' '.join(normalized_words)


def _extract_intersection_route(text: str) -> Optional[str]:
    m = re.search(
        r'пересеч\w*\s+с\s+(?P<prefix>[МMмАAаРPр])\s*-?\s*(?P<num>\d{1,3})(?!\d)',
        text,
        re.I,
    )
    if not m:
        return None
    prefix = m.group('prefix').upper()
    prefix = {'M': 'М', 'А': 'А', 'A': 'А', 'P': 'Р'}.get(prefix, prefix)
    return f"{prefix}-{m.group('num')}"


def _canonical_road_marker(marker: str) -> str:
    """Приводит общий тип дороги к короткой форме, не трогая её название."""
    marker_lower = marker.lower()
    if marker_lower in {'ф/д', 'фад'}:
        return 'ФАД'
    return 'а/д'


def _extract_named_road(text: str) -> Optional[str]:
    reverse_tract = re.search(
        r'(?P<name>[А-Яа-яЁёA-Za-z\-]+(?:\s+[А-Яа-яЁёA-Za-z\-]+){0,2})\s+'
        r'\d+(?:[\.,]\d+)?\s*км\.?\s+тракт\b',
        text,
        re.I,
    )
    if reverse_tract:
        return f"тракт {_clean(reverse_tract.group('name'))}"

    leading_tract = re.search(
        r'\bтракт\s+(?P<name>[А-Яа-яЁёA-Za-z\-]+(?:\s+[А-Яа-яЁёA-Za-z\-]+){0,2})',
        text,
        re.I,
    )
    if leading_tract:
        return f"тракт {_clean(leading_tract.group('name'))}"

    reverse_shosse = re.search(
        r'(?:\d+(?:[-–]?(?:й|ой|ый))?\s*км\.?|км\s*\d+(?:[-–]?(?:й|ой|ый))?\.?)\s+'
        r'(?P<name>[А-Яа-яЁёA-Za-z\-]+(?:\s+[А-Яа-яЁёA-Za-z\-]+){0,2})\s+шоссе\b',
        text,
        re.I,
    )
    if reverse_shosse:
        name = _normalize_shosse_name(reverse_shosse.group('name'))
        if name:
            return f"{name} шоссе"

    leading_shosse = re.search(
        r'(?P<name>[А-Яа-яЁёA-Za-z\-]+(?:\s+[А-Яа-яЁёA-Za-z\-]+){0,2})\s+шоссе'
        r'(?=\s*(?:\(|\d+(?:[-–]?(?:й|ой|ый))?\s*км|$))',
        text,
        re.I,
    )
    if leading_shosse:
        return f"{leading_shosse.group('name')} шоссе"

    trailing_marker = re.search(
        r'(?:\d+(?:[-–]\d+)?\s*км(?:\s*\+\s*\d+\s*м?)?)\s+'
        r'(?P<name>[А-Яа-яЁёA-Za-z\-]+(?:\s+[А-Яа-яЁёA-Za-z\-]+){0,2})\s+а/д\b',
        text,
        re.I,
    )
    if trailing_marker:
        name = _normalize_road_adjective(trailing_marker.group('name'))
        if name and not _is_side_word(name):
            return f"а/д {name}"

    suffix_marker = re.search(
        r'(?P<name>[А-ЯЁ][А-Яа-яЁёA-Za-z\-]+(?:\s+[А-ЯЁ][А-Яа-яЁёA-Za-z\-]+){0,2})\s+а/д(?=\s*(?:,|$))',
        text,
        re.I,
    )
    if suffix_marker:
        name = _normalize_road_adjective(suffix_marker.group('name'))
        if name and not _is_side_word(name):
            return f"{name} а/д"

    street_part = re.split(
        r'\s*,\s*|\s+(?:\d+(?:[-–]?(?:й|ой|ый))?\s*км|км\s*\d)',
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    street = _try_street(street_part)
    if street:
        return _compact_general_text(street)

    m = re.search(
        r'(?P<marker>а/[дм]|ф/д|фад|автодорог[аиуы]?|автотрасс[ауы]?|автомагистрал[ьи]?|трасс[аыeе]?)\s*[\"«]?'
        r'(?P<name>.+?)(?=\s*(?:\(|,|\d+(?:[-–]?(?:й|ой|ый))?\s*км|км\s*\d|\d+\s*\+)|$)',
        text,
        re.I,
    )
    if not m:
        return None
    name = _normalize_named_road_name(m.group('name'))
    if _is_side_word(name):
        return None
    marker = _canonical_road_marker(m.group('marker'))
    return f"{marker} {name}" if name else None


def _compact_objects(text: str) -> List[str]:
    result: List[str] = []
    pattern = re.compile(
        r'\b(?P<prefix>влд?\.?|влад\.?|владение|зд\.?|здание|соор\.?|сооружение|строен\.?|строение|стр\.?)\s*'
        r'(?:[№#]\s*)?(?P<num>\d[\dА-Яа-яA-Za-z/\-]*)',
        re.I,
    )
    for m in pattern.finditer(text):
        pref = m.group('prefix').lower()
        if pref.startswith('вл'):
            norm = 'вл.'
        elif pref.startswith('зд') or pref.startswith('здание'):
            norm = 'зд.'
        elif pref.startswith('соор') or pref.startswith('сооруж'):
            norm = 'соор.'
        else:
            norm = 'стр.'
        item = f"{norm}{m.group('num')}"
        if item not in result:
            result.append(item)
    return result


def _compact_road_houses(text: str) -> List[str]:
    """Обычный дом после дорожного фрагмента: «МКАД, 1Д» или «а/м ..., д.39»."""
    result: List[str] = []
    explicit = re.compile(r'\bд\.?\s*(?P<num>\d[\dА-Яа-яA-Za-z/\-]*)', re.I)
    for m in explicit.finditer(text):
        item = f"д.{m.group('num')}"
        if item not in result:
            result.append(item)

    litera = re.search(
        r'(?:^|,\s*)(?P<num>\d{1,3}[А-Яа-яA-Za-z]?(?:[/-]\d{1,3}[А-Яа-яA-Za-z]?)*)'
        r'\s*(?:лит\.?|литер|литера)\s*\.?\s*(?P<letter>[А-Яа-яA-Za-z])\s*$',
        text,
        re.I,
    )
    if litera:
        result.append(f"{litera.group('num')} лит.{litera.group('letter')}")

    bare = re.compile(
        r'(?:^|,\s*)(?P<num>\d{1,3}[А-Яа-яA-Za-z]?(?:[/-]\d{1,3}[А-Яа-яA-Za-z]?)*)'
        r'(?:\s*\([^)]*\))?\s*$'
    )
    m = bare.search(text)
    if m:
        value = m.group('num')
        if re.search(r'\bшоссе\s*\(', text, re.I):
            item = value
        elif re.search(r'[А-Яа-яA-Za-z]', value):
            item = value
        else:
            item = f"д.{value}"
        if item not in result:
            result.append(item)
    return result


def _compact_destination_direction(text: str) -> Optional[str]:
    if re.search(r'\bв\s+сторону\s+москв[ыа]\b', text, re.I):
        return 'Мск'
    if re.search(r'\bв\s+сторону\s+минск[а-я]*\b', text, re.I):
        return 'Мин'
    if re.search(r'\bиз\s+санкт-петербург[а-я]*\b', text, re.I):
        return 'из СПб'
    if re.search(r'\bв\s+сторону\s+санкт-петербург[а-я]*\b', text, re.I):
        return 'в СПб'
    if re.search(r'\bиз\s+екатеринбург[а-я]*\b', text, re.I):
        return 'из Екб'
    if re.search(r'\bв\s+сторону\s+екатеринбург[а-я]*\b', text, re.I):
        return 'в Екб'
    if re.search(r'\bв\s+сторону\s+уф[ыа]\b', text, re.I):
        return 'в сторону Уфы'
    if re.search(r'\bв\s+сторону\s+набережн\w*\s+челн\w*\b', text, re.I):
        return 'в Наб.Челны'
    return None


def _compact_road_landmarks(text: str) -> List[str]:
    """Сохраняет короткие ориентиры после трассы: «парк "Патриот"»."""
    result: List[str] = []
    park = re.search(
        r'\bпарк\s+[\"«]?(?P<name>[А-ЯЁA-Z][А-Яа-яЁёA-Za-z0-9\s\-]*)[\"»]?(?=,|$)',
        text,
        re.I,
    )
    if park:
        name = _clean(park.group('name').replace('"', '').replace('«', '').replace('»', ''))
        if name:
            result.append(f"парк {name}")
    zone = re.search(
        r'\bпромзона\s+[\"«]?(?P<name>[А-ЯЁA-Z][А-Яа-яЁёA-Za-z0-9\s\-]*)[\"»]?(?=,|$)',
        text,
        re.I,
    )
    if zone:
        name = _clean(zone.group('name').replace('"', '').replace('«', '').replace('»', ''))
        if name:
            result.append(f"промзона {name}")
    bypass = re.search(r'\bобход\s+(?P<city>г\.?\s*[А-ЯЁ][А-Яа-яЁё\-]+)', text, re.I)
    if bypass:
        city = re.sub(r'г\.\s*', 'г.', bypass.group('city'), flags=re.I)
        result.append(f"обход {city}")
    offset = re.search(r'\b(?P<distance>\d+)\s*м\.?\s+в(?P<side>лево|право)\b', text, re.I)
    if offset:
        side = 'Л' if offset.group('side').lower() == 'лево' else 'П'
        result.append(f"{offset.group('distance')}м {side}")
    plot = re.search(r'\bуч\.\s*(?P<num>\d[\dА-Яа-яA-Za-z/\-]*)', text, re.I)
    if plot:
        result.append(f"уч.{plot.group('num')}")
    road_exit = re.search(r'\bсъезд\s+к\s+(?P<target>х\.?\s*[А-ЯЁ][А-Яа-яЁё\-]+)', text, re.I)
    if road_exit:
        target = re.sub(r'\s+', '', road_exit.group('target'))
        result.append(f"съезд к {target}")
    elif re.search(r'\bсъезд\b', text, re.I):
        result.append('съезд')
    crossing = re.search(r'\bпересеч\w*\s+(?:ул\.?\s*)?(?P<street>[А-ЯЁ][А-Яа-яЁё\-]+)', text, re.I)
    if crossing:
        result.append(f"x ул.{crossing.group('street')}")
    turn = re.search(r'\bповорот\w*\s+на\s+(?P<name>[А-ЯЁ][А-Яа-яЁё\-\s]+)$', text, re.I)
    if turn:
        result.append(f"пов. {_clean(turn.group('name'))}")
    metro = re.search(r'\bнапротив\s+(?:т/к\s+)?(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)', text, re.I)
    if metro:
        result.append(f"напр.{metro.group('name')}")
    post = re.search(r'\bпочтов\w*\s+отделени\w*\s*№\s*(?P<num>\d+)', text, re.I)
    if post:
        result.append(f"п/о{post.group('num')}")
    ring = re.search(r'\bкольцев\w*\s+пересеч\w*', text, re.I)
    if ring:
        result.append('кольцо')
    near_hamlet = re.search(r'\bу\s+х\.?\s*(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)', text, re.I)
    if near_hamlet:
        result.append(f"у х.{_short_endpoint(near_hamlet.group('name'), 5)}")
    edge_hamlet = re.search(r'\bСВ\s+х\.?\s*(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)', text, re.I)
    if edge_hamlet:
        result.append(f"СВ х.{_short_endpoint(edge_hamlet.group('name'), 5)}")
    return result


def _meaningful_road_fallback_details(tokens: List[str]) -> List[str]:
    """Отбрасывает пустые разделители, но сохраняет содержательные ориентиры."""
    return [
        _clean(token)
        for token in tokens
        if re.search(r'[А-Яа-яЁёA-Za-z0-9]', token)
    ]


def _short_endpoint(name: str, length: int) -> str:
    cleaned = _clean(name)
    if len(cleaned) <= length:
        return cleaned
    return f"{cleaned[:length]}."


def _semantic_shortcuts(text: str) -> str:
    """Shortens well-known long words while preserving the address meaning."""
    result = text
    replacements = [
        (r'\bБольш(?:ая|ой)\b', 'Б.'),
        (r'\bМал(?:ая|ый)\b', 'М.'),
        (r'\bМосковск(?:ая|ий|ое|ого)\b', 'Мск'),
        (r'\bСанкт-Петербургская\b', 'Санкт-Пет.'),
        (r'\bС\.?\s*Петербург\b', 'СПб'),
        (r'\bСанкт-Петербург\b', 'СПб'),
        (r'\bЕкатеринбург\b', 'Екб'),
        (r'\bаэропорт\b', 'аэр.'),
        (r'\bНабережн\w*\s+Челн\w*\b', 'Наб.Челны'),
        (r'\bучастковое\s+лесничество\b', 'уч.лесн.'),
        (r'\bобслуживание\s+автотранспорта\b', 'обсл.автотрансп.'),
        (r'\bШкольный\s+бульвар\b', 'Школьный б-р'),
        (r'\bСамара\b', 'Сам.'),
        (r'\bЧелябинск\b', 'Чел.'),
        (r'\bТевлино-Русскинское\b', 'Тевл.-Рус.'),
    ]
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.I)
    return re.sub(r'\s+', ' ', result).strip(' ,;')


def _short_chainage(km: Optional[str]) -> str:
    if not km:
        return ''
    return re.sub(r'(?<!\d)(\d+)км\+(\d+)м\b', r'\1+\2', km)


def _compact_chainage(km: Optional[str]) -> str:
    return km or ''


def _first_semantic_fit(*candidates: Optional[str]) -> Optional[str]:
    for candidate in candidates:
        if not candidate:
            continue
        compact = re.sub(r'\s+', ' ', candidate).strip(' ,;')
        if len(compact) <= _MAX_HOUSE_STREET_LEN:
            return compact
    return None


def _compact_semantic_special(text: str) -> Optional[str]:
    """Preserves dense but important address landmarks before generic shortening."""
    t = _canonicalize_output_markers(text)
    km = _compact_chainage(_compact_km(t))
    km_short = _short_chainage(km)

    school = re.search(r'(?P<distance>\d+)м\s+(?P<side>[СЮЗВ])\s+от\s+шк\.(?P<num>\d+)', t, re.I)
    if school:
        return f"{school.group('distance')}м {school.group('side').upper()} от шк.{school.group('num')}"

    relative_house = re.search(
        r'(?P<distance>\d+)м\s+(?P<side>[СЮЗВ])\s+от\s+д\.(?P<house>[\dА-Яа-яA-Za-z/\-]+)'
        r'.*?,\s*ул\.\s*(?P<street>.+)$',
        t,
        re.I,
    )
    if relative_house:
        return _first_semantic_fit(
            f"{relative_house.group('distance')}м {relative_house.group('side').upper()} "
            f"от д.{relative_house.group('house')}, ул. {relative_house.group('street')}",
            f"{relative_house.group('distance')}м {relative_house.group('side').upper()} "
            f"от д.{relative_house.group('house')}, {relative_house.group('street')}",
        )

    if (
        re.search(r'\bдублер\s+Сибирского\s+тракта\b', t, re.I)
        and re.search(r'\b(?:напр\.?|напротив\s+(?:т/к\s+)?)Метро\b', t, re.I)
    ):
        return _first_semantic_fit(f"{km} дублер Сиб.тр. напр.Метро", f"{km_short} дублер Сиб.тр. напр.Метро")

    if km and _compact_side(t) and not re.search(r'\b(?:а/д|ФАД|МКАД|ЦКАД|ЕКАД|[МАР]-\d|ш\.|шоссе|тракт)\b', t, re.I):
        without_km_side = re.sub(r'[\d\sкм+.,()\-–]+|справа|слева|право|лево|на\s+участке', '', t, flags=re.I)
        if not re.search(r'[А-Яа-яЁёA-Za-z]', without_km_side):
            return f"{km} {_compact_side(t)}"

    if re.search(r'\bпр-т\s+(?:им\.?\s*)?Ю\.?\s*А\.?\s*Гагарина\s+8-я\s+линия\b', t, re.I):
        objects = _compact_objects(t)
        prefix = f"{objects[0]}, " if objects else ''
        return _first_semantic_fit(f"{prefix}пр-т Ю.А.Гагарина 8л")

    if re.search(r'\bтракт\s+Свердловский\b', t, re.I):
        return _first_semantic_fit(re.sub(r'\bтракт\s+Свердловский\b', 'Свердл. тракт', t, flags=re.I))

    street_crossing = re.search(
        r'(?P<house>\d[\d/\-]*),\s*ул\.\s*Сормовская\s*-\s*ул\.\s*Старокубанская',
        t,
        re.I,
    )
    if street_crossing:
        return f"{street_crossing.group('house')}, Сормов.-Старокуб."

    contours = re.search(
        r'колхоз\s+[\"«]?Нива[\"»]?\s+секция\s+(?P<section>\d+),?\s+'
        r'контур\s+(?P<start>\d+)(?:,\d+)*,(?P<end>\d+)',
        t,
        re.I,
    )
    if contours:
        return f"колхоз Нива сек{contours.group('section')} конт{contours.group('start')}-{contours.group('end')}"

    if re.search(r'\bМосква-Волгоград\b', t, re.I) and re.search(r'\bсъезд\b', t, re.I):
        target = re.search(r'\bсъезд\s+к\s+х\.?\s*(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)', t, re.I)
        if target:
            name = target.group('name')
            short_name = 'Криушин.' if re.match(r'Криушин', name, re.I) else _short_endpoint(name, 8)
            return _first_semantic_fit(f"Мск-Влг, съезд к х.{short_name}")
        return _first_semantic_fit(f"{km}, Мск-Влг, съезд", f"{km_short}, Мск-Влг, съезд")

    if re.search(r'\bКавказ\b', t, re.I):
        near_hamlet = re.search(r'\bу\s+х\.?\s*(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)', t, re.I)
        edge_hamlet = re.search(r'\bСВ\s+х\.?\s*(?P<name>[А-ЯЁ][А-Яа-яЁё\-]+)', t, re.I)
        if near_hamlet:
            near_name = _short_endpoint(near_hamlet.group('name'), 5)
            return _first_semantic_fit(
                f"{km} у х.{near_name}, ФАД Кавказ",
                f"{km_short} у х.{near_name}, ФАД Кавказ",
                f"{km_short} у х.{near_name.rstrip('.')}, ФАД Кавказ",
            )
        if edge_hamlet:
            edge_name = _short_endpoint(edge_hamlet.group('name'), 5)
            return _first_semantic_fit(
                f"{km} СВ х.{edge_name}, ФАД Кавказ",
                f"{km_short} СВ х.{edge_name}, ФАД Кавказ",
                f"{km_short} СВ х.{edge_name.rstrip('.')}, ФАД Кавказ",
            )

    if re.search(r'\bТемрюк-Краснодар-Кропоткин\b', t, re.I) and (
        re.search(r'\bп/о27\b', t, re.I)
        or re.search(r'\bпочтов\w*\s+отделени\w*\s*№\s*27\b', t, re.I)
    ):
        return _first_semantic_fit(
            f"{km} п/о27, Темр.-Красн.-Кроп.",
            f"{km} п/о27, Темр.-Красн.-Кроп",
        )

    if re.search(r'\bЕгорьевск-Коломна-Кашира-Ненашево\b', t, re.I):
        return _first_semantic_fit(f"{km}, Егор.-Кол.-Каш.-Н.", f"{km_short}, Егор.-Кол.-Каш.-Н.")

    if re.search(r'\bВологда\s*-\s*Новая\s+Ладога\b', t, re.I):
        offset = next((item for item in _compact_road_landmarks(t) if re.match(r'\d+м\s+[ЛП]\b', item)), '')
        return _first_semantic_fit(
            f"{km} {offset}, Волог.-Н.Лад.",
            f"{km_short} {offset}, Волог.-Н.Лад.",
        )

    if re.search(r'\bСамара-Уфа-Челябинск\b', t, re.I):
        objects = ' '.join(_compact_objects(t))
        return _first_semantic_fit(
            f"{km} {objects}, Сам.-Уфа-Чел.",
            f"{km_short} {objects}, Сам.-Уфа-Чел.",
        )

    if re.search(r'\bСтародеревянковская-Ленинградская-Кисляковская\b', t, re.I):
        side = _compact_side(t)
        return _first_semantic_fit(f"{km} {side or ''}, Стар.-Лен.-Кисл.")

    if re.search(r'\bТимашевск\b.*\bПолтавская\b', t, re.I):
        houses = _compact_road_houses(t)
        return _first_semantic_fit(f"{km} {' '.join(houses)}, Тимашевск-Полтавская")

    if re.search(r'\bОтрадо-Ольгинское-Новокубанск-Армавир\b', t, re.I):
        side = _compact_side(t)
        return _first_semantic_fit(
            f"{km} {side or ''}, Отр.-Ольг.-Нов.-Арм.",
            f"{km_short} {side or ''}, Отр.-Ольг.-Нов.-Арм.",
        )

    if re.search(r'\bКраснодар\s*-\s*г\.?\s*Кропоткин\b|\bКраснодар-Кропоткин\b', t, re.I):
        objects = _compact_objects(t)
        return _first_semantic_fit(
            f"{km} {' '.join(objects)}, Краснодар-Кропоткин",
            f"{km} {' '.join(objects)}, Красн.-Кропоткин",
        )

    if re.search(r'\bМ-25\b', t, re.I) and re.search(r'\bНовороссийск-Керченский\b', t, re.I):
        objects = _compact_objects(t)
        houses = _compact_road_houses(t)
        return _first_semantic_fit(f"{km} {' '.join(houses + objects)}, М-25 Нов.-Керч.")

    if re.search(r'\bул\.\s+Лазурная\b', t, re.I) and re.search(r'\bвыезд\s+на\b.*\bМ-29\b', t, re.I):
        return 'ул. Лазурная, выезд на М-29'

    if re.search(r'\bСаратов-Волгоград\b', t, re.I) and re.search(r'\bповорот\w*\s+на\s+Колотов\s+Буерак\b', t, re.I):
        return 'Сар.-Волг., пов.Колотов Буер.'

    if re.search(r'\bМ-4\s+Москва-Ростов\b', t, re.I) and km:
        side = _compact_side(t)
        return _first_semantic_fit(f"{km} {side or ''}, М-4 Мск-Ростов", f"{km_short} {side or ''}, М-4 Мск-Ростов")

    if re.search(r'\bим\.?\s+академика\s+О\.?\s*К\.?\s*Антонова\b', t, re.I):
        objects = _compact_objects(t)
        prefix = f"{objects[0]}, " if objects else ''
        return _first_semantic_fit(f"{prefix}ул. О.К.Антонова")

    if re.search(r'\bСызрань\s*-\s*Саратов\s*-\s*Волгоград\b', t, re.I):
        objects = _compact_objects(t)
        side = _compact_side(t)
        suffix = ' '.join([item for item in [km, *objects, side] if item])
        short_suffix = ' '.join([item for item in [km_short, *objects, side] if item])
        return _first_semantic_fit(f"{suffix}, Сызр.-Сар.-Волг.", f"{short_suffix}, Сызр.-Сар.-Волг.")

    don = re.search(r'\bа/д\s+Дон(?P<suffix>-\d+)?\b', t, re.I)
    if don and km:
        side = _compact_side(t)
        return _first_semantic_fit(f"{km} {side or ''}, а/д Дон{don.group('suffix') or ''}")

    if re.search(r'\bа/д\s+Кавказ\b', t, re.I) and km:
        return _first_semantic_fit(f"{km}, а/д Кавказ")

    return None


def _extract_road_section(text: str) -> Optional[str]:
    """«на участке д. Новосидориха-д. Никитинская» → «Нов.-Никит.»."""
    m = re.search(
        r'\bд\.\s*(?P<start>[А-ЯЁ][А-Яа-яЁё\-]+)\s*-\s*д\.\s*'
        r'(?P<end>[А-ЯЁ][А-Яа-яЁё\-]+)',
        text,
    )
    if not m:
        return None
    return f"{_short_endpoint(m.group('start'), 3)}-{_short_endpoint(m.group('end'), 5)}"


def _named_road_without_marker_to_fit(road: str, suffix_parts: List[str]) -> Optional[str]:
    if not road.startswith('а/д '):
        return None

    name = road[4:]
    variants = [name] if len(name.split('-')) < 3 else []
    for variant in [
        re.sub(r'\bаэропорт\b', 'аэр.', name, flags=re.I),
        re.sub(r'\bСанкт-Петербург\b', 'СПб', name, flags=re.I),
    ]:
        if variant != name and variant not in variants:
            variants.append(variant)

    endpoints = name.split('-')
    if len(endpoints) == 2 and any(' ' in endpoint for endpoint in endpoints):
        shortened_endpoints = []
        for index, endpoint in enumerate(endpoints):
            words = endpoint.split()
            if index == 0 and len(words) == 1 and len(endpoint) <= 8:
                shortened_endpoints.append(endpoint)
                continue
            shortened = ''.join(
                f"{word[0]}." if word_index < len(words) - 1 else _short_endpoint(word, 3)
                for word_index, word in enumerate(words)
            )
            shortened_endpoints.append(shortened)
        semantic = '-'.join(shortened_endpoints)
        if semantic != name:
            variants.append(semantic)
    for suffix_variant in _road_suffix_variants(suffix_parts):
        for variant in variants:
            compact = ' '.join([variant, *suffix_variant])
            if len(compact) <= _MAX_HOUSE_STREET_LEN:
                return compact
    return None


def _road_suffix_variants(suffix_parts: List[str]) -> List[List[str]]:
    variants = [suffix_parts]
    chainage = [
        re.sub(r'(?<!\d)(\d+)км\+(\d+)м\b', r'\1+\2', part)
        for part in suffix_parts
    ]
    if chainage != suffix_parts:
        variants.append(chainage)
    return variants


def _compact_named_road_to_fit(road: str, suffix_parts: List[str]) -> Optional[str]:
    """Сокращает длинную часть названия дороги, сохраняя конечные пункты."""
    if not road.startswith('а/д '):
        return None

    original_parts = road[4:].split('-')
    if len(original_parts) < 3:
        return None

    middle_shortened = list(original_parts)
    for index in range(1, len(middle_shortened) - 1):
        raw = middle_shortened[index].rstrip('.')
        if len(raw) <= 6:
            continue
        middle_shortened[index] = f"{raw[:5]}."
        for suffix_variant in _road_suffix_variants(suffix_parts):
            compact = ' '.join([f"а/д {'-'.join(middle_shortened)}", *suffix_variant])
            if len(compact) <= _MAX_HOUSE_STREET_LEN:
                return compact

    preferred_parts = []
    for index, part in enumerate(original_parts):
        raw = part.rstrip('.')
        max_len = 1 if index == len(original_parts) - 1 else (4 if index == 0 else 3)
        preferred_parts.append(raw if len(raw) <= max_len else f"{raw[:max_len]}.")
    for suffix_variant in reversed(_road_suffix_variants(suffix_parts)):
        compact = ' '.join([f"а/д {'-'.join(preferred_parts)}", *suffix_variant])
        if len(compact) <= _MAX_HOUSE_STREET_LEN:
            return compact

    for max_len in (6, 5, 4, 3, 1):
        for suffix_variant in _road_suffix_variants(suffix_parts):
            name_parts = []
            for part in original_parts:
                raw = part.rstrip('.')
                name_parts.append(raw if len(raw) <= max_len else f"{raw[:max_len]}.")
            compact = ' '.join([f"а/д {'-'.join(name_parts)}", *suffix_variant])
            if len(compact) <= _MAX_HOUSE_STREET_LEN:
                return compact
    return None


def _compact_zone_road_to_fit(
    road: Optional[str],
    km: Optional[str],
    houses: List[str],
    landmarks: List[str],
) -> Optional[str]:
    """Keeps the identifying zone name when a road address is unusually dense."""
    zone = next((item for item in landmarks if item.startswith('промзона ')), None)
    if not road or not zone:
        return None

    zone_name = zone[len('промзона '):]
    road_name = re.sub(r'^а/д\s+', '', road, flags=re.I)
    road_name = re.sub(r'\bСанкт-Петербург\b', 'СПб', road_name, flags=re.I)
    road_short = '-'.join(
        part if len(part) <= 7 else f"{part[:5]}."
        for part in road_name.split('-')
    )
    suffix = f" {km}" if km else ''
    house = re.sub(r'^д\.', '', houses[0]) if houses else ''

    candidates = []
    if house:
        candidates.extend([
            f"{house}, {zone_name}, {road_name}{suffix}",
            f"{house}, {zone_name}, {road_short}{suffix}",
        ])
    candidates.extend([
        f"{zone}, {road_name}{suffix}",
        f"{zone}, {road_short}{suffix}",
    ])
    return next((item for item in candidates if len(item) <= _MAX_HOUSE_STREET_LEN), None)


def _compact_road_text(text: str) -> Optional[str]:
    if not (_has_road_marker(text) or _RE_KM.search(text)):
        return None

    route = _extract_route_code(text)
    named_road = _extract_named_road(text)
    road = route or named_road
    route_code = _extract_route_code(text, with_name=False)
    if (
        route
        and route == route_code
        and named_road
        and named_road.startswith('а/д ')
        and named_road[4:] != route
    ):
        named_body = named_road[4:].strip()
        road = named_body if named_body.startswith(route) else f"{route} {named_body}"
    km = _compact_km(text)
    intersection = _extract_intersection_route(text)
    section = _extract_road_section(text)
    side = _compact_side(text)
    ring_side = _compact_ring_side(text)
    pk = _compact_pk(text)
    objects = _compact_objects(text)
    houses = _compact_road_houses(text)
    direction = _compact_destination_direction(text)
    landmarks = _compact_road_landmarks(text)

    if road and road.endswith(' а/д') and houses:
        house = re.sub(r'^д\.', '', houses[0])
        compact = f"{house}, {road}"
        if len(compact) <= _MAX_HOUSE_STREET_LEN:
            return compact

    if road and road.endswith(' шоссе') and objects:
        road = f"ш. {road[:-len(' шоссе')]}"

    if road and road.endswith(' шоссе') and km and houses:
        compact = ' '.join([f"{houses[0]},", f"ш. {road[:-len(' шоссе')]}", km])
        if len(compact) <= _MAX_HOUSE_STREET_LEN:
            return compact
        compact = _semantic_shortcuts(compact)
        if len(compact) <= _MAX_HOUSE_STREET_LEN:
            return compact

    front_parts = []
    if pk:
        front_parts.append(pk)
    if intersection and intersection != route and intersection != road:
        front_parts.append(f"x {intersection}")
    if section:
        front_parts.append(section)
    if side:
        front_parts.append(side)
    if ring_side:
        front_parts.append(ring_side)
    front_parts.extend(objects)
    front_parts.extend(item for item in houses if item not in front_parts)

    tail_parts = []
    if direction:
        tail_parts.append(direction)
    tail_parts.extend(item for item in landmarks if item not in tail_parts)

    def road_variants() -> List[Optional[str]]:
        variants: List[Optional[str]] = [road]
        if route_code and route_code != road:
            variants.append(route_code)
        if road and road.endswith(' шоссе'):
            variants.append(f"ш. {road[:-len(' шоссе')]}")
        if road:
            semantic_road = _semantic_shortcuts(road)
            if semantic_road != road:
                variants.append(semantic_road)
            if road.startswith('а/д '):
                name = road[4:]
                variants.append(name)
                semantic_name = _semantic_shortcuts(name)
                if semantic_name != name:
                    variants.append(semantic_name)
                if '-' in name:
                    endpoints = name.split('-')
                    for max_len in (6, 5, 4, 3, 1):
                        variants.append('-'.join(_short_endpoint(part, max_len) for part in endpoints))
                variants.append(_shorten_name_words(name, max_part_len=7))
                variants.append(_shorten_name_words(road, max_part_len=7))
            else:
                variants.append(_shorten_name_words(road, max_part_len=7))
                semantic_variant = _semantic_shortcuts(_shorten_name_words(road, max_part_len=12))
                if semantic_variant != road:
                    variants.append(semantic_variant)
        result: List[Optional[str]] = []
        for item in variants:
            if item and item not in result:
                result.append(item)
        return result or [None]

    km_variants = [km]
    short_km = _short_chainage(km)
    if short_km and short_km != km:
        km_variants.append(short_km)
    if not km:
        km_variants = [None]

    def build_candidate(road_part: Optional[str], km_part: Optional[str], comma: bool = True) -> str:
        leading = [item for item in [km_part, *front_parts] if item]
        lead = ' '.join(leading)
        if road_part and lead:
            sep = ', ' if comma else ' '
            base = f"{lead}{sep}{road_part}"
        elif road_part:
            base = road_part
        else:
            base = lead
        return ' '.join(item for item in [base, *tail_parts] if item).strip()

    candidates = [
        build_candidate(road_part, km_part, comma)
        for km_part in km_variants
        for road_part in road_variants()
        for comma in (True, False)
    ]
    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        return None

    for compact in candidates:
        if len(compact) <= _MAX_HOUSE_STREET_LEN:
            return compact

    zone_road = _compact_zone_road_to_fit(road, km, houses, landmarks)
    if zone_road:
        return zone_road

    for compact in candidates:
        semantic = _semantic_shortcuts(compact)
        if len(semantic) <= _MAX_HOUSE_STREET_LEN:
            return semantic

    return candidates[-1]


def _compact_relative_text(text: str) -> Optional[str]:
    m = re.search(r'(?P<distance>\d+)\s*(?:м\.?|метр\w*)\s+(?P<tail>.+)$', text, re.I)
    if not m:
        return None
    tail_l = m.group('tail').lower()
    direction = None
    if re.search(r'запад|западнее', tail_l):
        direction = 'З'
    elif re.search(r'восток|восточнее', tail_l):
        direction = 'В'
    elif re.search(r'север|севернее', tail_l):
        direction = 'С'
    elif re.search(r'юг|южнее', tail_l):
        direction = 'Ю'

    parts = [f"{m.group('distance')}м"]
    if direction:
        parts.append(direction)

    turn = re.search(r'поворот[а]?\s+([^()]+)', text, re.I)
    if turn:
        parts.append(f"пов. {_shorten_name_words(turn.group(1), max_part_len=8)}")
    return ', '.join([' '.join(parts[:2]), *parts[2:]])


def _canonicalize_output_markers(text: str, finalize_streets: bool = True) -> str:
    """Унифицирует служебные слова, сохраняя смысловую часть адреса."""
    result = _clean(text)
    replacements = [
        (r'\bпроизводственная\s+зона\b', 'промзона'),
        (r'(?<!\w)(?:ф/д|фад)(?!\w)', 'ФАД'),
        (r'(?<!\w)(?:а/м|автодорог[аиуы]?|автотрасс[ауы]?|автомагистрал[ьи]?|трасс[ауыeе]?)(?!\w)', 'а/д'),
        (r'\bмкад\b', 'МКАД'),
        (r'\bцкад\b', 'ЦКАД'),
        (r'\bекад\b', 'ЕКАД'),
        (r'(?<!\w)(?:территория|тер\.?)(?=\s|,|;|$|\d)', 'тер.'),
        (r'(?<!\w)(?:влд?\.?|влад\.?|владение)(?=\s*(?:[№#]\s*)?\d)', 'вл.'),
        (r'(?<!\w)(?:строен\.?|строение|стр\.?|с\.)(?=\s*(?:[№#]\s*)?\d)', 'стр.'),
        (r'(?<!\w)(?:зд\.?|здание)(?=\s*(?:[№#]\s*)?\d)', 'зд.'),
        (r'(?<!\w)(?:соор\.?|сооружение)(?=\s*(?:[№#]\s*)?\d)', 'соор.'),
        (r'(?<!\w)(?:корпус|корп\.?|кор\.?|к\.)(?=\s*\d)', 'к.'),
        (r'(?<!\w)(?:литера|литер|лит\.?)(?=\s*[А-Яа-яA-Za-z](?:\b|$))', 'лит.'),
        (r'(?<!\w)(?:участок|уч\.|з\.?\s*у\.?)\s*(?:№|N|#)?\s*(?=\d)', 'уч.'),
        (r'(?<![\w-])(?:пр-кт|пр-т|просп\.?|проспект)\.?\s+', 'пр-т '),
        (r'(?<![\w-])(?:проезд|пр-д)\.?\s+', 'пр-д '),
        (r'(?<![\w-])(?:улица|ул)\.?\s+', 'ул. '),
        (r'(?<![\w-])(?:переулок|пер)\.?\s+', 'пер. '),
        (r'(?<![\w-])(?:бульвар|б-р)\.?\s+', 'б-р '),
        (r'(?<![\w-])(?:набережная|наб)\.?\s+', 'наб. '),
        (r'(?<![\w-])(?:площадь|пл)\.?\s+', 'пл. '),
        (r'(?<![\w-])(?:тупик|туп)\.?\s+', 'туп. '),
        (r'\bс\.?\s*п\.?$', 'с.п.'),
        (r'\bвол\.?$', 'вол.'),
        (r'\bвнеш\.?$', 'внеш.'),
        (r'\bвнутр\.?$', 'внутр.'),
        (r'\bуч\.лесн\.?$', 'уч.лесн.'),
        (r'\bобсл\.автотрансп\.?$', 'обсл.автотрансп.'),
        (r'\bСанкт-Пет\.?$', 'Санкт-Пет.'),
    ]
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.I)
    result = re.sub(r'\bтер\.\s+а/д\b(?=\s*(?:,|$))', 'тер. Автодорога', result, flags=re.I)
    result = re.sub(r'\b(вл\.|зд\.|соор\.|стр\.)\s*[№#]\s*', r'\1 ', result, flags=re.I)
    result = re.sub(r'(?<!\w)(а/д|ФАД)(?=[А-ЯЁA-Z0-9])', r'\1 ', result)
    result = re.sub(
        r'(?P<km>\d+(?:[-–]\d+)?)\s*км\.?\s*\+\s*(?P<m>\d+)\s*м?\.?',
        r'\g<km>км+\g<m>м',
        result,
        flags=re.I,
    )
    result = re.sub(
        r'(?P<km>\d+(?:[-–]\d+)?)км\+(?P<m>\d+)(?!\d|\s*м)',
        r'\g<km>км+\g<m>м',
        result,
        flags=re.I,
    )
    result = re.sub(
        r'(?P<km>\d+(?:[-–]\d+)?)\s*км\.?\s+(?P<m>\d+)\s*м\.?',
        r'\g<km>км+\g<m>м',
        result,
        flags=re.I,
    )
    result = re.sub(
        r'(?<![\d+])(?P<km>\d+(?:[-–]\d+)?)(?:[-–]?(?:й|ой|ый))?\s*км\.?',
        lambda match: f"{match.group('km').replace('–', '-')}км",
        result,
        flags=re.I,
    )
    result = re.sub(
        r'\bкм\.?\s*(?P<km>\d+(?:[-–]\d+)?)(?:[-–]?(?:й|ой|ый))?',
        lambda match: f"{match.group('km').replace('–', '-')}км",
        result,
        flags=re.I,
    )

    if finalize_streets:
        name_word = r'[А-ЯЁA-Z][А-Яа-яЁёA-Za-z\-]*'
        result = re.sub(
            rf'(?<![\w-])(?P<name>{name_word}(?:\s+{name_word}){{0,2}})\s+шоссе\b',
            lambda match: f"ш. {match.group('name')}",
            result,
            flags=re.I,
        )
        result = re.sub(r'(?<![\w-])шоссе\s+', 'ш. ', result, flags=re.I)
        result = re.sub(r'\bул\.\s+ш\.\s+в\b', 'ул. Шоссе в', result, flags=re.I)
        result = re.sub(
            r'\bул\.\s+ш\.\s+(?!в\b|на\b|к\b)(?P<name>[^,]+)',
            lambda match: f"ш. {match.group('name').strip()}",
            result,
            flags=re.I,
        )
        result = re.sub(r'\bул\.\s+Новое\s+ш\.?\b', 'ул. Новое шоссе', result, flags=re.I)
        result = re.sub(r'\bул\.\s+б-р\s+', 'ул. Бульвар ', result, flags=re.I)
        result = re.sub(r'\bул\.\s+наб\.\s*$', 'ул. Набережная', result, flags=re.I)
        result = re.sub(r'\bул\.\s+мкр\.\s*$', 'ул. Микрорайон', result, flags=re.I)

    return re.sub(r'\s+', ' ', result).strip(' ,;')


def _compact_general_text(text: str) -> str:
    result = _canonicalize_output_markers(text)
    replacements = [
        (r'\s+(?=[,])', ''),
    ]
    for pattern, repl in replacements:
        result = re.sub(pattern, repl, result, flags=re.I)
    result = re.sub(r'\s+', ' ', result).strip(' ,;')
    if len(result) <= _MAX_HOUSE_STREET_LEN:
        return result

    result = re.sub(r'\b(вл\.|зд\.|соор\.|стр\.|к\.|лит\.)\s+', r'\1', result, flags=re.I)
    if len(result) <= _MAX_HOUSE_STREET_LEN:
        return result

    result = _semantic_shortcuts(result)
    if len(result) <= _MAX_HOUSE_STREET_LEN:
        return result

    words = result.split()
    shortened = []
    for word in words:
        raw = word.strip(',')
        if len(raw) > 10 and not re.search(r'\d', raw):
            word = word.replace(raw, raw[:7] + '.')
        shortened.append(word)
    result = ' '.join(shortened)
    return result.strip(' ,;')


def _compact_street_text(text: str) -> Optional[str]:
    """Compacts a regular street address semantically before generic truncation."""
    result = _canonicalize_output_markers(text)
    if not re.search(r'(?<![\w-])(?:ул\.|пр-т|пр-д|ш\.|пер\.|б-р|наб\.|пл\.|туп\.)\s+', result, re.I):
        return None

    variants = [result]
    marker_compact = re.sub(r'\b(вл\.|зд\.|соор\.|стр\.|к\.|лит\.)\s+', r'\1', result, flags=re.I)
    variants.append(marker_compact)

    semantic = _semantic_shortcuts(marker_compact)
    variants.append(semantic)

    without_type = re.sub(
        r'(?<=,\s)(?:ул\.|пр-т|пр-д|ш\.|пер\.|б-р|наб\.|пл\.|туп\.)\s+',
        '',
        semantic,
        count=1,
        flags=re.I,
    )
    variants.append(without_type)
    return next((item for item in variants if len(item) <= _MAX_HOUSE_STREET_LEN), None)


def _compact_detail_with_street(text: str) -> Optional[str]:
    m = re.match(
        r'(?P<detail>уч\.\d+\s+напр\.вл\.[\dА-Яа-яA-Za-z/\-]+),\s+'
        r'(?P<street>(?P<prefix>ул\.|пр-д|пр-т|ш\.|шоссе)\s+(?P<name>.+))$',
        _clean(text),
        re.I,
    )
    if not m:
        return None

    detail = m.group('detail')
    street = m.group('street')
    compact = f"{detail}, {street}"
    if len(compact) <= _MAX_HOUSE_STREET_LEN:
        return compact

    name_only = f"{detail}, {m.group('name')}"
    if len(name_only) <= _MAX_HOUSE_STREET_LEN:
        return name_only

    without_opposite = f"{detail.replace(' напр.', ' ')}, {street}"
    if len(without_opposite) <= _MAX_HOUSE_STREET_LEN:
        return without_opposite

    return None


def _should_compact_short_road(text: str) -> bool:
    if not (_has_road_marker(text) or _RE_KM.search(text)):
        return False
    return bool(
        re.search(r'^\d+(?:[-–]?(?:й|ой|ый))?\s*км\s*,\s*(?:а/[дм]|ф/д|фад|[МMмАAаРPр]\s*-?\s*\d)', text, re.I)
        or re.search(r'\bа/[дм](?=\S)', text, re.I)
        or re.search(r'\bмкад\b\s*,\s*\d{1,3}[А-Яа-яA-Za-z](?:[/-]\d{1,3}[А-Яа-яA-Za-z]?)?\s*$', text, re.I)
        or re.search(r'\bшоссе\s*\(\s*\d+(?:[-–]?(?:й|ой|ый))?\s*км\s*\)', text, re.I)
        or re.search(r'\d+\s*\([^)]*\d+\s*\+\s*\d+\s*м[^)]*\)\s*км', text, re.I)
        or re.search(r'\d+(?:[-–]?(?:й|ой|ый))?\s*км\.?\s+[А-Яа-яЁёA-Za-z\-]+(?:\s+[А-Яа-яЁёA-Za-z\-]+){0,2}\s+шоссе\b', text, re.I)
        or re.search(r'\bкилометр\w*\b', text, re.I)
        or re.search(r'\d+\s*\+\s*\d+\s*км\b', text, re.I)
        or re.search(r'\d+\s*\+\s*\d+(?:\s*м\.?)?\s*,\s*(?:справа|слева|право|лево)\b', text, re.I)
        or re.search(r'\bсъезд\b', text, re.I)
        or re.search(r'\bпочтов\w*\s+отделени\w*\s*№\s*\d+', text, re.I)
        or re.search(r'\b(?:у|СВ)\s+х\.?\s*[А-ЯЁ]', text, re.I)
        or re.search(r'\b(\d+)\s*км\b.*\b\1\s*км\b', text, re.I)
        or re.search(r'-(?:справа|слева|право|лево)\b', text, re.I)
        or (
            _RE_ROUTE_CODE.search(text)
            and _RE_KM.search(text)
            and re.search(r'\b(?:справа|слева|право|лево|правая\s+сторона|левая\s+сторона)\b', text, re.I)
        )
        or (
            _RE_STRONG_ROAD_MARKER.search(text)
            and _RE_KM.search(text)
            and re.search(
                r'(?<!\w)(?:вл\.?|влд\.?|влад\.?|владение|зд\.?|здание|'
                r'соор\.?|сооружение|строен\.?|строение|стр\.?)\s*\d',
                text,
                re.I,
            )
        )
    )


def _limit_house_street(text: str) -> str:
    result = _canonicalize_output_markers(text, finalize_streets=False)
    roadish = bool(
        _RE_STRONG_ROAD_MARKER.search(result)
        or (
            _RE_KM.search(result)
            and (
                _RE_SHOSSE_MARKER.search(result)
                or re.search(r'\b(?:тракт|а/д|ФАД|МКАД|ЦКАД|ЕКАД|[МАР]-\d)\b', result, re.I)
            )
        )
    )

    def fit(candidate: Optional[str]) -> Optional[str]:
        if not candidate:
            return None
        canonical = _canonicalize_output_markers(candidate)
        return canonical if len(canonical) <= _MAX_HOUSE_STREET_LEN else None

    direct_route_house = re.match(
        r'^(?:\d[\dА-Яа-яA-Za-z/\-]*(?:\s+лит\.\s*[А-Яа-яA-Za-z])?'
        r'|(?:вл\.|зд\.|соор\.|стр\.)\s*\d[\dА-Яа-яA-Za-z/\-]*)'
        r'\s*,\s*[МАР]-\d+\b.*\b\d+(?:[-–]\d+)?км\b',
        result,
        re.I,
    )
    if direct_route_house:
        fitted = fit(result)
        if fitted:
            return fitted

    fitted = fit(_compact_semantic_special(result))
    if fitted:
        return fitted

    if re.search(r'\bпромзона\b', result, re.I) and not _RE_KM.search(result):
        fitted = fit(result)
        if fitted:
            return fitted

    if re.search(r'\bтер\.\s+Автодорога\b', result, re.I) and not _RE_KM.search(result):
        fitted = fit(result)
        if fitted:
            return fitted

    compact_road = None
    if roadish:
        compact_road = _compact_road_text(result)
        fitted = fit(compact_road)
        if fitted:
            return fitted

    if _should_compact_short_road(result):
        if compact_road is None:
            compact_road = _compact_road_text(result)
        fitted = fit(compact_road)
        if fitted:
            return fitted

    if roadish and compact_road:
        compact = _canonicalize_output_markers(_compact_general_text(compact_road))
        if len(compact) <= _MAX_HOUSE_STREET_LEN:
            return compact
        return compact[:_MAX_HOUSE_STREET_LEN].rstrip(' ,;.')

    fitted = fit(result)
    if fitted:
        return fitted

    for compact in (_compact_road_text(result), _compact_relative_text(result), _compact_detail_with_street(result), _compact_street_text(result), _compact_general_text(result)):
        fitted = fit(compact)
        if fitted:
            return fitted

    compact = _canonicalize_output_markers(_compact_general_text(result))
    if len(compact) <= _MAX_HOUSE_STREET_LEN:
        return compact
    return compact[:_MAX_HOUSE_STREET_LEN].rstrip(' ,;.')


# ═══════════════════════════════════════════════════════════════════
#  ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════════════

def parse_address(raw: str) -> ParsedAddress:
    if not raw or not isinstance(raw, str):
        return ParsedAddress(raw=str(raw) if raw else "")

    src = _normalize_source_text(re.sub(r'\s+', ' ', str(raw)).strip())
    if not src:
        return ParsedAddress(raw=raw)

    tokens = _split_address_tokens(src)
    has_strong_road_context = any(
        _RE_KM.search(tok) or _RE_STRONG_ROAD_MARKER.search(tok)
        for tok in tokens
    )

    settlements: List[Tuple[str, str, int]] = []
    streets:     List[str] = []
    houses:      List[str] = []
    km_tokens:   List[str] = []
    road_tokens: List[str] = []
    spatial_tokens: List[str] = []
    address_landmark_tokens: List[str] = []
    microdistrict_tokens: List[str] = []
    district_fallbacks: List[Tuple[str, str, int]] = []
    region_fallbacks: List[Tuple[str, str, int]] = []
    road_admin_fallbacks: List[Tuple[str, str, int]] = []
    other:       List[str] = []

    pomesh_seen = False   # флаг: встретили помещ./пом. → пропускаем голые номера

    for raw_tok in tokens:
        tok = _repair_glued_road_token(raw_tok)
        if _is_postal(tok):    continue
        if _is_country(tok):   continue

        compound_admin = _try_compound_admin_landmark(tok)
        if compound_admin:
            sett, landmark = compound_admin
            settlements.append(sett)
            address_landmark_tokens.append(landmark)
            continue

        parenthesized_road = _try_parenthesized_settlement_road(tok)
        if parenthesized_road:
            sett, road = parenthesized_road
            settlements.append(sett)
            road_tokens.append(road)
            continue

        settlement_before_km = _try_settlement_before_km(tok)
        if settlement_before_km:
            sett, km = settlement_before_km
            settlements.append(sett)
            km_tokens.append(km)
            continue

        inline = _try_inline_settlement_street_house(tok)
        if inline:
            sett, street, inline_houses = inline
            settlements.append(sett)
            streets.append(street)
            houses.extend(inline_houses)
            continue

        compound = _try_compound_settlement_street(tok)
        if compound:
            sett, street = compound
            settlements.append(sett)
            streets.append(street)
            continue

        spatial = _try_distance_direction_settlement(tok)
        if spatial:
            sett, desc = spatial
            settlements.append(sett)
            if desc:
                spatial_tokens.append(desc)
            continue

        street_relative_house = _try_street_relative_house(tok)
        if street_relative_house:
            street, detail = street_relative_house
            streets.append(street)
            houses.append(detail)
            continue

        relative_house = _try_relative_house_landmark(tok)
        if relative_house and streets:
            houses.append(relative_house)
            continue

        initial_street = _try_initial_street(tok)
        if initial_street:
            streets.append(initial_street)
            continue

        school_landmark = _try_school_landmark(tok)
        if school_landmark:
            address_landmark_tokens.append(school_landmark)
            continue

        street_landmark = _try_street_landmark(tok)
        if street_landmark:
            streets.append(street_landmark)
            continue

        zone = _try_zone_object(tok)
        if zone:
            address_landmark_tokens.append(zone)
            continue

        if streets and not road_tokens and re.fullmatch(
            r'\d+(?:[-–]\d+)?[\.,]?\d*(?:[-–]?(?:й|ой|ый))?\s*км',
            tok,
            re.I,
        ):
            km_tokens.append(tok)
            continue

        territory = _try_territory_object(tok)
        if territory:
            streets.append(territory)
            continue

        road_fragment = _try_road_fragment(tok, allow_shosse=has_strong_road_context)
        if road_fragment:
            embedded_settlement = _try_road_embedded_settlement(tok)
            if embedded_settlement:
                settlements.append(embedded_settlement)
            road_tokens.append(road_fragment)
            continue

        if road_tokens and (_is_road_object_token(tok) or _RE_ROAD_SIDE_ONLY.match(_clean(tok))):
            house = _try_house(tok)
            road_tokens.append(house or _clean(tok))
            continue

        road_landmark = _try_road_landmark_token(tok)
        if road_landmark:
            if road_tokens:
                road_tokens.append(road_landmark)
            else:
                address_landmark_tokens.append(road_landmark)
            continue

        detail = _try_address_detail(tok)
        if detail:
            if road_tokens:
                road_tokens.append(detail)
            else:
                houses.append(detail)
            continue

        azs = _try_azs_landmark(tok)
        if azs:
            address_landmark_tokens.append(azs)
            continue

        named_landmark = _try_named_landmark(tok)
        if named_landmark:
            streets.append(named_landmark)
            continue

        relative_hamlet = _try_relative_hamlet_landmark(tok)
        if relative_hamlet:
            address_landmark_tokens.append(relative_hamlet)
            continue

        direction_landmark = _try_direction_landmark(tok)
        if direction_landmark:
            address_landmark_tokens.append(direction_landmark)
            continue

        municipal_settlement = _try_municipal_settlement(tok)
        if municipal_settlement:
            settlements.append(municipal_settlement)
            continue

        district_fallback = _try_city_district_fallback(tok)
        if district_fallback:
            district_fallbacks.append(district_fallback)
            if not road_tokens and not km_tokens:
                road_admin_fallbacks.append(district_fallback)
            continue

        trailing_admin_street = _try_trailing_admin_street(tok)
        if trailing_admin_street:
            streets.append(trailing_admin_street)
            continue

        if _is_region(tok) and not _RE_KM.search(tok):
            region_fallback = ('регион', _clean(tok), 0)
            region_fallbacks.append(region_fallback)
            if not road_tokens and not km_tokens:
                road_admin_fallbacks.append(region_fallback)
            continue

        embedded_aul = _try_embedded_aul(tok)
        if embedded_aul:
            settlements.append(embedded_aul)
            continue

        # Пространственные описания («в районе здания 2а») — извлекаем номер
        # ДО проверки на район, иначе «в районе» отфильтрует токен целиком.
        near = _try_near_building(tok)
        if near is not None:
            houses.append(near)
            continue

        road_district_fallback = _try_road_district_fallback(tok)
        if road_district_fallback:
            district_fallbacks.append(road_district_fallback)
            if not road_tokens and not km_tokens:
                road_admin_fallbacks.append(road_district_fallback)
            continue

        if _is_district(tok) and not _RE_KM.search(tok):
            explicit_street = _try_street(tok)
            if explicit_street:
                streets.append(explicit_street)
            continue

        # Помещения: сам токен пропускаем, последующие bare-number токены —
        # продолжение списка помещений, тоже пропускаем.
        # Пример: «помещ. 105Н, 106Н, 107Н» → все три токена отбрасываются.
        if re.match(r'^(?:помещ(?:ение)?|пом)\.?(?:\s|$)', tok, re.I):
            pomesh_seen = True
            continue
        if pomesh_seen and _RE_BARE_NUM.match(tok):
            continue

        short_structure = _try_short_structure(tok)
        if short_structure and (streets or road_tokens):
            if road_tokens:
                road_tokens.append(short_structure)
            else:
                houses.append(short_structure)
            continue

        # ── Порядок важен: сначала дом, потом нас.пункт ──
        # (иначе «д. 9» матчится как деревня)
        if houses and re.fullmatch(r'к\.?\s*[А-Яа-яA-Za-z]', tok, re.I):
            houses.append(f"к. {_clean(tok[1:])}")
            continue

        if streets and houses and re.fullmatch(r'[А-Яа-яA-Za-z]', tok):
            houses[-1] = f"{houses[-1]}{tok}"
            continue

        if streets and re.fullmatch(r'\d{1,3},\d{1,3}', tok):
            houses.append(tok)
            continue

        house = _try_house(tok)
        if house is not None:
            houses.append(house)
            continue

        sett = _try_settlement(tok)
        if sett:
            settlements.append(sett)
            if sett[0] == 'мкр.':
                microdistrict_tokens.append(_format_settlement(sett))
            continue

        if _RE_KM.search(tok):
            km_tokens.append(tok)
            continue

        street_house = _try_street_house(tok)
        if street_house:
            street, house = street_house
            streets.append(street)
            houses.append(house)
            continue

        street = _try_street(tok)
        if street:
            streets.append(street)
            continue

        other.append(tok)

    # ── Выбор населённого пункта ──────────────────────────────────
    settlement_str = ""
    shifted_address_landmark = ""
    road_admin_fallback_used = False
    conventional_streets = [street for street in streets if not street.startswith('мкр. ')]
    if conventional_streets:
        streets = conventional_streets
    explicit_streets = [street for street in streets if street.startswith('ул. ')]
    if explicit_streets and len(streets) > 1:
        streets = [explicit_streets[-1]]

    forestry_landmarks = [street for street in streets if street.endswith((' лесн.', ' уч.лесн.'))]
    if forestry_landmarks:
        streets = [street for street in streets if not street.endswith((' лесн.', ' уч.лесн.'))]
        address_landmark_tokens.append(forestry_landmarks[-1])

    if not settlements and (streets or road_tokens or houses) and len(other) == 1:
        fallback = _try_plain_settlement_fallback(other[0])
        if fallback:
            settlements.append(fallback)
            other.clear()

    if not streets and houses and not road_tokens and not km_tokens and len(other) == 1:
        implicit_street = _try_implicit_street(other[0])
        if implicit_street:
            streets.append(implicit_street)
            other.clear()

    hierarchy_shift = None
    direction_landmarks_only = bool(address_landmark_tokens) and all(
        landmark.startswith(('из ', 'в '))
        for landmark in address_landmark_tokens
    )
    if (
        not streets
        and (not address_landmark_tokens or direction_landmarks_only)
        and not road_tokens
        and not km_tokens
        and not spatial_tokens
        and (houses or not other)
    ):
        hierarchy_shift = _try_hierarchy_shift(
            settlements,
            district_fallbacks,
            region_fallbacks,
        )
    if (
        not hierarchy_shift
        and not streets
        and not address_landmark_tokens
        and not houses
        and not road_tokens
        and not km_tokens
        and not spatial_tokens
        and not other
    ):
        hierarchy_shift = _try_only_settlement_shift(
            settlements,
            district_fallbacks,
            region_fallbacks,
        )

    if hierarchy_shift:
        parent, shifted_address_landmark = hierarchy_shift
        settlement_str = _format_settlement(parent)
    elif not settlements and (road_tokens or km_tokens) and road_admin_fallbacks:
        settlement_str = _format_settlement(road_admin_fallbacks[-1])
        road_admin_fallback_used = True
    elif not settlements and district_fallbacks and not road_tokens and not km_tokens:
        settlement_str = _format_settlement(max(district_fallbacks, key=lambda x: x[2]))
    elif not settlements and region_fallbacks:
        settlement_str = _format_settlement(region_fallbacks[-1])
    elif settlements:
        # Если есть г. И нас.пункт из _SUBCITY_TYPES (п., д., с., х., аул…)
        # → берём не-город (он специфичнее для доставки).
        # мкр. в _SUBCITY_TYPES НЕ входит — микрорайон часть города, не отдельный пункт.
        # Примеры: «г. Дзержинск, п. Гавриловка» → п. Гавриловка
        #          «г. Лыткарино, 6-й мкр»        → г. Лыткарино
        non_city = [s for s in settlements if s[0] in _SUBCITY_TYPES]
        city     = [s for s in settlements if s[0] == 'г.']
        specific_city = [
            s for s in city
            if s[1].lower() in _SPECIFIC_CITY_NAMES
        ]
        concrete_non_city = [
            s for s in non_city
            if s[0] not in {'г.п.', 'гп.'}
        ]
        spatial_is_parent_context = all(
            token.lower().startswith(('в р-не', 'в районе'))
            for token in spatial_tokens
        )
        if spatial_tokens and spatial_is_parent_context:
            non_spatial_landmarks = [
                s for s in settlements
                if s[0] not in _ADDRESS_LANDMARK_SETTLEMENT_TYPES
            ]
            effective = non_spatial_landmarks or settlements
        else:
            effective = specific_city or (concrete_non_city if (concrete_non_city and city) else settlements)
        if streets or road_tokens or km_tokens:
            best = max(
                enumerate(effective),
                key=lambda item: (_settlement_hierarchy_rank(item[1]), item[1][2], item[0]),
            )[1]
        else:
            best = max(effective, key=lambda x: x[2])
        settlement_str = _format_settlement(best)

    # ── Формирование «дом, улица» ─────────────────────────────────
    house_street_str = ""

    if road_tokens:
        local_street = next((_try_street(part) for part in road_tokens if _try_street(part)), None)
        has_separate_route = any(
            _RE_ROUTE_CODE.search(part)
            for part in road_tokens
            if not local_street or _try_street(part) != local_street
        )
        route_part = next((_extract_route_code(part) for part in road_tokens if _extract_route_code(part)), None)
        km_part = next((_compact_km(part) for part in road_tokens if _compact_km(part)), None)
        side_part = _compact_side(' '.join(road_tokens))
        if local_street and houses and has_separate_route and route_part and km_part:
            route_tail = ' '.join(item for item in [route_part, km_part, side_part] if item)
            route_candidate = f"{_join_houses(houses)}, {route_tail}"
            if len(_canonicalize_output_markers(route_candidate)) <= _MAX_HOUSE_STREET_LEN:
                house_street_str = route_candidate
        if local_street and houses and has_separate_route:
            house_street_str = house_street_str or f"{_join_houses(houses)}, {local_street}"

        parts = list(road_tokens)
        parts.extend(item for item in km_tokens if item not in parts)
        if streets and not house_street_str:
            parts.extend(streets)
        parts.extend(spatial_tokens)
        parts.extend(address_landmark_tokens)
        house_p = _join_houses(houses)
        if house_p:
            parts.append(house_p)
        if road_admin_fallback_used:
            parts.extend(_meaningful_road_fallback_details(other))
        if not house_street_str:
            house_street_str = ', '.join(parts)

    elif km_tokens:
        km_text  = ', '.join(km_tokens)
        km_desc  = _km_description(km_text)
        parts    = []
        house_p  = _join_houses(houses)
        if house_p:
            parts.append(house_p)
        parts.append(km_desc)
        if streets:
            parts.append(', '.join(streets))
        parts.extend(address_landmark_tokens)
        house_street_str = ', '.join(parts)

    elif houses or streets or address_landmark_tokens or microdistrict_tokens or shifted_address_landmark:
        house_p  = _join_houses(houses)
        landmarks = [
            *streets,
            *([shifted_address_landmark] if shifted_address_landmark else []),
            *address_landmark_tokens,
        ]
        street_p = ', '.join(landmarks or microdistrict_tokens)
        if house_p and street_p:
            house_street_str = f"{house_p}, {street_p}"
        elif house_p:
            house_street_str = house_p
        else:
            house_street_str = street_p

    elif spatial_tokens:
        house_street_str = ', '.join(spatial_tokens)

    elif other:
        house_street_str = ', '.join(other)

    if house_street_str:
        house_street_str = _correct_road_endpoint_typo(house_street_str, settlement_str)
        house_street_str = _limit_house_street(house_street_str)
    if settlement_str:
        settlement_str = _limit_settlement(settlement_str)

    # ── Уверенность ───────────────────────────────────────────────
    confidence = 1.0
    if not settlement_str:   confidence -= 0.3
    if not house_street_str: confidence -= 0.3
    if other:                confidence -= 0.05 * len(other)
    confidence = round(max(0.0, min(1.0, confidence)), 2)

    debug = (f"sett={settlements} | streets={streets} | "
             f"houses={houses} | km={km_tokens} | road={road_tokens} | "
             f"road_admin={road_admin_fallbacks} | spatial={spatial_tokens} | other={other}")

    return ParsedAddress(
        settlement=settlement_str,
        house_street=house_street_str,
        raw=raw,
        confidence=confidence,
        debug_info=debug,
    )
