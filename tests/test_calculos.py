"""Testes das regras de negócio, ancorados no caso de referência 8585/7104."""

from decimal import Decimal

from gestor_akf.calculos import (
    calcular_desembolso,
    calcular_recompra,
    conferir_bordero,
    custo_real_operacao,
    diferenca_por_fora,
    taxa_efetiva_mensal,
)
from gestor_akf.modelos import Bordero, TituloBordero

D = Decimal


def _bordero_8585() -> Bordero:
    return Bordero(
        numero="8585", conexao="PRODUCAO", cliente="NEO FORMAS",
        total_bordero=D("440000.00"), desagio=D("17424.00"),
        valor_liquido=D("422576.00"), recompras=D("168568.52"),
        creditos=D("0.00"), debitos=D("45.00"), abatimento=D("0.00"),
        desembolso=D("253962.48"),
        titulos=[TituloBordero(documento="1261/2", valor_face=D("440000.00"),
                               desagio=D("17424.00"))],
    )


def _bordero_7104() -> Bordero:
    return Bordero(
        numero="7104", conexao="PRODUCAO02", cliente="NEO FORMAS PARA CONCRETO",
        total_bordero=D("440000.00"), desagio=D("33264.00"),
        valor_liquido=D("406736.00"), recompras=D("168568.52"),
        creditos=D("0.00"), debitos=D("45.00"), abatimento=D("0.00"),
        desembolso=D("238122.48"),
        titulos=[TituloBordero(documento="1261/2", valor_face=D("440000.00"),
                               desagio=D("33264.00"))],
    )


# --- Desembolso ------------------------------------------------------------ #
def test_desembolso_8585():
    r = calcular_desembolso(D("440000.00"), D("17424.00"),
                            recompras=D("168568.52"), debitos=D("45.00"))
    assert r.valor_liquido == D("422576.00")
    assert r.desembolso == D("253962.48")


def test_desembolso_7104():
    r = calcular_desembolso(D("440000.00"), D("33264.00"),
                            recompras=D("168568.52"), debitos=D("45.00"))
    assert r.valor_liquido == D("406736.00")
    assert r.desembolso == D("238122.48")


# --- Diferença por fora ---------------------------------------------------- #
def test_diferenca_por_fora_15840():
    r = diferenca_por_fora(_bordero_8585(), _bordero_7104())
    assert r.diferenca == D("15840.00")
    assert r.liquido_por_dentro == D("422576.00")
    assert r.liquido_por_fora == D("406736.00")


# --- Recompra -------------------------------------------------------------- #
def test_recompra_com_multa_2pct():
    # Exemplo 29/05: regresso 2955, correção 1.945,53, multa 2%
    total = calcular_recompra(D("163356.00"), correcao=D("1945.53"))
    multa = D("163356.00") * D("0.02")  # 3267.12
    assert total == (D("163356.00") + D("1945.53") + multa).quantize(D("0.01"))


# --- Conferência (auditoria) ----------------------------------------------- #
def test_conferir_bordero_ok():
    assert conferir_bordero(_bordero_8585()) == []
    assert conferir_bordero(_bordero_7104()) == []


def test_conferir_bordero_flagra_erro():
    b = _bordero_8585()
    b.desembolso = D("999999.99")  # simula erro de OCR
    problemas = conferir_bordero(b)
    assert problemas
    assert any("Desembolso" in p for p in problemas)


# --- Custo efetivo --------------------------------------------------------- #
def test_taxa_efetiva_positiva():
    # face 440k, deságio oficial 17.424, prazo 50 dias
    taxa = taxa_efetiva_mensal(D("17424.00"), D("440000.00"), 50)
    assert taxa is not None
    assert D("0.02") < taxa < D("0.03")   # ~2,4% a.m.


def test_taxa_efetiva_dias_invalidos():
    assert taxa_efetiva_mensal(D("100"), D("1000"), 0) is None


def test_custo_real_maior_que_oficial():
    """O custo real (por dentro + por fora) deve ser ~o dobro do oficial."""
    cr = custo_real_operacao(_bordero_8585(), _bordero_7104(), dias=50)
    assert cr.custo_oficial == D("17424.00")
    assert cr.custo_por_fora == D("15840.00")
    assert cr.custo_total == D("33264.00")
    assert cr.taxa_real_am > cr.taxa_oficial_am
