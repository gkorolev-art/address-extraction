"""
column_detector.py — автоматическое определение столбца с адресами.

Алгоритм:
  1. Для каждого столбца считаем «адресный score».
  2. Признаки: наличие типов нас.пунктов, типов улиц, запятых, «обл.», км и т.д.
  3. Столбец с максимальным score — кандидат.
"""

from __future__ import annotations
import re
import pandas as pd
from typing import Optional

# Маркеры, характерные для адреса
_ADDRESS_PATTERNS = [
    re.compile(p, re.I) for p in [
        r'\bобл\.?\b',
        r'\bрайон\b|\bр-н\b',
        r'\bг\.\s+\w',
        r'\bул\.\b|\bулица\b',
        r'\bд\.\s+\d',
        r'\bпр-кт\b|\bпр-т\b|\bпросп\b',
        r'\bшоссе\b|\bш\.\b',
        r'\bпер\.\b|\bпереулок\b',
        r'\d{6}\b',            # почтовый индекс
        r'\bкм\b',
        r'\bобласть\b',
        r'\bпгт\b|\bрп\b',
        r'\bс\.\s+\w',         # «с. Название»
        r'\bд\.\s+[А-Яа-я]',   # «д. Деревня»
        r'дом\s*[№#]',
        r'\bвл\.\b|\bвлд\.\b',
    ]
]

_NAME_HINTS = [
    'адрес', 'address', 'адр', 'местонахожд', 'местополож',
    'location', 'addr',
]


def detect_address_column(df: pd.DataFrame, sample_rows: int = 20) -> Optional[str]:
    """
    Возвращает имя наиболее вероятного столбца с адресами.
    Если ни один столбец не набрал достаточно очков — возвращает None.
    """
    best_col: Optional[str] = None
    best_score: float = 0.0

    sample = df.head(sample_rows)

    for col in df.columns:
        score = _score_column(col, sample[col])
        if score > best_score:
            best_score = score
            best_col = col

    return best_col if best_score >= 2.0 else None


def score_all_columns(df: pd.DataFrame, sample_rows: int = 20) -> dict:
    """Возвращает словарь {имя_столбца: score} для отображения пользователю."""
    sample = df.head(sample_rows)
    return {col: round(_score_column(col, sample[col]), 2) for col in df.columns}


def _score_column(col_name: str, series: pd.Series) -> float:
    score = 0.0

    # Подсказка по имени столбца
    col_lower = str(col_name).lower()
    if any(hint in col_lower for hint in _NAME_HINTS):
        score += 3.0

    # Анализ значений
    values = series.dropna().astype(str).head(30)
    if len(values) == 0:
        return 0.0

    for val in values:
        val_score = _score_value(val)
        score += val_score / len(values)  # среднее по строкам

    return score


def _score_value(val: str) -> float:
    """Насколько строка похожа на адрес (0..10)."""
    if not val or val.strip() in ('', 'nan', 'None'):
        return 0.0

    score = 0.0

    # Много запятых — признак адреса
    commas = val.count(',')
    if commas >= 2:
        score += 1.5
    elif commas == 1:
        score += 0.5

    # Совпадение адресных паттернов
    for pat in _ADDRESS_PATTERNS:
        if pat.search(val):
            score += 0.7

    # Длина (адреса обычно >= 20 символов)
    if len(val) >= 30:
        score += 0.5
    elif len(val) < 10:
        score -= 1.0

    return min(score, 10.0)
