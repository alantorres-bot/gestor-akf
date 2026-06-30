"""Ingestão da carteira de recebíveis (export do ERP Consistem).

O export é um CSV em **cp1252** com separador **;** e cabeçalho nomeado.
Mapeamos as colunas pelo NOME do cabeçalho (tolerante a reordenação), com
nomes-padrão do Consistem e possibilidade de sobrescrever o mapeamento.

Portador identifica se o título já está antecipado:
  998 / "AKF"  -> já antecipado (está com a AKF)
  91  / "CARTEIRA", 237 / "BRADESCO", ... -> disponível para antecipar
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from .numeros import parse_valor_br
from .util import normalizar_texto, parse_data_br

# Portador da AKF (título já antecipado).
PORTADOR_AKF_CODIGO = "998"
PORTADOR_AKF_NOMES = {"akf"}

# Mapeamento padrão: campo do app -> nome da coluna no CSV do Consistem.
# A comparação é feita por nome normalizado (sem acento, minúsculo).
MAPEAMENTO_PADRAO = {
    "titulo": "Título",
    "cliente_codigo": "Cliente",
    "cliente_nome": "Nome Cliente",
    "emissao": "Emissão",
    "vencimento": "Vencimento",
    "valor": "Valor",
    "portador_codigo": "Portador",
    "portador_nome": "Nome Portador",
    "tipo_cobranca": "Descrição Tipo de Cobrança",
    "dias_atraso": "Dias Atraso",
    "dias_prazo": "Dias Prazo",
    "empresa": "Empresa",
    "cnpj_grupo": "Código Grupo",
    "bordero": "Borderô",
    "observacao": "Observação do Título",
}


@dataclass
class TituloCarteira:
    titulo: str
    cliente_codigo: str = ""
    cliente_nome: str = ""
    emissao: Optional[date] = None
    vencimento: Optional[date] = None
    valor: Decimal = Decimal("0.00")
    portador_codigo: str = ""
    portador_nome: str = ""
    tipo_cobranca: str = ""
    dias_atraso: int = 0
    dias_prazo: int = 0
    empresa: str = ""
    cnpj_grupo: str = ""
    bordero: str = ""
    observacao: str = ""
    origem_linha: int = 0  # auditoria: nº da linha no CSV

    @property
    def antecipado(self) -> bool:
        return (
            self.portador_codigo.strip() == PORTADOR_AKF_CODIGO
            or normalizar_texto(self.portador_nome) in PORTADOR_AKF_NOMES
        )

    @property
    def disponivel(self) -> bool:
        return not self.antecipado

    def dias_ate_vencimento(self, ref: date) -> Optional[int]:
        if self.vencimento is None:
            return None
        return (self.vencimento - ref).days

    @property
    def vencido(self) -> bool:
        return self.dias_atraso > 0


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def _detectar_encoding(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _detectar_separador(linha: str) -> str:
    return max([";", ",", "\t", "|"], key=linha.count)


def _resolver_colunas(cabecalho: list[str], mapeamento: dict[str, str]) -> dict[str, int]:
    """Acha o índice de cada coluna pelo nome (normalizado)."""
    norm = {normalizar_texto(h): i for i, h in enumerate(cabecalho)}
    indices: dict[str, int] = {}
    for campo, nome_col in mapeamento.items():
        i = norm.get(normalizar_texto(nome_col))
        if i is not None:
            indices[campo] = i
    return indices


def _int(v: str) -> int:
    v = (v or "").strip()
    try:
        return int(float(v.replace(".", "").replace(",", "."))) if v else 0
    except ValueError:
        return 0


def carregar_carteira(
    caminho: str,
    mapeamento: Optional[dict[str, str]] = None,
) -> list[TituloCarteira]:
    """Lê o CSV do Consistem e devolve a lista de títulos da carteira."""
    mapeamento = mapeamento or MAPEAMENTO_PADRAO
    raw = open(caminho, "rb").read()
    enc = _detectar_encoding(raw)
    texto = raw.decode(enc)
    linhas = texto.splitlines()
    if not linhas:
        return []
    sep = _detectar_separador(linhas[0])
    leitor = csv.reader(linhas, delimiter=sep)
    rows = list(leitor)
    cabecalho = rows[0]
    cols = _resolver_colunas(cabecalho, mapeamento)
    if "titulo" not in cols or "valor" not in cols:
        raise ValueError(
            "Não encontrei as colunas mínimas (Título e Valor) no CSV. "
            f"Cabeçalho lido: {cabecalho}"
        )

    def get(row, campo):
        i = cols.get(campo)
        return row[i] if i is not None and i < len(row) else ""

    titulos: list[TituloCarteira] = []
    for n, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        titulo = get(row, "titulo").strip()
        if not titulo:
            continue
        titulos.append(
            TituloCarteira(
                titulo=titulo,
                cliente_codigo=get(row, "cliente_codigo").strip(),
                cliente_nome=get(row, "cliente_nome").strip(),
                emissao=parse_data_br(get(row, "emissao")),
                vencimento=parse_data_br(get(row, "vencimento")),
                valor=parse_valor_br(get(row, "valor")) or Decimal("0.00"),
                portador_codigo=get(row, "portador_codigo").strip(),
                portador_nome=get(row, "portador_nome").strip(),
                tipo_cobranca=get(row, "tipo_cobranca").strip(),
                dias_atraso=_int(get(row, "dias_atraso")),
                dias_prazo=_int(get(row, "dias_prazo")),
                empresa=get(row, "empresa").strip(),
                cnpj_grupo=get(row, "cnpj_grupo").strip(),
                bordero=get(row, "bordero").strip(),
                observacao=get(row, "observacao").strip(),
                origem_linha=n,
            )
        )
    return titulos


@dataclass
class ResumoCarteira:
    total_titulos: int
    total_valor: Decimal
    disponiveis_qtd: int
    disponiveis_valor: Decimal
    antecipados_qtd: int
    antecipados_valor: Decimal
    vencidos_qtd: int
    vencidos_valor: Decimal


def resumir(titulos: list[TituloCarteira]) -> ResumoCarteira:
    Z = Decimal("0.00")
    disp = [t for t in titulos if t.disponivel]
    ant = [t for t in titulos if t.antecipado]
    venc = [t for t in titulos if t.vencido]
    return ResumoCarteira(
        total_titulos=len(titulos),
        total_valor=sum((t.valor for t in titulos), Z),
        disponiveis_qtd=len(disp),
        disponiveis_valor=sum((t.valor for t in disp), Z),
        antecipados_qtd=len(ant),
        antecipados_valor=sum((t.valor for t in ant), Z),
        vencidos_qtd=len(venc),
        vencidos_valor=sum((t.valor for t in venc), Z),
    )
