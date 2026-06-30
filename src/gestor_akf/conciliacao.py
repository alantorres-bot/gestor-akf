"""Conciliação: instrução × borderô × carteira.

Cruza o que foi PEDIDO (instrução/seleção) com o que foi OPERADO (borderôs) e
aponta divergências:
  * NFs pedidas e não operadas;
  * divergência de valor ou vencimento;
  * títulos em duplicidade;
  * títulos operados sem terem sido pedidos;
  * recompras a conferir (correção + multa 2%);
  * diferença por dentro/por fora (quando há o par de borderôs).

Como os números de documento podem diferir entre sistemas, o casamento é feito
pelo documento (normalizado) e, na falta dele, por (valor de face + vencimento).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from .calculos import calcular_recompra, diferenca_por_fora
from .modelos import Bordero, TituloBordero
from .numeros import formatar_valor_br

Z = Decimal("0.00")
TOL = Decimal("0.05")


@dataclass
class Pedido:
    documento: str
    valor: Decimal
    vencimento: Optional[date] = None
    cliente: str = ""


@dataclass
class Divergencia:
    tipo: str        # nao_operada | valor | vencimento | duplicidade | so_no_bordero | recompra
    documento: str
    detalhe: str


@dataclass
class ResultadoConciliacao:
    casados: list[str] = field(default_factory=list)
    divergencias: list[Divergencia] = field(default_factory=list)
    diferenca_por_fora: Optional[object] = None
    recompras_total: Decimal = Z

    @property
    def ok(self) -> bool:
        return not self.divergencias

    def por_tipo(self, tipo: str) -> list[Divergencia]:
        return [d for d in self.divergencias if d.tipo == tipo]


def _norm_doc(doc: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]", "", doc or "").upper()


def _operados(borderos: list[Bordero]) -> list[TituloBordero]:
    """Títulos operados, tomando a carteira 'por dentro' como referência.

    Os borderôs por dentro e por fora listam os MESMOS títulos; para não contar
    em dobro, usamos os por dentro (oficiais). Se só houver por fora, usa-os.
    """
    dentro = [b for b in borderos if b.por_dentro]
    base = dentro if dentro else borderos
    titulos: list[TituloBordero] = []
    for b in base:
        titulos.extend(b.titulos)
    return titulos


def conciliar(
    pedidos: list[Pedido],
    borderos: list[Bordero],
    *,
    taxa_multa: Decimal = Decimal("0.02"),
) -> ResultadoConciliacao:
    res = ResultadoConciliacao()
    operados = _operados(borderos)

    # índices
    por_doc: dict[str, list[TituloBordero]] = {}
    for t in operados:
        por_doc.setdefault(_norm_doc(t.documento), []).append(t)

    # duplicidade entre os operados
    for doc, lst in por_doc.items():
        if doc and len(lst) > 1:
            res.divergencias.append(Divergencia(
                "duplicidade", doc,
                f"Documento aparece {len(lst)}x nos borderôs.",
            ))

    usados: set[int] = set()  # ids de TituloBordero já casados

    def achar_por_valor_venc(p: Pedido) -> Optional[TituloBordero]:
        for t in operados:
            if id(t) in usados:
                continue
            if abs(t.valor_face - p.valor) <= TOL and (
                p.vencimento is None or t.vencimento == p.vencimento
            ):
                return t
        return None

    for p in pedidos:
        ndoc = _norm_doc(p.documento)
        candidatos = [t for t in por_doc.get(ndoc, []) if id(t) not in usados]
        match = candidatos[0] if candidatos else achar_por_valor_venc(p)

        if match is None:
            res.divergencias.append(Divergencia(
                "nao_operada", p.documento,
                f"NF pedida (R$ {formatar_valor_br(p.valor)}) não encontrada nos borderôs.",
            ))
            continue

        usados.add(id(match))
        divergiu = False
        # confere valor
        if abs(match.valor_face - p.valor) > TOL:
            divergiu = True
            res.divergencias.append(Divergencia(
                "valor", p.documento,
                f"Valor difere: pedido R$ {formatar_valor_br(p.valor)} × "
                f"borderô R$ {formatar_valor_br(match.valor_face)}.",
            ))
        # confere vencimento
        if p.vencimento and match.vencimento and p.vencimento != match.vencimento:
            divergiu = True
            res.divergencias.append(Divergencia(
                "vencimento", p.documento,
                f"Vencimento difere: pedido {p.vencimento:%d/%m/%Y} × "
                f"borderô {match.vencimento:%d/%m/%Y}.",
            ))
        if not divergiu:
            res.casados.append(p.documento)

    # títulos operados que ninguém pediu
    for t in operados:
        if id(t) not in usados:
            res.divergencias.append(Divergencia(
                "so_no_bordero", t.documento,
                f"Operado sem pedido: {t.sacado} R$ {formatar_valor_br(t.valor_face)}.",
            ))

    # recompras (a conferir contra o documento de pendências liquidadas)
    res.recompras_total = sum((b.recompras for b in borderos if b.por_dentro), Z)
    if res.recompras_total > 0:
        res.divergencias.append(Divergencia(
            "recompra", "",
            f"Há recompra de R$ {formatar_valor_br(res.recompras_total)} no borderô — "
            f"conferir correção + multa {taxa_multa * 100:.0f}% no documento de regresso.",
        ))

    # diferença por dentro/por fora
    dentro = next((b for b in borderos if b.por_dentro), None)
    fora = next((b for b in borderos if b.por_fora), None)
    if dentro and fora:
        res.diferenca_por_fora = diferenca_por_fora(dentro, fora)

    return res
