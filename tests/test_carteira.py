import os
from datetime import date
from decimal import Decimal

import pytest

from gestor_akf.carteira import carregar_carteira, resumir

D = Decimal

# CSV sintético no mesmo formato do Consistem (cp1252/;), para teste determinístico.
CSV_SINTETICO = (
    "Título;Cliente;Nome Cliente;Emissão;Vencimento;Valor;Portador;Nome Portador;"
    "Descrição Tipo de Cobrança;Dias Atraso;Dias Prazo;Empresa;Representante;"
    "Dias Prorrogados;Dias Vencer;Borderô;Código Tipo;Código Grupo;Tipo de Cobrança;"
    "Descrição Conceito Cliente;Valor do Desconto;NSU Cartão;Tipo Vencimento;"
    "Conta Bancária;Atendente;Observação do Título\n"
    "1001187U;144;CANOPUS SPE LTDA;25/03/2026;30/04/2026;17.000,00;998;AKF;DESCONTO;"
    "59;36;1;2;7;0;;0;49437905;3;;;;Vencimento;121212;;\n"
    "1001285U;105;MULTHIFER LTDA;24/06/2026;24/07/2026;1.328,00;91;CARTEIRA;CARTEIRA;"
    "0;30;1;2;;26;;0;08909912;1;;;;Vencimento;;;\n"
    "4002118U;33;SOMATTOS SPE;16/03/2026;20/04/2026;1.336,64;237;BRADESCO;SIMPLES;"
    "69;35;1;5;;0;;0;42360157;2;;;;Vencimento;;;\n"
)


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "carteira.csv"
    p.write_bytes(CSV_SINTETICO.encode("cp1252"))
    return str(p)


def test_carregar_basico(csv_path):
    ts = carregar_carteira(csv_path)
    assert len(ts) == 3
    t = ts[0]
    assert t.titulo == "1001187U"
    assert t.cliente_nome == "CANOPUS SPE LTDA"
    assert t.emissao == date(2026, 3, 25)
    assert t.vencimento == date(2026, 4, 30)
    assert t.valor == D("17000.00")
    assert t.cnpj_grupo == "49437905"


def test_classificacao_antecipado(csv_path):
    ts = carregar_carteira(csv_path)
    by = {t.titulo: t for t in ts}
    assert by["1001187U"].antecipado is True       # portador 998 AKF
    assert by["1001285U"].disponivel is True       # CARTEIRA
    assert by["4002118U"].disponivel is True       # BRADESCO
    assert by["4002118U"].vencido is True          # dias_atraso 69


def test_resumo(csv_path):
    r = resumir(carregar_carteira(csv_path))
    assert r.total_titulos == 3
    assert r.antecipados_qtd == 1
    assert r.antecipados_valor == D("17000.00")
    assert r.disponiveis_qtd == 2
    assert r.disponiveis_valor == D("2664.64")


def test_dias_ate_vencimento(csv_path):
    t = carregar_carteira(csv_path)[0]
    assert t.dias_ate_vencimento(date(2026, 4, 20)) == 10


# --- Integração: arquivos reais do Consistem (se disponíveis) -------------- #
_REAL_AKF = "C:/Users/alant/Downloads/Consulta de Títulos em Aberto.csv"
_REAL_NAO = "C:/Users/alant/Downloads/Consulta de Títulos em Aberto NÃO ANTECIPADOS.csv"


@pytest.mark.skipif(not os.path.exists(_REAL_AKF), reason="CSV real não disponível")
def test_real_antecipados():
    ts = carregar_carteira(_REAL_AKF)
    assert len(ts) > 0
    # Esse arquivo é o de títulos COM portador AKF.
    assert all(t.antecipado for t in ts)


@pytest.mark.skipif(not os.path.exists(_REAL_NAO), reason="CSV real não disponível")
def test_real_nao_antecipados():
    ts = carregar_carteira(_REAL_NAO)
    assert len(ts) > 0
    assert all(t.disponivel for t in ts)
