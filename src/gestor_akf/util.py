"""Utilidades gerais (datas, normalização de texto)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Optional


def parse_data_br(texto) -> Optional[date]:
    """Lê data em dd/mm/aaaa (ou objeto date/datetime). Retorna None se vazio."""
    if texto is None or texto == "":
        return None
    if isinstance(texto, datetime):
        return texto.date()
    if isinstance(texto, date):
        return texto
    s = str(texto).strip()
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", s)
    if not m:
        # tenta ISO aaaa-mm-dd
        m2 = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m2:
            try:
                return date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
            except ValueError:
                return None
        return None
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if ano < 100:
        ano += 2000
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def normalizar_texto(s: str) -> str:
    """minúsculas, sem acento, espaços colapsados — para comparar nomes/rótulos."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()
