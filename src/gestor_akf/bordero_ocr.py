"""Parser de borderôs em PDF (Declaração de Recebimento / Quitação da AKF).

Os borderôs são PDFs *escaneados* (imagem, sem camada de texto), então o
fluxo é: renderizar a página em imagem (pymupdf) -> OCR local (rapidocr) ->
interpretar as linhas de texto.

Para manter os testes rápidos e auditáveis, o módulo separa duas etapas:
  * ocr_paginas(pdf)  -> lista de linhas de texto  (lento; precisa do PDF)
  * parse_linhas(...) -> Bordero                    (puro; fácil de testar)
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Optional

from .modelos import ZERO, Bordero, TituloBordero
from .numeros import parse_valor_br

# --------------------------------------------------------------------------- #
# Padrões
# --------------------------------------------------------------------------- #
_RE_NUMERO = re.compile(r"RECEBIMENTO[^\d]{0,12}(\d{3,6})", re.IGNORECASE)
_RE_NUMERO_ARQ = re.compile(r"BORDERO[^\d]*(\d{3,6})", re.IGNORECASE)
_RE_CONEXAO = re.compile(r"Conex[aã]o\s*[:\-]?\s*(produ\S*)", re.IGNORECASE)
_RE_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_RE_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
_RE_DOC = re.compile(r"^\d{1,7}(?:[/-]\d{1,3})?$")  # 1261/2, 123456
_RE_TIPO = re.compile(r"^[A-Z]{2,4}$")              # DM, DS, NP, CH...
_RE_VALOR = re.compile(r"^-?[\d.\sOoº]*\d[\d.,\sOoº]*$")  # parece número (com ruído de OCR)
_RE_SACADO_COD = re.compile(r"^(\d{3,6})\s*[-–]\s*(.+)$")  # "15776 - IMOBILIARIA ..."

_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

# Rótulos dos totais -> atributo do Bordero. A ordem importa: procuramos o
# rótulo e pegamos a primeira linha numérica logo abaixo.
_ROTULOS_TOTAIS = [
    ("total do bordero", "total_bordero"),
    ("valor liquido", "valor_liquido"),
    ("recompras", "recompras"),
    ("creditos", "creditos"),
    ("debitos", "debitos"),
    ("abatimento", "abatimento"),
    ("desembolso", "desembolso"),
]


def _norm(s: str) -> str:
    """minúsculas, sem acento, sem pontuação de rótulo."""
    s = s.lower()
    for a, b in [("á", "a"), ("à", "a"), ("â", "a"), ("ã", "a"), ("é", "e"),
                 ("ê", "e"), ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"),
                 ("ú", "u"), ("ç", "c")]:
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


def _parece_valor(linha: str) -> bool:
    t = linha.strip()
    if not t or _RE_CNPJ.search(t) or _RE_DATA.search(t):
        return False
    return bool(_RE_VALOR.match(t)) and any(c.isdigit() for c in t)


def _eh_monetario(linha: str) -> bool:
    """Valor em dinheiro tem SEMPRE vírgula decimal (ex.: 440.000,00).

    Distingue valores de números de documento (1136, 002067), que não têm
    vírgula — evita confundir nº de NF com valor.
    """
    t = linha.strip()
    return "," in t and _parece_valor(t)


def _proximo_valor(linhas: list[str], inicio: int) -> Optional[Decimal]:
    """A partir de `inicio` (exclusive), retorna o 1º valor numérico encontrado."""
    for j in range(inicio + 1, min(inicio + 4, len(linhas))):
        if _parece_valor(linhas[j]):
            return parse_valor_br(linhas[j])
    return None


def _parse_data_extenso(linhas: list[str]) -> Optional[date]:
    """Lê 'CUIABA, 29 de Maio de 2026'."""
    for ln in linhas:
        m = re.search(r"(\d{1,2})\s+de\s+([A-Za-zçãéê]+)\s+de\s+(\d{4})", ln, re.IGNORECASE)
        if m:
            dia, mes_txt, ano = m.group(1), _norm(m.group(2)), m.group(3)
            mes = _MESES.get(mes_txt)
            if mes:
                try:
                    return date(int(ano), mes, int(dia))
                except ValueError:
                    return None
    return None


def _parse_data_br(txt: str) -> Optional[date]:
    m = _RE_DATA.search(txt)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Títulos
# --------------------------------------------------------------------------- #
def _parse_titulos(regiao: list[str]) -> list[TituloBordero]:
    """Interpreta a região de títulos (entre o cabeçalho e 'TOTAL:').

    A ORDEM das colunas varia entre borderôs (ora Deságio vem antes do
    Documento, ora depois), então não dependemos de posição fixa. Em vez disso
    classificamos cada linha pelo seu CONTEÚDO e montamos N títulos, onde
    N = quantidade de CNPJs (cada título tem exatamente um sacado/CNPJ):

      * CNPJs, sacados, datas e documentos saem em ordem de título;
      * valores monetários saem em pares por título; dentro do par,
        deságio < valor de face (deságio é sempre desconto sobre a face),
        então ordenamos o par para separar um do outro.
    """
    docs: list[str] = []
    tipos: list[str] = []
    datas: list[Optional[date]] = []
    sacados: list[tuple[str, str]] = []
    cnpjs: list[str] = []
    valores: list[Decimal] = []

    for ln in regiao:
        t = ln.strip()
        if not t:
            continue
        if _RE_SACADO_COD.match(t) and not _eh_monetario(t):
            m = _RE_SACADO_COD.match(t)
            sacados.append((m.group(1), m.group(2).strip()))
        elif _RE_CNPJ.search(t):
            cnpjs.append(t)
        elif _RE_DATA.search(t):
            datas.append(_parse_data_br(t))
        elif _eh_monetario(t):
            v = parse_valor_br(t)
            if v is not None:
                valores.append(v)
        elif _RE_DOC.match(t):
            docs.append(t)
        elif _RE_TIPO.match(t):
            tipos.append(t)

    n = len(cnpjs)
    titulos: list[TituloBordero] = []

    def _get(lst, i):
        return lst[i] if i < len(lst) else None

    if n >= 1 and len(valores) >= 2 * n:
        for i in range(n):
            par = sorted(valores[2 * i:2 * i + 2])  # [deságio, face]
            sac = _get(sacados, i)
            titulos.append(TituloBordero(
                documento=_get(docs, i) or "",
                valor_face=par[-1],
                desagio=par[0],
                tipo=_get(tipos, i) or "",
                sacado=sac[1] if sac else "",
                sacado_codigo=sac[0] if sac else None,
                sacado_cnpj=cnpjs[i],
                vencimento=_get(datas, i),
            ))
        return titulos

    # Fallback (contagens não batem — OCR perdeu algo): um único título com o
    # que deu para extrair. A conferência de totais sinalizará a divergência.
    if valores:
        par = sorted(valores)
        sac = _get(sacados, 0)
        titulos.append(TituloBordero(
            documento=_get(docs, 0) or "",
            valor_face=par[-1],
            desagio=par[0] if len(par) >= 2 else ZERO,
            tipo=_get(tipos, 0) or "",
            sacado=sac[1] if sac else "",
            sacado_codigo=sac[0] if sac else None,
            sacado_cnpj=_get(cnpjs, 0),
            vencimento=_get(datas, 0),
        ))
    return titulos


# --------------------------------------------------------------------------- #
# Parser principal (puro)
# --------------------------------------------------------------------------- #
def parse_linhas(linhas: list[str], origem: str = "") -> Bordero:
    """Constrói um Bordero a partir das linhas de texto (OCR ou outra fonte)."""
    linhas = [l.rstrip() for l in linhas if l is not None]
    texto = "\n".join(linhas)

    m = _RE_NUMERO.search(texto)
    numero = m.group(1) if m else ""
    if not numero and origem:
        ma = _RE_NUMERO_ARQ.search(origem)
        if ma:
            numero = ma.group(1)

    mc = _RE_CONEXAO.search(texto)
    conexao = ""
    if mc:
        tok = mc.group(1).upper()
        # OCR varia: "PRODUCAO", "Produgao", "PRODUÇÃO02"... normalizamos.
        conexao = "PRODUCAO02" if "02" in tok else "PRODUCAO"

    b = Bordero(numero=numero, conexao=conexao, origem_arquivo=origem)
    b.data = _parse_data_extenso(linhas)

    # Cliente: nome após "declara haver recebido" começa o corpo; pegamos o
    # primeiro "NEO FORMAS..." que aparecer.
    for ln in linhas:
        u = ln.upper()
        if "NEO FORMAS" in u and "CONCRETO" in u:
            b.cliente = "NEO FORMAS PARA CONCRETO"
            break
        if "NEO FORMAS" in u and not b.cliente:
            b.cliente = "NEO FORMAS"

    # Totais. Comparamos sem espaços porque o OCR às vezes parte a palavra
    # (ex.: "Dese mbolso").
    norm_linhas = [_norm(l) for l in linhas]
    norm_ns = [nl.replace(" ", "") for nl in norm_linhas]
    usados: set[int] = set()
    for rotulo, attr in _ROTULOS_TOTAIS:
        alvo = rotulo.replace(" ", "")
        for i, nl in enumerate(norm_ns):
            if i in usados:
                continue
            if alvo in nl:
                val = _proximo_valor(linhas, i)
                if val is not None:
                    setattr(b, attr, val)
                    usados.add(i)
                break

    # Deságio dos totais: linha "(-) Desagio" (após "Total do bordero").
    for i, nl in enumerate(norm_linhas):
        if "desagio" in nl and ("-" in linhas[i] or i > _indice(norm_linhas, "total do bordero")):
            val = _proximo_valor(linhas, i)
            if val is not None:
                b.desagio = val
                break

    # Títulos: região entre "valor face" (cabeçalho) e "total" / "quantidade".
    ini = _indice(norm_linhas, "valor face")
    fim = _indice(norm_linhas, "total", a_partir=ini + 1 if ini >= 0 else 0)
    if ini >= 0 and fim > ini:
        b.titulos = _parse_titulos(linhas[ini + 1:fim])

    return b


def _indice(norm_linhas: list[str], alvo: str, a_partir: int = 0) -> int:
    for i in range(a_partir, len(norm_linhas)):
        if alvo in norm_linhas[i]:
            return i
    return -1


# --------------------------------------------------------------------------- #
# OCR (lento — isolado para os testes poderem pular)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR  # import tardio (pesado)

    return RapidOCR()


def ocr_paginas(pdf_path: str, dpi: int = 300) -> list[str]:
    """Renderiza cada página do PDF e roda OCR. Retorna as linhas de texto."""
    import fitz  # pymupdf

    ocr = _ocr_engine()
    linhas: list[str] = []
    zoom = dpi / 72
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            png = pix.tobytes("png")
            resultado, _ = ocr(png)
            if resultado:
                for _box, texto, _conf in resultado:
                    linhas.append(str(texto))
    return linhas


def parse_bordero(pdf_path: str, dpi: int = 300) -> Bordero:
    """Lê um borderô em PDF (OCR + parsing) e confere a aritmética interna."""
    from .calculos import conferir_bordero

    linhas = ocr_paginas(pdf_path, dpi=dpi)
    b = parse_linhas(linhas, origem=pdf_path)
    b.avisos.extend(conferir_bordero(b))
    return b
