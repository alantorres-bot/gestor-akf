"""Geração da instrução por e-mail para a AKF (André / Kayza).

Monta o texto a partir de uma seleção de títulos, separando os clientes que
NÃO aceitam boleto de factoring (regra: operar 1 dia após o vencimento, sem
emitir boleto).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .numeros import formatar_valor_br
from .parametros import Parametros
from .selecao import ResultadoSelecao

Z = Decimal("0.00")


@dataclass
class Instrucao:
    assunto: str
    para: list[str]
    cc: list[str]
    corpo: str


def _fmt_data(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def gerar_instrucao(
    selecao: ResultadoSelecao,
    params: Parametros,
    *,
    data_operacao: date | None = None,
    saudacao: str = "Olá, André e Kayza,",
    remetente: str = "Alan Torres — Financeiro Neo Formas",
) -> Instrucao:
    """Gera o e-mail de instrução para a AKF com os títulos selecionados."""
    itens = selecao.itens
    normais = [i for i in itens if not i.sem_boleto]
    sem_boleto = [i for i in itens if i.sem_boleto]

    linhas: list[str] = [saudacao, ""]
    linhas.append(
        "Segue a relação de títulos para operar"
        + (f" (operação {_fmt_data(data_operacao)})" if data_operacao else "")
        + ":"
    )
    linhas.append("")

    def bloco(titulo_bloco: str, grupo, obs: str = "") -> None:
        if not grupo:
            return
        linhas.append(titulo_bloco)
        if obs:
            linhas.append(f"  ⚠ {obs}")
        for i in grupo:
            t = i.titulo
            linhas.append(
                f"  • NF {t.titulo} | {t.cliente_nome} | "
                f"venc. {_fmt_data(t.vencimento)} | R$ {formatar_valor_br(t.valor)}"
            )
        subtotal = sum((i.titulo.valor for i in grupo), Z)
        linhas.append(f"  Subtotal: R$ {formatar_valor_br(subtotal)} ({len(grupo)} título(s))")
        linhas.append("")

    bloco("TÍTULOS (operação normal):", normais)
    bloco(
        "TÍTULOS DE CLIENTES SEM BOLETO DE FACTORING:",
        sem_boleto,
        obs=params.observacao_sem_boleto,
    )

    linhas.append(
        f"TOTAL GERAL: R$ {formatar_valor_br(selecao.valor_total)} "
        f"({selecao.qtd} título(s))."
    )
    if selecao.custo_estimado > 0:
        linhas.append(
            f"(Estimativa interna — não enviar à AKF: deságio aprox. "
            f"R$ {formatar_valor_br(selecao.custo_estimado)}, "
            f"desembolso aprox. R$ {formatar_valor_br(selecao.desembolso_estimado)}.)"
        )
    linhas.append("")
    linhas.append("Qualquer dúvida, fico à disposição.")
    linhas.append("")
    linhas.append("Atenciosamente,")
    linhas.append(remetente)

    contatos = params.contatos_akf or {}
    assunto = "Neo Formas — Títulos para operar"
    if data_operacao:
        assunto += f" — {_fmt_data(data_operacao)}"

    return Instrucao(
        assunto=assunto,
        para=list(contatos.get("para", [])),
        cc=list(contatos.get("cc", [])),
        corpo="\n".join(linhas),
    )
