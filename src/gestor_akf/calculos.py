"""Regras de negócio / cálculos da operação de antecipação.

Funções puras (entram números, saem números) para serem fáceis de testar.
Casos de teste de referência: borderôs 8585/7104 (29/05/2026).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .modelos import ZERO, Bordero

CENTAVOS = Decimal("0.01")
TOLERANCIA = Decimal("0.05")  # tolerância p/ conferência de arredondamento (5 centavos)


# --------------------------------------------------------------------------- #
# Desembolso
# --------------------------------------------------------------------------- #
@dataclass
class ResultadoDesembolso:
    valor_liquido: Decimal
    desembolso: Decimal


def calcular_desembolso(
    total_bordero: Decimal,
    desagio: Decimal,
    recompras: Decimal = ZERO,
    creditos: Decimal = ZERO,
    debitos: Decimal = ZERO,
    abatimento: Decimal = ZERO,
) -> ResultadoDesembolso:
    """Aplica a fórmula do borderô:

        Valor Líquido = Total do borderô − Deságio
        Desembolso    = Líquido − Recompras + Créditos − Débitos − Abatimento
    """
    liquido = (total_bordero - desagio).quantize(CENTAVOS)
    desembolso = (liquido - recompras + creditos - debitos - abatimento).quantize(CENTAVOS)
    return ResultadoDesembolso(valor_liquido=liquido, desembolso=desembolso)


def conferir_bordero(b: Bordero) -> list[str]:
    """Confere a aritmética interna de um borderô lido (auditoria).

    Retorna a lista de divergências encontradas (vazia = tudo confere).
    Serve para flagrar erro de OCR automaticamente.
    """
    problemas: list[str] = []
    esperado = calcular_desembolso(
        b.total_bordero, b.desagio, b.recompras, b.creditos, b.debitos, b.abatimento
    )
    if abs(esperado.valor_liquido - b.valor_liquido) > TOLERANCIA:
        problemas.append(
            f"Valor líquido não bate: lido {b.valor_liquido} ≠ calculado "
            f"{esperado.valor_liquido} (Total − Deságio)."
        )
    if abs(esperado.desembolso - b.desembolso) > TOLERANCIA:
        problemas.append(
            f"Desembolso não bate: lido {b.desembolso} ≠ calculado {esperado.desembolso}."
        )
    # Soma dos títulos deve bater com o total do borderô (quando há títulos lidos).
    if b.titulos:
        soma_face = sum((t.valor_face for t in b.titulos), ZERO)
        if abs(soma_face - b.total_bordero) > TOLERANCIA:
            problemas.append(
                f"Soma das faces dos títulos ({soma_face}) ≠ Total do borderô "
                f"({b.total_bordero})."
            )
    return problemas


# --------------------------------------------------------------------------- #
# Recompra / regresso
# --------------------------------------------------------------------------- #
def calcular_recompra(
    valor_titulo: Decimal,
    correcao: Decimal = ZERO,
    despesas: Decimal = ZERO,
    taxa_multa: Decimal = Decimal("0.02"),
) -> Decimal:
    """Valor total da recompra = título + correção + multa (2% sobre o título) + despesas.

    Base da multa = valor do título (padrão da operação AKF).
    """
    multa = (valor_titulo * taxa_multa).quantize(CENTAVOS)
    return (valor_titulo + correcao + multa + despesas).quantize(CENTAVOS)


# --------------------------------------------------------------------------- #
# Diferença "por fora"
# --------------------------------------------------------------------------- #
@dataclass
class ResultadoPorFora:
    diferenca: Decimal           # juro "por fora" da operação (custo financeiro)
    liquido_por_dentro: Decimal
    liquido_por_fora: Decimal
    bordero_por_dentro: str
    bordero_por_fora: str


def diferenca_por_fora(b_dentro: Bordero, b_fora: Bordero) -> ResultadoPorFora:
    """Diferença = Valor Líquido (por dentro) − Valor Líquido (por fora).

    Esse valor é o "juro por fora" daquela operação — tratado pela sua
    substância econômica: custo financeiro.
    """
    dif = (b_dentro.valor_liquido - b_fora.valor_liquido).quantize(CENTAVOS)
    return ResultadoPorFora(
        diferenca=dif,
        liquido_por_dentro=b_dentro.valor_liquido,
        liquido_por_fora=b_fora.valor_liquido,
        bordero_por_dentro=b_dentro.numero,
        bordero_por_fora=b_fora.numero,
    )


# --------------------------------------------------------------------------- #
# Custo efetivo
# --------------------------------------------------------------------------- #
def taxa_efetiva_mensal(
    desagio: Decimal,
    valor_face: Decimal,
    dias: int,
    *,
    composta: bool = True,
) -> Optional[Decimal]:
    """Taxa efetiva ao mês (30 dias) do custo de antecipação.

    taxa_periodo = deságio / líquido_recebido   (custo sobre o dinheiro recebido)
    composta:  (1 + taxa_periodo) ** (30/dias) − 1
    simples:    taxa_periodo * 30 / dias

    Retorna None se dias <= 0 ou líquido <= 0 (não dá para anualizar).
    """
    if dias <= 0:
        return None
    liquido = valor_face - desagio
    if liquido <= 0:
        return None
    taxa_periodo = Decimal(desagio) / Decimal(liquido)
    fator = Decimal(30) / Decimal(dias)
    if composta:
        # usa float só para a potência fracionária; resultado volta a Decimal
        base = float(1 + taxa_periodo)
        taxa = Decimal(str(base ** float(fator))) - 1
    else:
        taxa = taxa_periodo * fator
    return taxa.quantize(Decimal("0.000001"))


@dataclass
class CustoReal:
    """Custo efetivo de uma operação, somando 'por dentro' + 'por fora'."""

    custo_oficial: Decimal       # deságio do borderô por dentro
    custo_por_fora: Decimal      # diferença de líquido entre os dois borderôs
    custo_total: Decimal         # soma dos dois
    valor_face: Decimal
    liquido_real: Decimal        # face − custo_total (caixa real após custo verdadeiro)
    taxa_oficial_am: Optional[Decimal]   # taxa só com o deságio oficial
    taxa_real_am: Optional[Decimal]      # taxa com o custo verdadeiro


def custo_real_operacao(
    b_dentro: Bordero,
    b_fora: Bordero,
    dias: int,
    *,
    composta: bool = True,
) -> CustoReal:
    """Custo verdadeiro = deságio oficial + parcela 'por fora'.

    Evita o "custo cego": a taxa real costuma ser bem maior que a oficial.
    `dias` = prazo médio da operação (emissão/operação -> vencimento).
    """
    custo_oficial = b_dentro.desagio
    por_fora = diferenca_por_fora(b_dentro, b_fora).diferenca
    custo_total = (custo_oficial + por_fora).quantize(CENTAVOS)
    face = b_dentro.total_bordero
    liquido_real = (face - custo_total).quantize(CENTAVOS)
    return CustoReal(
        custo_oficial=custo_oficial,
        custo_por_fora=por_fora,
        custo_total=custo_total,
        valor_face=face,
        liquido_real=liquido_real,
        taxa_oficial_am=taxa_efetiva_mensal(custo_oficial, face, dias, composta=composta),
        taxa_real_am=taxa_efetiva_mensal(custo_total, face, dias, composta=composta),
    )
