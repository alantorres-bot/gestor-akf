from datetime import date
from decimal import Decimal

from gestor_akf.conciliacao import Pedido, conciliar
from gestor_akf.modelos import Bordero, TituloBordero

D = Decimal


def _bordero(numero, conexao, titulos, recompras=D("0")):
    b = Bordero(numero=numero, conexao=conexao, recompras=recompras)
    b.titulos = titulos
    b.valor_liquido = sum((t.valor_liquido for t in titulos), D("0"))
    return b


def _tb(doc, valor, venc=None, desagio=D("0"), sacado=""):
    return TituloBordero(
        documento=doc, valor_face=D(valor), desagio=desagio,
        vencimento=venc, sacado=sacado,
    )


def test_tudo_bate():
    pedidos = [Pedido("1261/2", D("440000"), date(2026, 7, 18))]
    bd = _bordero("8585", "PRODUCAO", [_tb("1261/2", "440000", date(2026, 7, 18), D("17424"))])
    r = conciliar(pedidos, [bd])
    assert r.casados == ["1261/2"]
    assert r.por_tipo("nao_operada") == []
    assert r.por_tipo("valor") == []


def test_nf_nao_operada():
    pedidos = [Pedido("1000", D("50000")), Pedido("2000", D("30000"))]
    bd = _bordero("8585", "PRODUCAO", [_tb("1000", "50000")])
    r = conciliar(pedidos, [bd])
    nao = r.por_tipo("nao_operada")
    assert len(nao) == 1
    assert nao[0].documento == "2000"


def test_divergencia_de_valor():
    pedidos = [Pedido("1000", D("50000"))]
    bd = _bordero("8585", "PRODUCAO", [_tb("1000", "55000")])
    r = conciliar(pedidos, [bd])
    assert len(r.por_tipo("valor")) == 1
    assert "1000" not in r.casados


def test_duplicidade():
    pedidos = [Pedido("1000", D("50000"))]
    bd = _bordero("8585", "PRODUCAO", [_tb("1000", "50000"), _tb("1000", "50000")])
    r = conciliar(pedidos, [bd])
    assert len(r.por_tipo("duplicidade")) == 1


def test_operado_sem_pedido():
    pedidos = [Pedido("1000", D("50000"))]
    bd = _bordero("8585", "PRODUCAO", [_tb("1000", "50000"), _tb("9999", "12000")])
    r = conciliar(pedidos, [bd])
    extras = r.por_tipo("so_no_bordero")
    assert len(extras) == 1
    assert extras[0].documento == "9999"


def test_recompra_sinalizada():
    pedidos = [Pedido("1000", D("50000"))]
    bd = _bordero("8585", "PRODUCAO", [_tb("1000", "50000")], recompras=D("168568.52"))
    r = conciliar(pedidos, [bd])
    assert len(r.por_tipo("recompra")) == 1


def test_diferenca_por_fora_no_par():
    pedidos = [Pedido("1261/2", D("440000"))]
    bd = _bordero("8585", "PRODUCAO", [_tb("1261/2", "440000", desagio=D("17424"))])
    bf = _bordero("7104", "PRODUCAO02", [_tb("1261/2", "440000", desagio=D("33264"))])
    r = conciliar(pedidos, [bd, bf])
    assert r.diferenca_por_fora is not None
    assert r.diferenca_por_fora.diferenca == D("15840.00")


def test_casa_por_valor_quando_doc_difere():
    # doc do pedido (carteira) difere do doc do borderô, mas valor+venc batem
    pedidos = [Pedido("4002195U", D("440000"), date(2026, 7, 18))]
    bd = _bordero("8585", "PRODUCAO", [_tb("1261/2", "440000", date(2026, 7, 18))])
    r = conciliar(pedidos, [bd])
    assert r.casados == ["4002195U"]
    assert r.por_tipo("nao_operada") == []
