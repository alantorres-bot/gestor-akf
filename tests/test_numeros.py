from decimal import Decimal

import pytest

from gestor_akf.numeros import formatar_pct, formatar_valor_br, parse_valor_br


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("440.000,00", Decimal("440000.00")),
        ("17.424,00", Decimal("17424.00")),
        ("168.568,52", Decimal("168568.52")),
        ("45,00", Decimal("45.00")),
        ("0,00", Decimal("0.00")),
        ("R$ 1.451.340,86", Decimal("1451340.86")),
        ("-25.525,29", Decimal("-25525.29")),
        ("1234.56", Decimal("1234.56")),   # ponto como decimal
        ("1,5", Decimal("1.50")),
        (440000, Decimal("440000")),
        (Decimal("10.10"), Decimal("10.10")),
    ],
)
def test_parse_valor_br(entrada, esperado):
    assert parse_valor_br(entrada) == esperado


def test_parse_valor_vazio():
    assert parse_valor_br("") is None
    assert parse_valor_br(None) is None
    assert parse_valor_br("Desembolso") is None


def test_parse_ruido_ocr():
    # OCR às vezes lê 'O' no lugar de zero
    assert parse_valor_br("44O.000,00") == Decimal("440000.00")


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (Decimal("440000.00"), "440.000,00"),
        (Decimal("253962.48"), "253.962,48"),
        (Decimal("45"), "45,00"),
        (Decimal("-25525.29"), "-25.525,29"),
        (Decimal("1451340.86"), "1.451.340,86"),
    ],
)
def test_formatar_valor_br(valor, esperado):
    assert formatar_valor_br(valor) == esperado


def test_formatar_com_simbolo():
    assert formatar_valor_br(Decimal("440000"), com_simbolo=True) == "R$ 440.000,00"


def test_formatar_pct():
    assert formatar_pct(Decimal("0.0245")) == "2,45%"
    assert formatar_pct(Decimal("0.0218")) == "2,18%"
