from datetime import date
from decimal import Decimal

from gestor_akf.carteira import TituloCarteira
from gestor_akf.parametros import Parametros, carregar_parametros
from gestor_akf.selecao import selecionar_titulos

D = Decimal


def _t(titulo, valor, venc, cliente="CLIENTE X", cod="1", portador="91"):
    return TituloCarteira(
        titulo=titulo, cliente_codigo=cod, cliente_nome=cliente,
        vencimento=date.fromisoformat(venc), valor=D(valor),
        portador_codigo=portador, portador_nome="CARTEIRA",
    )


def _params(**kw):
    base = dict(
        clientes_sem_boleto_factoring=["MIP"], observacao_sem_boleto="Sem boleto.",
        limite_global_akf=D("0"), limite_por_sacado={}, multa_recompra=D("0.02"),
        taxa_referencia_am=D("0.02"), taxas_bancarias_am={},
        concentracao_maxima_por_sacado=D("0"), contatos_akf={},
    )
    base.update(kw)
    return Parametros(**base)


REF = date(2026, 6, 28)


def test_prioriza_menor_prazo():
    titulos = [
        _t("A", "100000", "2026-09-01"),   # prazo longo
        _t("B", "100000", "2026-07-10"),   # prazo curto -> deve vir 1º
        _t("C", "100000", "2026-08-01"),
    ]
    r = selecionar_titulos(titulos, D("150000"), REF, _params())
    assert r.itens[0].titulo.titulo == "B"
    assert r.itens[1].titulo.titulo == "C"
    assert r.atingiu_alvo is True
    assert r.valor_total == D("200000")  # 2 títulos cobrem 150k


def test_ignora_antecipados_e_vencidos():
    titulos = [
        _t("A", "50000", "2026-07-10"),
        _t("ANTEC", "50000", "2026-07-10", portador="998"),  # já na AKF
        _t("VENC", "50000", "2026-06-01"),                   # vencido
    ]
    r = selecionar_titulos(titulos, D("200000"), REF, _params())
    nomes = {i.titulo.titulo for i in r.itens}
    assert "ANTEC" not in nomes
    assert "VENC" not in nomes
    assert r.atingiu_alvo is False  # só A (50k) disponível < 200k


def test_marca_sem_boleto():
    titulos = [_t("A", "50000", "2026-07-10", cliente="MIP ENGENHARIA", cod="9")]
    r = selecionar_titulos(titulos, D("40000"), REF, _params())
    assert r.itens[0].sem_boleto is True
    assert "boleto" in r.itens[0].observacao.lower()


def test_limite_global_nao_e_aplicado():
    # O limite global da AKF é volátil -> NÃO barra mais a seleção, mesmo configurado.
    titulos = [_t("A", "100000", "2026-07-10"), _t("B", "100000", "2026-07-11")]
    r = selecionar_titulos(
        titulos, D("200000"), REF, _params(limite_global_akf=D("1000000")),
        exposicao_atual=D("950000"),
    )
    assert r.qtd == 2
    assert r.excluidos_limite == []
    assert r.atingiu_alvo is True


def test_concentracao_nao_e_aplicada():
    # Concentração máxima por sacado também não barra mais.
    titulos = [
        _t("A", "60000", "2026-07-10", cliente="SACADO 1", cod="1"),
        _t("B", "60000", "2026-07-11", cliente="SACADO 1", cod="1"),
        _t("C", "60000", "2026-07-12", cliente="SACADO 2", cod="2"),
    ]
    r = selecionar_titulos(
        titulos, D("150000"), REF, _params(concentracao_maxima_por_sacado=D("0.30")),
    )
    nomes = {i.titulo.titulo for i in r.itens}
    assert {"A", "B", "C"} == nomes          # todos entram, sem barrar
    assert r.excluidos_concentracao == []


def test_custo_e_desembolso_estimados():
    titulos = [_t("A", "100000", "2026-07-28")]  # 30 dias
    r = selecionar_titulos(titulos, D("100000"), REF, _params(taxa_referencia_am=D("0.02")))
    # 30 dias, taxa 2% a.m. -> deságio ~ 2000
    assert r.custo_estimado == D("2000.00")
    assert r.desembolso_estimado == D("98000.00")
    assert r.taxa_estimada_am is not None
