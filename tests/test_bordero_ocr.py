"""Testes do parser de borderô.

`parse_linhas` é testado com as linhas REAIS de OCR (fixtures abaixo), então
roda rápido e é determinístico. O teste marcado `ocr` roda o OCR de verdade
sobre o PDF original, se ele estiver disponível na pasta do Drive.
"""

import os
from decimal import Decimal

import pytest

from gestor_akf.bordero_ocr import parse_bordero, parse_linhas
from gestor_akf.calculos import conferir_bordero, diferenca_por_fora

D = Decimal

# Linhas exatamente como o OCR (rapidocr @300dpi) devolveu para os PDFs reais.
LINHAS_8585 = [
    "DECLARACAO DE RECEBIMENTO N° - 8585", "(QUITACAO)", "Cliente:",
    "NEO FORMAS - 17.209.767/0001-28", "Desagio", "Documento", "Vencimento",
    "Tipo Sacado", "CNPJICPF", "Valor Face", "DM", "1261/2", "18/07/2026",
    "17.424,00", "15776 - IMOBILIARIA ECONSTRUTORA GEORGIA",
    "14.911.473/0001-55", "440.000,00", "TOTAL:", "Quantidade:", "17.424,00",
    "440.000,00", "Total do bordero", "440.000,00", "(-） Desagio", "17.424,00",
    "Valor Liquido", "422.576,00", "(-) Recompras", "168.568,52",
    "(+ ）Créditos", "0,00", "(-) Débitos", "45,00", "(-) Abatimento / Desconto",
    "0,00", "Desembolso", "253.962,48", "CUIABA, 29 de Maio de 2026.",
    "Conexao: PRODUCAO",
]

LINHAS_7104 = [
    "DECLARACAO DE RECEBIMENTO N° - 7104", "(QUITACAO)", "Cliente:", "Desagio",
    "Documento", "CNPJICPF", "Vencimento", "Tipo Sacado", "Valor Face", "DM",
    "1261/2", "18/07/2026", "33.264,00",
    "14248 - IMOBILIARIA ECONSTRUTORA GEORGIA", "14.911.473/0001-55",
    "440.000,00", "TOTAL:", "Quantidade:", "33.264,00", "440.000,00",
    "Total do bordero", "440.000,00", "（-） Desagio", "33.264,00",
    "Valor Liquido", "406.736,00", "(-) Recompras", "168.568,52",
    "(+ ）Créditos", "0,00", "(-) Débitos", "45,00", "(-) Abatimento / Desconto",
    "0,00", "Desembolso", "238.122,48",
    "NEO FORMAS PARA CONCRETO EIRELI, declara haver recebido",
    "CUIABA, 29 de Maio de 2026.", "Conexao: PRODUCAO02",
]


def test_parse_8585_totais():
    b = parse_linhas(LINHAS_8585, origem="8585.pdf")
    assert b.numero == "8585"
    assert b.conexao == "PRODUCAO"
    assert b.por_dentro is True
    assert b.total_bordero == D("440000.00")
    assert b.desagio == D("17424.00")
    assert b.valor_liquido == D("422576.00")
    assert b.recompras == D("168568.52")
    assert b.debitos == D("45.00")
    assert b.desembolso == D("253962.48")
    assert b.data is not None and b.data.isoformat() == "2026-05-29"
    assert conferir_bordero(b) == []


def test_parse_7104_totais():
    b = parse_linhas(LINHAS_7104, origem="7104.pdf")
    assert b.numero == "7104"
    assert b.conexao == "PRODUCAO02"
    assert b.por_fora is True
    assert b.desagio == D("33264.00")
    assert b.valor_liquido == D("406736.00")
    assert b.desembolso == D("238122.48")
    assert conferir_bordero(b) == []


def test_parse_titulo_8585():
    b = parse_linhas(LINHAS_8585)
    assert len(b.titulos) == 1
    t = b.titulos[0]
    assert t.documento == "1261/2"
    assert t.valor_face == D("440000.00")
    assert t.desagio == D("17424.00")
    assert t.vencimento is not None and t.vencimento.isoformat() == "2026-07-18"
    assert t.sacado_cnpj and "14.911.473" in t.sacado_cnpj


def test_diferenca_a_partir_dos_dois_parses():
    bd = parse_linhas(LINHAS_8585)
    bf = parse_linhas(LINHAS_7104)
    assert diferenca_por_fora(bd, bf).diferenca == D("15840.00")


# --------------------------------------------------------------------------- #
# Integração: OCR real (lento). Pulado se o PDF não estiver acessível.
# --------------------------------------------------------------------------- #
_BASE = (
    "g:/Drives compartilhados/Neo Formas Publico/FINANCEIRO NEO FORMAS/"
    "03 - CONTABILIDADE/BORDEROS/2026/AKF/05 - Maio/29"
)


@pytest.mark.ocr
@pytest.mark.skipif(
    not os.path.exists(os.path.join(_BASE, "BORDERO 8585.pdf")),
    reason="PDF de referência não acessível",
)
def test_ocr_real_8585():
    b = parse_bordero(os.path.join(_BASE, "BORDERO 8585.pdf"))
    assert b.numero == "8585"
    assert b.desembolso == D("253962.48")
    assert b.avisos == []
