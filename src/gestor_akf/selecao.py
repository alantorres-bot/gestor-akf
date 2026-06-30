"""Seleção/otimização dos títulos a antecipar.

Objetivo: levantar o caixa necessário ao MENOR custo e MENOR risco,
respeitando restrições. A decisão final é do humano — isto prioriza e sugere.

Ordem de prioridade aplicada:
  (a) necessidade de caixa  — para de selecionar ao atingir o valor-alvo;
  (b) menor prazo = menor custo — ordena por dias até o vencimento (crescente);
  (c) clientes sem boleto de factoring — marca a observação da regra;
  (d) evita concentração por sacado — limita o quanto cada sacado entra;
  (e) respeita o limite disponível na AKF (global e por sacado);
  (f) estima o custo efetivo da seleção.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from .carteira import TituloCarteira
from .parametros import Parametros
from .calculos import taxa_efetiva_mensal

Z = Decimal("0.00")


@dataclass
class ItemSelecao:
    titulo: TituloCarteira
    dias: int                 # dias até o vencimento (na data de referência)
    sem_boleto: bool
    observacao: str
    desagio_estimado: Decimal


@dataclass
class ResultadoSelecao:
    itens: list[ItemSelecao] = field(default_factory=list)
    valor_alvo: Decimal = Z
    valor_total: Decimal = Z
    atingiu_alvo: bool = False
    custo_estimado: Decimal = Z
    desembolso_estimado: Decimal = Z
    taxa_estimada_am: Optional[Decimal] = None
    excluidos_concentracao: list[TituloCarteira] = field(default_factory=list)
    excluidos_limite: list[TituloCarteira] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def qtd(self) -> int:
        return len(self.itens)


def _chave_sacado(t: TituloCarteira) -> str:
    return t.cliente_codigo or t.cliente_nome


def selecionar_titulos(
    titulos: list[TituloCarteira],
    valor_alvo: Decimal,
    data_ref: date,
    params: Parametros,
    *,
    incluir_vencidos: bool = False,
    exposicao_atual: Decimal = Z,
    taxa_am: Optional[Decimal] = None,
) -> ResultadoSelecao:
    """Seleciona títulos disponíveis até cobrir o valor-alvo.

    `exposicao_atual` = valor já antecipado na AKF (para checar o limite global).
    `taxa_am` = taxa mensal usada para estimar o deságio; se None, usa a de
    referência dos parâmetros.
    """
    valor_alvo = Decimal(valor_alvo)
    taxa_am = taxa_am if taxa_am is not None else params.taxa_referencia_am
    res = ResultadoSelecao(valor_alvo=valor_alvo)

    # (b) candidatos: disponíveis, com vencimento conhecido; ordena por prazo.
    candidatos = [t for t in titulos if t.disponivel and t.vencimento is not None]
    if not incluir_vencidos:
        candidatos = [t for t in candidatos if (t.vencimento - data_ref).days >= 0]
    candidatos.sort(key=lambda t: ((t.vencimento - data_ref).days, -t.valor))

    limite_global = params.limite_global_akf
    cap_concentracao = (
        valor_alvo * params.concentracao_maxima_por_sacado
        if params.concentracao_maxima_por_sacado > 0 else None
    )

    por_sacado: dict[str, Decimal] = {}
    total = Z

    for t in candidatos:
        if total >= valor_alvo:
            break
        sac = _chave_sacado(t)
        novo_sacado = por_sacado.get(sac, Z) + t.valor

        # (e) limite global na AKF
        if limite_global > 0 and (exposicao_atual + total + t.valor) > limite_global:
            res.excluidos_limite.append(t)
            continue
        # (e) limite por sacado (se configurado)
        lim_sac = params.limite_por_sacado.get(sac) or params.limite_por_sacado.get(t.cliente_nome)
        if lim_sac is not None and novo_sacado > lim_sac:
            res.excluidos_limite.append(t)
            continue
        # (d) concentração máxima por sacado
        if cap_concentracao is not None and novo_sacado > cap_concentracao and total > 0:
            res.excluidos_concentracao.append(t)
            continue

        dias = (t.vencimento - data_ref).days
        sem_boleto = params.cliente_sem_boleto(t.cliente_nome)
        obs = params.observacao_sem_boleto if sem_boleto else ""
        # estimativa de deságio: pro-rata simples sobre o prazo
        dias_eff = max(dias, 0)
        desagio = (t.valor * taxa_am * Decimal(dias_eff) / Decimal(30)).quantize(Decimal("0.01"))

        res.itens.append(ItemSelecao(
            titulo=t, dias=dias, sem_boleto=sem_boleto,
            observacao=obs, desagio_estimado=desagio,
        ))
        por_sacado[sac] = novo_sacado
        total += t.valor

    res.valor_total = total
    res.atingiu_alvo = total >= valor_alvo
    res.custo_estimado = sum((i.desagio_estimado for i in res.itens), Z)
    res.desembolso_estimado = (total - res.custo_estimado).quantize(Decimal("0.01"))

    # taxa efetiva estimada da seleção (prazo médio ponderado pelo valor)
    if res.itens and total > 0:
        dias_medio = sum((Decimal(max(i.dias, 0)) * i.titulo.valor for i in res.itens), Z) / total
        res.taxa_estimada_am = taxa_efetiva_mensal(
            res.custo_estimado, total, int(dias_medio) or 1
        )

    # avisos
    if not res.atingiu_alvo:
        falta = (valor_alvo - total).quantize(Decimal("0.01"))
        res.avisos.append(
            f"Não foi possível atingir o valor-alvo: faltam R$ {falta} "
            f"(candidatos disponíveis insuficientes ou barrados por limite/concentração)."
        )
    if total > valor_alvo:
        sobra = (total - valor_alvo).quantize(Decimal("0.01"))
        res.avisos.append(
            f"A seleção excede o alvo em R$ {sobra} (títulos são indivisíveis)."
        )
    return res
