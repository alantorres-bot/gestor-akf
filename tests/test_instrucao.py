from datetime import date
from decimal import Decimal

from gestor_akf.carteira import TituloCarteira
from gestor_akf.instrucao import gerar_instrucao
from gestor_akf.parametros import Parametros
from gestor_akf.selecao import selecionar_titulos

D = Decimal
REF = date(2026, 6, 28)


def _params():
    return Parametros(
        clientes_sem_boleto_factoring=["MIP"],
        observacao_sem_boleto="Operar 1 dia após o vencimento, sem emitir boleto.",
        limite_global_akf=D("0"), limite_por_sacado={}, multa_recompra=D("0.02"),
        taxa_referencia_am=D("0.02"), taxas_bancarias_am={},
        concentracao_maxima_por_sacado=D("0"),
        contatos_akf={"para": ["andre.kamil@akfsec.com.br"], "cc": ["akfsec@outlook.com"]},
    )


def _t(titulo, valor, venc, cliente, cod):
    return TituloCarteira(
        titulo=titulo, cliente_codigo=cod, cliente_nome=cliente,
        vencimento=date.fromisoformat(venc), valor=D(valor),
        portador_codigo="91", portador_nome="CARTEIRA",
    )


def test_instrucao_separa_sem_boleto():
    titulos = [
        _t("A", "50000", "2026-07-10", "CONSTRUTORA NORMAL", "1"),
        _t("B", "30000", "2026-07-12", "MIP ENGENHARIA", "2"),
    ]
    sel = selecionar_titulos(titulos, D("80000"), REF, _params())
    instr = gerar_instrucao(sel, _params(), data_operacao=REF)

    assert "andre.kamil@akfsec.com.br" in instr.para
    assert "akfsec@outlook.com" in instr.cc
    assert "28/06/2026" in instr.assunto
    # título normal e bloco sem boleto presentes
    assert "NF A" in instr.corpo
    assert "SEM BOLETO DE FACTORING" in instr.corpo
    assert "1 dia após o vencimento" in instr.corpo
    assert "NF B" in instr.corpo
    # total geral
    assert "TOTAL GERAL" in instr.corpo
