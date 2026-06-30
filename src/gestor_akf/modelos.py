"""Modelos de dados da operação de antecipação.

Tudo em Decimal para dinheiro. Cada borderô guarda a origem (arquivo) para
auditoria, conforme requisito não-funcional do projeto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

ZERO = Decimal("0.00")


@dataclass
class TituloBordero:
    """Um título (NF/parcela) dentro de um borderô."""

    documento: str
    valor_face: Decimal
    desagio: Decimal = ZERO
    tipo: str = ""
    sacado: str = ""
    sacado_codigo: Optional[str] = None
    sacado_cnpj: Optional[str] = None
    vencimento: Optional[date] = None

    @property
    def valor_liquido(self) -> Decimal:
        return self.valor_face - self.desagio


@dataclass
class Bordero:
    """Borderô (Declaração de Recebimento / Quitação) da AKF.

    `conexao` distingue a carteira: PRODUCAO = "por dentro" (oficial),
    PRODUCAO02 = "por fora". É o discriminador mais confiável; a série do
    número (8xxx vs 7xxx) é só um reforço.
    """

    numero: str
    conexao: str = ""
    cliente: str = ""
    data: Optional[date] = None
    titulos: list[TituloBordero] = field(default_factory=list)

    # Totais (lidos diretamente do borderô)
    total_bordero: Decimal = ZERO
    desagio: Decimal = ZERO
    valor_liquido: Decimal = ZERO
    recompras: Decimal = ZERO
    creditos: Decimal = ZERO
    debitos: Decimal = ZERO
    abatimento: Decimal = ZERO
    desembolso: Decimal = ZERO

    # Auditoria / diagnóstico
    origem_arquivo: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def por_dentro(self) -> bool:
        """True para a carteira oficial (PRODUCAO, série 8xxx)."""
        c = self.conexao.upper().replace(" ", "")
        if c:
            return not c.endswith("02")
        return self.numero.startswith("8")

    @property
    def por_fora(self) -> bool:
        return not self.por_dentro

    @property
    def serie(self) -> str:
        return self.numero[0] if self.numero else ""

    @property
    def rotulo_carteira(self) -> str:
        return "por dentro" if self.por_dentro else "por fora"
