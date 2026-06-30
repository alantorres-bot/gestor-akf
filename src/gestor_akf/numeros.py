"""Conversão de números no formato brasileiro (1.234.567,89).

Usa Decimal para dinheiro — nunca float — para evitar erros de
arredondamento em valores financeiros.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Aceita opcionalmente "R$", sinal, milhares com ponto e centavos com vírgula.
# Também tolera ruído de OCR: espaços internos e o caractere "O" no lugar de "0".
_LIMPA = re.compile(r"[^\d.,\-]")
_SO_NUMERO = re.compile(r"\d")

CENTAVOS = Decimal("0.01")


def parse_valor_br(texto: str | int | float | Decimal | None) -> Decimal | None:
    """Converte "440.000,00" -> Decimal("440000.00").

    Retorna None se não houver nenhum dígito (campo vazio / texto puro).
    Levanta ValueError se houver dígitos mas o formato for irrecuperável.
    """
    if texto is None:
        return None
    if isinstance(texto, Decimal):
        return texto
    if isinstance(texto, (int,)):
        return Decimal(texto)
    if isinstance(texto, float):
        # valores vindos de Excel são float; arredonda para centavos para
        # evitar resíduo de ponto flutuante ao somar.
        return Decimal(str(texto)).quantize(CENTAVOS)

    bruto = str(texto).strip()
    if not bruto:
        return None
    # Ruído comum de OCR: "O"/"o" lidos no lugar de zero quando cercados de dígitos.
    bruto = re.sub(r"(?<=\d)[Ooº](?=[\d.,])", "0", bruto)
    limpo = _LIMPA.sub("", bruto)
    if not _SO_NUMERO.search(limpo):
        return None

    negativo = limpo.startswith("-")
    limpo = limpo.lstrip("-")

    # Decide o separador decimal: o último entre '.' e ',' que aparecer.
    ult_virgula = limpo.rfind(",")
    ult_ponto = limpo.rfind(".")
    if ult_virgula > ult_ponto:
        # vírgula é o decimal -> remove pontos (milhar), troca vírgula por ponto
        limpo = limpo.replace(".", "").replace(",", ".")
    elif ult_ponto > ult_virgula:
        # ponto é o decimal -> remove vírgulas (milhar)
        limpo = limpo.replace(",", "")
    # else: só dígitos, sem separador

    try:
        valor = Decimal(limpo)
    except InvalidOperation as exc:  # pragma: no cover - defensivo
        raise ValueError(f"Valor numérico irreconhecível: {texto!r}") from exc

    valor = valor.quantize(CENTAVOS)
    return -valor if negativo else valor


def formatar_valor_br(valor: Decimal | int | float | None, *, com_simbolo: bool = False) -> str:
    """Formata 440000 -> "440.000,00" (ou "R$ 440.000,00")."""
    if valor is None:
        return ""
    d = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    d = d.quantize(CENTAVOS)
    negativo = d < 0
    inteiro, _, dec = f"{abs(d):.2f}".partition(".")
    # agrupa milhares com ponto
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    txt = ".".join(grupos) + "," + dec
    if negativo:
        txt = "-" + txt
    return f"R$ {txt}" if com_simbolo else txt


def formatar_pct(taxa: Decimal | float | None, casas: int = 2) -> str:
    """Formata 0.0245 -> "2,45%"."""
    if taxa is None:
        return ""
    d = taxa if isinstance(taxa, Decimal) else Decimal(str(taxa))
    pct = (d * 100).quantize(Decimal(1).scaleb(-casas))
    return f"{pct}".replace(".", ",") + "%"
