import os
from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from gestor_akf.passivo import importar_planilha_por_fora

D = Decimal


@pytest.fixture
def planilha(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilha2"
    ws.append(["CONTROLE DE JUROS", None, None, None, None, None, None])
    ws.append(["DATA", "BASE 01", "BASE 02", "VALOR", "PAGAMENTOS", "SALDO", "OBSERVAÇÃO"])
    ws.append([date(2025, 2, 19), "6841", "5804", 1523.50, None, 1523.50, ""])
    ws.append([date(2025, 2, 24), None, None, None, 1000.00, -1000.00, "ABATIMENTO PGTO"])
    ws.append([date(2025, 11, 19), None, None, None, 500.00, 500.00, "DEVOLUÇÃO ABATIDO A MAIOR"])
    ws.append([None, None, None, None, None, None, None])  # linha vazia
    p = tmp_path / "planilha.xlsx"
    wb.save(str(p))
    return str(p)


def test_importa_e_separa_estorno(planilha):
    r = importar_planilha_por_fora(planilha)
    assert r.qtd == 3                       # ignora a linha vazia
    assert r.total_gerado == D("1523.50")
    assert r.total_pago == D("1000.00")     # NÃO inclui a devolução
    assert r.total_estornado == D("500.00")
    # saldo = gerado - pago + estorno = 1523.50 - 1000 + 500 = 1023.50
    assert r.saldo == D("1023.50")


def test_lancamentos_tem_borderos(planilha):
    r = importar_planilha_por_fora(planilha)
    primeiro = r.lancamentos[0]
    assert primeiro.base01 == "6841"
    assert primeiro.base02 == "5804"
    assert primeiro.data == date(2025, 2, 19)


def test_marca_estorno(planilha):
    r = importar_planilha_por_fora(planilha)
    estornos = [l for l in r.lancamentos if l.eh_estorno]
    assert len(estornos) == 1
    assert estornos[0].estorno == D("500.00")


# --- Integração: planilha real (se disponível) ----------------------------- #
_REAL = "C:/Users/alant/Downloads/PLANILHA NEO FORMAS CONTROLE JUROS POR FORA - AKF (1).xlsx"


@pytest.mark.skipif(not os.path.exists(_REAL), reason="planilha real não disponível")
def test_real_saldo_91390():
    r = importar_planilha_por_fora(_REAL, aba="Planilha2")
    assert r.total_gerado == D("1451340.86")
    assert r.total_pago == D("1385475.51")
    assert r.total_estornado == D("25525.29")
    assert r.saldo == D("91390.64")
