"""Testes da integração com a API do Consistem.

Os unitários NÃO tocam a rede — injetam respostas JSON simuladas via monkeypatch.
O teste ao vivo (marcado `api`) só roda se houver token configurado.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from gestor_akf import consistem_api as capi
from gestor_akf.carteira import resumir


# --------------------------------------------------------------------------- #
# Resposta HTTP simulada
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.content = b"x"
        self.text = "" if isinstance(payload, (dict, list)) else str(payload)

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def _fake_paginado(paginas):
    """Devolve uma função que serve `paginas` em sequência (simula continuationToken)."""
    chamadas = {"n": 0}

    def _get(url, headers, params, timeout=None):  # assinatura de requests.get
        i = chamadas["n"]
        chamadas["n"] += 1
        return _FakeResp(paginas[min(i, len(paginas) - 1)])

    return _get, chamadas


# --------------------------------------------------------------------------- #
# Mapeamento contasReceber -> TituloCarteira
# --------------------------------------------------------------------------- #
def test_mapeia_registro_basico():
    r = {
        "codTitulo": "001/2024",
        "codCliente": 123,
        "codPortador": 91,
        "tipoCobranca": 1,
        "dataEmissao": "2024-01-15",
        "dataVenc": "2024-02-15",
        "dataPagamento": None,
        "valorTitulo": 1500.50,
    }
    t = capi._titulo_de_registro(r, {"123": {"nome": "Exemplo Ltda", "cpf_cnpj": "x"}})
    assert t.titulo == "001/2024"
    assert t.cliente_codigo == "123"
    assert t.cliente_nome == "Exemplo Ltda"
    assert t.emissao == date(2024, 1, 15)
    assert t.vencimento == date(2024, 2, 15)
    assert t.valor == Decimal("1500.50")
    assert t.portador_codigo == "91"
    assert t.disponivel is True
    assert t.antecipado is False


def test_classifica_portador_998_como_antecipado():
    r = {"codTitulo": "T1", "codCliente": 1, "codPortador": 998, "valorTitulo": 100}
    t = capi._titulo_de_registro(r, {})
    assert t.portador_codigo == "998"
    assert t.portador_nome == "AKF"
    assert t.antecipado is True
    assert t.disponivel is False


def test_valor_aceita_numero_e_string_br():
    # número JSON (financeiro) e string pt-BR (estoque) — a mesma função trata os dois.
    a = capi._titulo_de_registro({"codTitulo": "A", "valorTitulo": 1234.5}, {})
    b = capi._titulo_de_registro({"codTitulo": "B", "valorTitulo": "1.234,50"}, {})
    assert a.valor == Decimal("1234.50")
    assert b.valor == Decimal("1234.50")


def test_valor_ausente_vira_zero():
    t = capi._titulo_de_registro({"codTitulo": "A"}, {})
    assert t.valor == Decimal("0.00")


# --------------------------------------------------------------------------- #
# Paginação por continuationToken
# --------------------------------------------------------------------------- #
def test_paginacao_acumula_todas_as_paginas(monkeypatch):
    paginas = [
        {"data": [{"codTitulo": "A"}], "continuationToken": "p2"},
        {"data": [{"codTitulo": "B"}], "continuationToken": "p3"},
        {"data": [{"codTitulo": "C"}], "continuationToken": ""},
    ]
    get, chamadas = _fake_paginado(paginas)
    monkeypatch.setattr(capi.requests, "get", get)
    monkeypatch.setenv("CONSISTEM_API_KEY", "T" * 60)

    regs = capi._buscar_todas_paginas("financeiro/v10/contasReceber", {"tipoTitulo": 0})
    assert [x["codTitulo"] for x in regs] == ["A", "B", "C"]
    assert chamadas["n"] == 3


def test_resposta_lista_pura(monkeypatch):
    get, _ = _fake_paginado([[{"codTitulo": "X"}, {"codTitulo": "Y"}]])
    monkeypatch.setattr(capi.requests, "get", get)
    monkeypatch.setenv("CONSISTEM_API_KEY", "T" * 60)
    regs = capi._buscar_todas_paginas("financeiro/v10/contasReceber", {})
    assert len(regs) == 2


# --------------------------------------------------------------------------- #
# Erros
# --------------------------------------------------------------------------- #
def test_servico_nao_liberado_gera_erro_amigavel(monkeypatch):
    def _get(url, headers, params, timeout=None):
        return _FakeResp("Serviço não liberado", status=403)

    monkeypatch.setattr(capi.requests, "get", _get)
    monkeypatch.setenv("CONSISTEM_API_KEY", "T" * 60)
    with pytest.raises(capi.ConsistemError, match="Acesso negado"):
        capi._buscar_todas_paginas("financeiro/v10/contasReceber", {})


def test_sem_token_gera_erro(monkeypatch):
    monkeypatch.delenv("CONSISTEM_API_KEY", raising=False)
    monkeypatch.setattr(capi, "carregar_token", lambda: "")
    with pytest.raises(capi.ConsistemError, match="Token"):
        capi._headers()


# --------------------------------------------------------------------------- #
# Fluxo completo (mock) -> resumir
# --------------------------------------------------------------------------- #
def test_buscar_titulos_abertos_fluxo(monkeypatch):
    contas = [{
        "data": [
            {"codTitulo": "1001U", "codCliente": 10, "codPortador": 998,
             "dataVenc": "2024-02-10", "dataEmissao": "2024-01-10", "valorTitulo": 1000},
            {"codTitulo": "1002U", "codCliente": 20, "codPortador": 91,
             "dataVenc": "2024-03-10", "dataEmissao": "2024-01-10", "valorTitulo": 500},
        ],
        "continuationToken": "",
    }]
    clientes = [{
        "data": [
            {"codCliente": 10, "nome": "Cliente AKF", "cpfCnpj": "1"},
            {"codCliente": 20, "nome": "Cliente Carteira", "cpfCnpj": "2"},
        ],
        "continuationToken": "",
    }]

    def _get(url, headers, params, timeout=None):
        if "contasReceber" in url:
            return _FakeResp(contas[0])
        if "cliente" in url:
            return _FakeResp(clientes[0])
        raise AssertionError(f"rota inesperada: {url}")

    monkeypatch.setattr(capi.requests, "get", _get)
    monkeypatch.setenv("CONSISTEM_API_KEY", "T" * 60)

    titulos = capi.buscar_titulos_abertos()
    assert len(titulos) == 2
    nomes = {t.titulo: t.cliente_nome for t in titulos}
    assert nomes == {"1001U": "Cliente AKF", "1002U": "Cliente Carteira"}

    r = resumir(titulos)
    assert r.total_titulos == 2
    assert r.antecipados_qtd == 1          # 998
    assert r.disponiveis_qtd == 1          # 91
    assert r.total_valor == Decimal("1500.00")


# --------------------------------------------------------------------------- #
# Teste ao vivo (opcional)
# --------------------------------------------------------------------------- #
@pytest.mark.api
def test_api_ao_vivo():
    if not capi.token_configurado():
        pytest.skip("CONSISTEM_API_KEY não configurado")
    titulos = capi.buscar_titulos_abertos(enriquecer_nomes=False)
    assert isinstance(titulos, list)
