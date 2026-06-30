"""Carrega os parâmetros configuráveis do app (config/parametros.json).

Se não houver arquivo, usa os padrões abaixo (mesmos do parametros.exemplo.json).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .util import normalizar_texto

_PADRAO = {
    "clientes_sem_boleto_factoring": [
        "MIP", "MB", "JANEIRO", "CAPARAO", "HOUSE GARDEN", "QRTZ 39",
    ],
    "observacao_sem_boleto": "Operar 1 dia após o vencimento, sem emitir boleto.",
    "limite_global_akf": 3000000.00,
    "limite_por_sacado": {},
    "multa_recompra": 0.02,
    "taxa_referencia_am": 0.0218,
    "taxas_bancarias_am": {},
    "concentracao_maxima_por_sacado": 0.30,
    "contatos_akf": {
        "para": ["andre.kamil@akfsec.com.br", "kayza@akfsec.com.br"],
        "cc": ["akfsec@outlook.com"],
    },
}


@dataclass
class Parametros:
    clientes_sem_boleto_factoring: list[str] = field(default_factory=list)
    observacao_sem_boleto: str = ""
    limite_global_akf: Decimal = Decimal("0")
    limite_por_sacado: dict[str, Decimal] = field(default_factory=dict)
    multa_recompra: Decimal = Decimal("0.02")
    taxa_referencia_am: Decimal = Decimal("0")
    taxas_bancarias_am: dict[str, Decimal] = field(default_factory=dict)
    concentracao_maxima_por_sacado: Decimal = Decimal("0.30")
    contatos_akf: dict = field(default_factory=dict)

    # cache de nomes normalizados dos clientes sem boleto
    _sem_boleto_norm: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._sem_boleto_norm = [
            normalizar_texto(c) for c in self.clientes_sem_boleto_factoring
        ]

    def cliente_sem_boleto(self, nome_cliente: str) -> bool:
        """True se o nome do cliente bate com algum da lista 'sem boleto'."""
        alvo = normalizar_texto(nome_cliente)
        return any(termo and termo in alvo for termo in self._sem_boleto_norm)


def _to_decimal(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def carregar_parametros(caminho: Optional[str] = None) -> Parametros:
    """Carrega parâmetros do JSON; cai nos padrões se o arquivo não existir."""
    dados = dict(_PADRAO)
    if caminho is None:
        # procura config/parametros.json a partir da raiz do projeto
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        candidato = os.path.join(raiz, "config", "parametros.json")
        caminho = candidato if os.path.exists(candidato) else None

    if caminho and os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if not k.startswith("_"):
                dados[k] = v

    return Parametros(
        clientes_sem_boleto_factoring=list(dados["clientes_sem_boleto_factoring"]),
        observacao_sem_boleto=dados["observacao_sem_boleto"],
        limite_global_akf=_to_decimal(dados["limite_global_akf"]),
        limite_por_sacado={
            k: _to_decimal(v) for k, v in dados.get("limite_por_sacado", {}).items()
            if not k.startswith("_")
        },
        multa_recompra=_to_decimal(dados["multa_recompra"]),
        taxa_referencia_am=_to_decimal(dados["taxa_referencia_am"]),
        taxas_bancarias_am={
            k: _to_decimal(v) for k, v in dados.get("taxas_bancarias_am", {}).items()
        },
        concentracao_maxima_por_sacado=_to_decimal(dados["concentracao_maxima_por_sacado"]),
        contatos_akf=dados.get("contatos_akf", {}),
    )
