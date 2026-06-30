"""Integração com a API REST do Consistem (módulos Financeiro e Cadastros Gerais).

Busca a carteira de recebíveis **ao vivo**, substituindo o export manual de CSV.
É a mesma API já em produção no NEOControl (base ``erp.neoformas.com.br/api``):
autenticação por header ``Authorization`` (token JWT gerado no CSMEN050) + header
``empresa``; paginação por ``continuationToken``.

A busca devolve a MESMA dataclass :class:`~gestor_akf.carteira.TituloCarteira` que o
CSV produz — então seleção, instrução, resumo e tudo a jusante ficam intactos.

Configuração (cai em padrões se nada for definido):
  - ``config/consistem.json``  -> {"base_url": ..., "empresa": ...}  (opcional)
  - env ``CONSISTEM_BASE_URL`` / ``CONSISTEM_EMPRESA``                (override)
  - TOKEN (nunca versionado): env ``CONSISTEM_API_KEY`` ou arquivo
    ``config/consistem.secret`` (o mesmo token usado no NEOControl, ~250 chars).
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from decimal import Decimal
from typing import Optional

import requests

from .carteira import PORTADOR_AKF_CODIGO, TituloCarteira
from .numeros import parse_valor_br
from .util import parse_data_br

BASE_URL_PADRAO = "https://erp.neoformas.com.br/api"
EMPRESA_PADRAO = "1"
TIMEOUT = 30  # segundos
MAX_TENTATIVAS_429 = 4
PAGINACAO = 200  # itens por página
_TAM_MIN_TOKEN = 50  # o JWT do CSMEN050 tem ~250 chars


class ConsistemError(RuntimeError):
    """Falha ao falar com a API do Consistem (rede, auth, serviço não liberado)."""


# --------------------------------------------------------------------------- #
# Configuração e token
# --------------------------------------------------------------------------- #
def _raiz() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _config() -> dict:
    cfg = {"base_url": BASE_URL_PADRAO, "empresa": EMPRESA_PADRAO}
    caminho = os.path.join(_raiz(), "config", "consistem.json")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
    cfg["base_url"] = os.environ.get("CONSISTEM_BASE_URL", cfg["base_url"]).rstrip("/")
    cfg["empresa"] = str(os.environ.get("CONSISTEM_EMPRESA", cfg["empresa"]))
    return cfg


def carregar_token() -> str:
    """Token da API: env CONSISTEM_API_KEY ou config/consistem.secret."""
    tok = os.environ.get("CONSISTEM_API_KEY", "").strip()
    if not tok:
        caminho = os.path.join(_raiz(), "config", "consistem.secret")
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                tok = f.read().strip()
    return tok


def token_configurado() -> bool:
    return len(carregar_token()) >= _TAM_MIN_TOKEN


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _headers() -> dict:
    tok = carregar_token()
    if len(tok) < _TAM_MIN_TOKEN:
        raise ConsistemError(
            "Token da API do Consistem não configurado. Defina a variável de ambiente "
            "CONSISTEM_API_KEY ou crie config/consistem.secret com o token "
            "(o mesmo do NEOControl, ~250 caracteres)."
        )
    return {"Authorization": tok, "empresa": _config()["empresa"], "Accept": "application/json"}


def _get_com_retry(url: str, headers: dict, params: dict) -> requests.Response:
    """GET com retry exponencial em HTTP 429 (rate limit)."""
    resp = None
    for tentativa in range(MAX_TENTATIVAS_429):
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if resp.status_code == 429 and tentativa < MAX_TENTATIVAS_429 - 1:
            time.sleep(2 ** tentativa)
            continue
        return resp
    return resp  # type: ignore[return-value]


def _buscar_todas_paginas(rota: str, params: dict) -> list[dict]:
    """GET paginado: acumula ``data`` de todas as páginas (continuationToken)."""
    cfg = _config()
    url = f"{cfg['base_url']}/{rota.lstrip('/')}"
    headers = _headers()
    registros: list[dict] = []
    p = dict(params)
    guard = 0
    while guard < 1000:
        guard += 1
        resp = _get_com_retry(url, headers, p)
        if resp.status_code in (401, 403):
            raise ConsistemError(
                f"Acesso negado (HTTP {resp.status_code}). O serviço pode não estar "
                "liberado no token (CSMEN050 → aba Serviço). "
                f"Detalhe: {resp.text[:200]}"
            )
        if not resp.ok:
            raise ConsistemError(f"Consistem HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json() if resp.content else {}
        if isinstance(body, list):
            registros.extend(body)
            break
        registros.extend(body.get("data") or body.get("Data") or [])
        cont = body.get("continuationToken") or body.get("ContinuationToken")
        if not cont:
            break
        p["continuationToken"] = cont
    return registros


# --------------------------------------------------------------------------- #
# Domínio
# --------------------------------------------------------------------------- #
def buscar_clientes() -> dict[str, dict]:
    """Mapa {codCliente: {'nome', 'cpf_cnpj'}} dos clientes (para enriquecer nomes)."""
    regs = _buscar_todas_paginas(
        "cadastrosgerais/v10/cliente",
        {"situacao": 1, "paginacao": PAGINACAO},
    )
    mapa: dict[str, dict] = {}
    for r in regs:
        cod = str(r.get("codCliente", "")).strip()
        if cod:
            mapa[cod] = {
                "nome": (r.get("nome") or r.get("nomeFantasia") or "").strip(),
                "cpf_cnpj": str(r.get("cpfCnpj") or "").strip(),
            }
    return mapa


def _parse_data_api(v) -> Optional[date]:
    """Datas da API vêm em ISO (YYYY-MM-DD). Cai no parser br como reserva."""
    if not v:
        return None
    s = str(v).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return parse_data_br(v)


def _titulo_de_registro(r: dict, clientes: dict[str, dict]) -> TituloCarteira:
    """Mapeia um registro de contasReceber para TituloCarteira."""
    cod_cliente = str(r.get("codCliente", "")).strip()
    cod_portador = str(r.get("codPortador", "")).strip()
    info = clientes.get(cod_cliente, {})
    return TituloCarteira(
        titulo=str(r.get("codTitulo", "")).strip(),
        cliente_codigo=cod_cliente,
        cliente_nome=info.get("nome", ""),
        emissao=_parse_data_api(r.get("dataEmissao")),
        vencimento=_parse_data_api(r.get("dataVenc")),
        valor=parse_valor_br(r.get("valorTitulo")) or Decimal("0.00"),
        portador_codigo=cod_portador,
        # a API não devolve o nome do portador; só sinalizamos AKF (998) para o display.
        portador_nome="AKF" if cod_portador == PORTADOR_AKF_CODIGO else "",
        tipo_cobranca=str(r.get("tipoCobranca", "")).strip(),
        cnpj_grupo=cod_cliente,  # sem "Código Grupo" na API; usa o cliente p/ concentração
    )


def buscar_titulos_abertos(enriquecer_nomes: bool = True) -> list[TituloCarteira]:
    """Busca os títulos em aberto (carteira) via API e devolve list[TituloCarteira].

    ``enriquecer_nomes`` faz um GET extra em /cliente para preencher o nome do
    cliente (a contasReceber só traz o código).
    """
    regs = _buscar_todas_paginas(
        "financeiro/v10/contasReceber",
        {"tipoTitulo": 0, "paginacao": PAGINACAO},  # 0 = em aberto
    )
    clientes = buscar_clientes() if enriquecer_nomes else {}
    hoje = date.today()
    titulos: list[TituloCarteira] = []
    for r in regs:
        t = _titulo_de_registro(r, clientes)
        if not t.titulo:
            continue
        # dias de atraso/prazo não vêm na API — calculamos a partir das datas.
        if t.vencimento:
            t.dias_atraso = max(0, (hoje - t.vencimento).days)
            if t.emissao:
                t.dias_prazo = max(0, (t.vencimento - t.emissao).days)
        titulos.append(t)
    return titulos
