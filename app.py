"""Gestor de Antecipações AKF — Neo Formas (interface).

Roda local no navegador. Para iniciar:
    .venv\\Scripts\\activate
    streamlit run app.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from gestor_akf import auth, db
from gestor_akf.calculos import conferir_bordero, custo_real_operacao, diferenca_por_fora
from gestor_akf.carteira import carregar_carteira, resumir
from gestor_akf.conciliacao import Pedido, conciliar
from gestor_akf.instrucao import gerar_instrucao
from gestor_akf.numeros import formatar_pct, formatar_valor_br
from gestor_akf.parametros import carregar_parametros
from gestor_akf.passivo import importar_planilha_por_fora
from gestor_akf.selecao import selecionar_titulos

st.set_page_config(page_title="Gestor AKF · Neo Formas", page_icon="🔷", layout="wide")

Z = Decimal("0.00")
LOGO = os.path.join(os.path.dirname(__file__), "assets", "logo-neoformas.jpg")
AZUL = "#3E5A82"  # azul-aço da marca Neo Formas


def _estilo():
    """Injeta o visual da marca (cartões, cabeçalhos, sidebar)."""
    st.markdown(
        """
        <style>
        h1, h2, h3 { color: #2A3F5F; font-weight: 700; }
        /* Métricas viram cartões */
        div[data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #E2E8F2;
            border-radius: 12px;
            padding: 14px 18px;
            box-shadow: 0 1px 3px rgba(30,42,58,.06);
        }
        div[data-testid="stMetricLabel"] p { color: #5B6B82; font-weight: 600; }
        div[data-testid="stMetricValue"] { color: #2A3F5F; }
        /* Sidebar */
        section[data-testid="stSidebar"] { border-right: 1px solid #E2E8F2; }
        section[data-testid="stSidebar"] img { border-radius: 8px; }
        /* Botões arredondados */
        .stButton>button, .stDownloadButton>button, .stFormSubmitButton>button {
            border-radius: 8px; font-weight: 600;
        }
        /* Tabelas e expanders mais suaves */
        div[data-testid="stExpander"] { border-radius: 10px; }
        /* Faixa de topo fina na cor da marca */
        .block-container { padding-top: 2.2rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def card_kpi(titulo: str, valor: str, sub: str = "", cor: str = AZUL):
    """Cartão de indicador para o painel inicial."""
    st.markdown(
        f"""
        <div style="background:#fff;border:1px solid #E2E8F2;border-left:5px solid {cor};
                    border-radius:12px;padding:16px 18px;box-shadow:0 1px 3px rgba(30,42,58,.06);">
          <div style="color:#5B6B82;font-size:.85rem;font-weight:600;">{titulo}</div>
          <div style="color:#2A3F5F;font-size:1.55rem;font-weight:700;line-height:1.3;">{valor}</div>
          <div style="color:#8492A6;font-size:.8rem;">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def rs(v) -> str:
    return "R$ " + formatar_valor_br(v)


@st.cache_data(show_spinner=False)
def _carteira_cache(caminho: str, mtime: float):
    ts = carregar_carteira(caminho)
    return ts


@st.cache_data(show_spinner="Lendo borderô (OCR)... pode levar ~20s por página")
def _bordero_cache(caminho: str, mtime: float):
    from gestor_akf.bordero_ocr import parse_bordero
    b = parse_bordero(caminho)
    # serializa o essencial para o cache/sessão
    return {
        "numero": b.numero, "conexao": b.conexao, "cliente": b.cliente,
        "carteira": b.rotulo_carteira, "data": b.data,
        "total_bordero": b.total_bordero, "desagio": b.desagio,
        "valor_liquido": b.valor_liquido, "recompras": b.recompras,
        "creditos": b.creditos, "debitos": b.debitos, "abatimento": b.abatimento,
        "desembolso": b.desembolso, "avisos": b.avisos,
        "titulos": [
            {"documento": t.documento, "sacado": t.sacado, "cnpj": t.sacado_cnpj,
             "vencimento": t.vencimento, "desagio": t.desagio, "valor_face": t.valor_face}
            for t in b.titulos
        ],
        "_obj": b,
        "origem": caminho,
    }


def _params():
    if "params" not in st.session_state:
        st.session_state.params = carregar_parametros()
    return st.session_state.params


def _salvar_temp(uploaded) -> str:
    d = os.path.join(tempfile.gettempdir(), "gestor_akf_uploads")
    os.makedirs(d, exist_ok=True)
    caminho = os.path.join(d, uploaded.name)
    with open(caminho, "wb") as f:
        f.write(uploaded.getbuffer())
    return caminho


# --------------------------------------------------------------------------- #
# Navegação
# --------------------------------------------------------------------------- #
_estilo()
try:
    st.logo(LOGO, size="large")
except Exception:
    pass  # versões antigas do Streamlit sem st.logo

# Login e papéis (modo local quando o banco não está configurado).
email_usuario, papel_usuario = auth.exigir_login()
pode_escrever = auth.pode_escrever(papel_usuario)

st.sidebar.markdown("### Gestor de Antecipações")
st.sidebar.caption("Neo Formas × AKF Securitizadora")
st.sidebar.divider()

PAGINAS = [
    "🏠 Início",
    "📥 Carteira",
    "🎯 Seleção de títulos",
    "✉️ Instrução (e-mail)",
    "📄 Borderôs (PDF)",
    "🔎 Conciliação",
    "📊 Passivo \"por fora\"",
    "💰 Custo efetivo",
]
if auth.is_admin(papel_usuario):
    PAGINAS.append("👥 Usuários")
pagina = st.sidebar.radio("Navegação", PAGINAS, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption(f"👤 {email_usuario} · **{papel_usuario}**")
if not db.configurado():
    st.sidebar.caption("⚙️ Modo local (banco não configurado).")
else:
    if not pode_escrever:
        st.sidebar.caption("🔒 Perfil de leitura: você consulta, mas não altera dados.")
    if st.sidebar.button("Sair", use_container_width=True):
        st.logout()


# --------------------------------------------------------------------------- #
# Página: Início
# --------------------------------------------------------------------------- #
if pagina == "🏠 Início":
    cab1, cab2 = st.columns([1, 4])
    with cab1:
        st.image(LOGO, width=150)
    with cab2:
        st.title("Gestor de Antecipações AKF")
        nome = email_usuario.split("@")[0].split(".")[0].capitalize()
        st.caption(f"Bem-vindo, {nome}. Operação Neo Formas × AKF Securitizadora.")

    # --- Painel da carteira ---
    st.subheader("Visão da carteira")
    titulos = st.session_state.get("carteira")
    if titulos:
        r = resumir(titulos)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            card_kpi("Carteira total", rs(r.total_valor), f"{r.total_titulos} títulos")
        with c2:
            card_kpi("Disponível p/ antecipar", rs(r.disponiveis_valor),
                     f"{r.disponiveis_qtd} títulos", "#2E7D5B")
        with c3:
            card_kpi("Já antecipado (AKF)", rs(r.antecipados_valor),
                     f"{r.antecipados_qtd} títulos", "#B7791F")
        with c4:
            card_kpi("Vencidos", rs(r.vencidos_valor),
                     f"{r.vencidos_qtd} títulos", "#C0392B")
        st.caption(f"Origem: {st.session_state.get('carteira_origem', '—')}")
    else:
        st.info("Carregue a carteira na página **📥 Carteira** (direto da API do "
                "Consistem ou via CSV) para ver o painel.", icon="📥")

    st.divider()
    cesq, cdir = st.columns([3, 2])
    with cesq:
        st.subheader("Como usar, no dia a dia")
        st.markdown(
            """
            1. **📥 Carteira** — títulos em aberto, direto da API do Consistem.
            2. **🎯 Seleção** — diga quanto de caixa precisa; o app sugere os títulos ao menor custo.
            3. **✉️ Instrução** — gere o e-mail para a AKF.
            4. **📄 Borderôs** — depois que a AKF responder, leia os PDFs recebidos (OCR).
            5. **🔎 Conciliação** — confira se o que foi operado bate com o pedido.
            6. **📊 Passivo "por fora"** — acompanhe o saldo da diferença.
            7. **💰 Custo efetivo** — veja o custo real (oficial + por fora).
            """
        )
    with cdir:
        st.subheader("Parâmetros")
        p = _params()
        m1, m2 = st.columns(2)
        m1.metric("Multa de recompra", formatar_pct(p.multa_recompra, 0))
        m2.metric("Taxa de referência", formatar_pct(p.taxa_referencia_am) + " a.m.")
        st.caption("Sem teto de desconto: o limite da AKF é volátil, então não barra "
                   "a seleção. Ajustes finos ficam em `config/parametros.json`.")


# --------------------------------------------------------------------------- #
# Página: Carteira
# --------------------------------------------------------------------------- #
elif pagina == "📥 Carteira":
    st.title("📥 Carteira de recebíveis")
    st.caption("Títulos em aberto — direto da API do Consistem ou via export CSV.")

    # --- Opção 1: buscar ao vivo na API do Consistem ---
    from gestor_akf import consistem_api

    cbtn, cinfo = st.columns([1, 3])
    with cbtn:
        buscar = st.button("🔄 Buscar da API do Consistem", type="primary",
                           use_container_width=True)
    with cinfo:
        if consistem_api.token_configurado():
            st.caption("Token configurado. A busca traz os títulos em aberto direto do ERP.")
        else:
            st.caption("⚠️ Token não configurado (defina CONSISTEM_API_KEY ou "
                       "`config/consistem.secret`). Use o CSV abaixo enquanto isso.")

    if buscar:
        try:
            with st.spinner("Buscando títulos no Consistem..."):
                titulos_api = consistem_api.buscar_titulos_abertos()
            st.session_state.carteira = titulos_api
            st.session_state.carteira_origem = "API do Consistem"
            st.success(f"Carteira atualizada da API: {len(titulos_api)} títulos.")
        except consistem_api.ConsistemError as e:
            st.error(f"Não consegui buscar da API: {e}")
            st.info("Você pode usar o export CSV abaixo como alternativa.", icon="📄")

    st.divider()

    # --- Opção 2: export CSV do Consistem (alternativa / fallback) ---
    st.caption("Alternativa: export do Consistem em CSV.")
    col1, col2 = st.columns(2)
    with col1:
        up = st.file_uploader("Enviar CSV da carteira", type=["csv"], key="up_cart")
    with col2:
        caminho_txt = st.text_input(
            "...ou caminho do arquivo no disco",
            value=st.session_state.get("caminho_carteira", ""),
        )

    caminho = None
    if up is not None:
        caminho = _salvar_temp(up)
    elif caminho_txt and os.path.exists(caminho_txt):
        caminho = caminho_txt

    if caminho:
        st.session_state.caminho_carteira = caminho
        try:
            titulos = _carteira_cache(caminho, os.path.getmtime(caminho))
        except Exception as e:
            st.error(f"Não consegui ler o arquivo: {e}")
            st.stop()
        st.session_state.carteira = titulos
        st.session_state.carteira_origem = f"CSV ({os.path.basename(caminho)})"

    # --- Exibição (carteira de qualquer origem) ---
    titulos = st.session_state.get("carteira")
    if titulos:
        st.divider()
        st.caption(f"Origem: {st.session_state.get('carteira_origem', '—')}")
        r = resumir(titulos)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de títulos", r.total_titulos, rs(r.total_valor))
        c2.metric("Disponíveis p/ antecipar", r.disponiveis_qtd, rs(r.disponiveis_valor))
        c3.metric("Já antecipados (AKF)", r.antecipados_qtd, rs(r.antecipados_valor))
        c4.metric("Vencidos", r.vencidos_qtd, rs(r.vencidos_valor))

        st.session_state.exposicao_atual = r.antecipados_valor

        filtro = st.radio("Mostrar",
                          ["Disponíveis", "Antecipados (AKF)", "Vencidos", "Todos"],
                          horizontal=True)
        if filtro == "Disponíveis":
            mostra = [t for t in titulos if t.disponivel]
        elif filtro == "Antecipados (AKF)":
            mostra = [t for t in titulos if t.antecipado]
        elif filtro == "Vencidos":
            mostra = [t for t in titulos if t.vencido]
        else:
            mostra = titulos

        df = pd.DataFrame([{
            "Título": t.titulo, "Cliente": t.cliente_nome,
            "Vencimento": t.vencimento, "Valor": float(t.valor),
            "Portador": t.portador_nome, "Cobrança": t.tipo_cobranca,
            "Dias atraso": t.dias_atraso,
        } for t in mostra])
        st.dataframe(df, width="stretch", hide_index=True,
                     column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")})
    else:
        st.info("Clique em **Buscar da API do Consistem** ou envie um CSV para começar.",
                icon="📄")


# --------------------------------------------------------------------------- #
# Página: Seleção
# --------------------------------------------------------------------------- #
elif pagina == "🎯 Seleção de títulos":
    st.title("🎯 Seleção de títulos a antecipar")
    if "carteira" not in st.session_state:
        st.warning("Carregue a carteira primeiro (página 📥 Carteira).", icon="⚠️")
        st.stop()

    p = _params()
    c1, c2 = st.columns(2)
    with c1:
        alvo = st.number_input("Caixa necessário (R$)", min_value=0.0,
                               value=200000.0, step=10000.0, format="%.2f")
    with c2:
        data_ref = st.date_input("Data de referência", value=date.today())
    st.caption("Apenas títulos **a vencer** entram na seleção — vencidos não são antecipáveis.")

    exposicao = st.session_state.get("exposicao_atual", Z)
    if st.button("Sugerir seleção", type="primary"):
        sel = selecionar_titulos(
            st.session_state.carteira, Decimal(str(alvo)), data_ref, p,
            exposicao_atual=Decimal(str(exposicao)),
        )
        st.session_state.selecao = sel

    if "selecao" in st.session_state:
        sel = st.session_state.selecao
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Selecionado", rs(sel.valor_total), f"{sel.qtd} título(s)")
        c2.metric("Atingiu o alvo?", "Sim ✅" if sel.atingiu_alvo else "Não ⚠️")
        c3.metric("Deságio estimado", rs(sel.custo_estimado),
                  formatar_pct(sel.taxa_estimada_am) + " a.m." if sel.taxa_estimada_am else "")
        c4.metric("Desembolso estimado", rs(sel.desembolso_estimado))

        for a in sel.avisos:
            st.warning(a, icon="⚠️")

        df = pd.DataFrame([{
            "Título": i.titulo.titulo, "Cliente": i.titulo.cliente_nome,
            "Vencimento": i.titulo.vencimento, "Dias": i.dias,
            "Valor": float(i.titulo.valor), "Sem boleto?": "Sim" if i.sem_boleto else "",
            "Obs.": i.observacao,
        } for i in sel.itens])
        st.dataframe(df, width="stretch", hide_index=True,
                     column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")})



# --------------------------------------------------------------------------- #
# Página: Instrução
# --------------------------------------------------------------------------- #
elif pagina == "✉️ Instrução (e-mail)":
    st.title("✉️ Instrução para a AKF")
    if "selecao" not in st.session_state:
        st.warning("Faça uma seleção primeiro (página 🎯 Seleção).", icon="⚠️")
        st.stop()

    p = _params()
    data_op = st.date_input("Data da operação", value=date.today())
    instr = gerar_instrucao(st.session_state.selecao, p, data_operacao=data_op)

    st.text_input("Para", value="; ".join(instr.para))
    st.text_input("Cc", value="; ".join(instr.cc))
    st.text_input("Assunto", value=instr.assunto)
    st.text_area("Corpo do e-mail", value=instr.corpo, height=420)
    st.caption("Copie o texto acima para o seu e-mail. (Nada é enviado pelo app.)")


# --------------------------------------------------------------------------- #
# Página: Borderôs
# --------------------------------------------------------------------------- #
elif pagina == "📄 Borderôs (PDF)":
    st.title("📄 Leitura de borderôs (PDF → dados)")
    st.caption("Os borderôs são imagens escaneadas; o app usa OCR local. "
               "Cada valor é conferido pela aritmética do próprio borderô.")

    ups = st.file_uploader("Enviar PDFs de borderô", type=["pdf"],
                           accept_multiple_files=True, key="up_bord")
    pasta = st.text_input("...ou caminho de uma pasta com PDFs")

    caminhos: list[str] = []
    if ups:
        caminhos = [_salvar_temp(u) for u in ups]
    elif pasta and os.path.isdir(pasta):
        caminhos = [os.path.join(pasta, f) for f in sorted(os.listdir(pasta))
                    if f.lower().endswith(".pdf")]

    if caminhos and st.button("Ler borderôs", type="primary"):
        lidos = []
        prog = st.progress(0.0)
        for k, c in enumerate(caminhos):
            try:
                lidos.append(_bordero_cache(c, os.path.getmtime(c)))
            except Exception as e:
                st.error(f"Erro em {os.path.basename(c)}: {e}")
            prog.progress((k + 1) / len(caminhos))
        st.session_state.borderos = lidos

    for b in st.session_state.get("borderos", []):
        carteira_tag = "🟢 por dentro" if b["carteira"] == "por dentro" else "🟠 por fora"
        with st.expander(f"Borderô {b['numero'] or '?'} — {carteira_tag} — "
                         f"{os.path.basename(b['origem'])}", expanded=False):
            if b["avisos"]:
                for a in b["avisos"]:
                    st.error("⚠ " + a)
            else:
                st.success("Aritmética confere ✅")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total", rs(b["total_bordero"]))
            c1.metric("Deságio", rs(b["desagio"]))
            c2.metric("Líquido", rs(b["valor_liquido"]))
            c2.metric("Recompras", rs(b["recompras"]))
            c3.metric("Débitos", rs(b["debitos"]))
            c3.metric("Desembolso", rs(b["desembolso"]))
            if b["titulos"]:
                df = pd.DataFrame([{
                    "Documento": t["documento"], "Sacado": t["sacado"],
                    "Vencimento": t["vencimento"], "Deságio": float(t["desagio"]),
                    "Valor face": float(t["valor_face"]),
                } for t in b["titulos"]])
                st.dataframe(df, width="stretch", hide_index=True)

    if st.session_state.get("borderos"):
        # se houver um par por dentro/por fora, mostra a diferença
        dentro = next((x for x in st.session_state.borderos if x["carteira"] == "por dentro"), None)
        fora = next((x for x in st.session_state.borderos if x["carteira"] == "por fora"), None)
        if dentro and fora:
            dif = diferenca_por_fora(dentro["_obj"], fora["_obj"])
            st.info(f"**Diferença \"por fora\"** entre borderô {dif.bordero_por_dentro} "
                    f"e {dif.bordero_por_fora}: **{rs(dif.diferenca)}**", icon="💡")


# --------------------------------------------------------------------------- #
# Página: Conciliação
# --------------------------------------------------------------------------- #
elif pagina == "🔎 Conciliação":
    st.title("🔎 Conciliação — pedido × borderô")
    if not st.session_state.get("borderos"):
        st.warning("Leia os borderôs primeiro (página 📄 Borderôs).", icon="⚠️")
        st.stop()

    st.markdown("**Pedidos** (o que foi instruído). Use a seleção feita no app "
                "ou cole a lista manualmente.")
    origem = st.radio("Origem dos pedidos", ["Usar seleção do app", "Digitar manualmente"],
                      horizontal=True)
    pedidos: list[Pedido] = []
    if origem == "Usar seleção do app" and "selecao" in st.session_state:
        for i in st.session_state.selecao.itens:
            pedidos.append(Pedido(i.titulo.titulo, i.titulo.valor,
                                  i.titulo.vencimento, i.titulo.cliente_nome))
    else:
        txt = st.text_area("Um título por linha: documento;valor (ex.: 1261/2;440000,00)",
                           height=150)
        from gestor_akf.numeros import parse_valor_br
        for ln in txt.splitlines():
            if ";" in ln:
                doc, _, val = ln.partition(";")
                v = parse_valor_br(val)
                if doc.strip() and v is not None:
                    pedidos.append(Pedido(doc.strip(), v))

    borderos = [x["_obj"] for x in st.session_state.borderos]
    if pedidos and st.button("Conciliar", type="primary"):
        r = conciliar(pedidos, borderos, taxa_multa=_params().multa_recompra)
        if r.ok:
            st.success(f"Tudo conferido — {len(r.casados)} título(s) bateram. ✅")
        else:
            st.warning(f"{len(r.divergencias)} divergência(s) encontrada(s).")
        rotulos = {
            "nao_operada": "❌ Pedidas e não operadas",
            "valor": "💲 Divergência de valor",
            "vencimento": "📅 Divergência de vencimento",
            "duplicidade": "👯 Duplicidade",
            "so_no_bordero": "❓ Operado sem pedido",
            "recompra": "↩️ Recompra a conferir",
        }
        for tipo, rot in rotulos.items():
            ds = r.por_tipo(tipo)
            if ds:
                st.subheader(rot)
                for d in ds:
                    st.write(f"• **{d.documento}** — {d.detalhe}" if d.documento else f"• {d.detalhe}")
        if r.diferenca_por_fora:
            st.info(f"Diferença \"por fora\": **{rs(r.diferenca_por_fora.diferenca)}**", icon="💡")


# --------------------------------------------------------------------------- #
# Página: Passivo "por fora"
# --------------------------------------------------------------------------- #
elif pagina == "📊 Passivo \"por fora\"":
    st.title("📊 Passivo \"por fora\" (diferença entre borderôs)")
    st.caption("Tratado pela substância econômica = custo financeiro. "
               "Estornos/devoluções ficam separados dos pagamentos.")

    up = st.file_uploader("Enviar a planilha de controle (Excel)", type=["xlsx"], key="up_plan")
    cam = st.text_input("...ou caminho da planilha no disco",
                        value=st.session_state.get("caminho_planilha", ""))
    caminho = _salvar_temp(up) if up else (cam if cam and os.path.exists(cam) else None)

    if caminho:
        st.session_state.caminho_planilha = caminho
        try:
            r = importar_planilha_por_fora(caminho)
        except Exception as e:
            st.error(f"Erro ao ler a planilha: {e}")
            st.stop()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Custo gerado (total)", rs(r.total_gerado))
        c2.metric("Pago (abatido)", rs(r.total_pago))
        c3.metric("Estornos/devoluções", rs(r.total_estornado))
        c4.metric("Saldo devedor", rs(r.saldo))

        df = pd.DataFrame([{
            "Data": l.data, "Borderô (dentro)": l.base01, "Borderô (fora)": l.base02,
            "Custo": float(l.valor), "Pagamento": float(l.pagamento),
            "Estorno": float(l.estorno), "Observação": l.observacao,
        } for l in r.lancamentos])
        st.dataframe(df, width="stretch", hide_index=True,
                     column_config={
                         "Custo": st.column_config.NumberColumn(format="R$ %.2f"),
                         "Pagamento": st.column_config.NumberColumn(format="R$ %.2f"),
                         "Estorno": st.column_config.NumberColumn(format="R$ %.2f"),
                     })
    else:
        st.info("Envie a planilha ou informe o caminho.", icon="📄")


# --------------------------------------------------------------------------- #
# Página: Custo efetivo
# --------------------------------------------------------------------------- #
elif pagina == "💰 Custo efetivo":
    st.title("💰 Custo efetivo real (oficial + por fora)")
    st.markdown("Calcule o custo verdadeiro de uma operação somando o deságio "
                "oficial (borderô por dentro) com a diferença \"por fora\".")

    bs = st.session_state.get("borderos", [])
    dentro = next((x for x in bs if x["carteira"] == "por dentro"), None)
    fora = next((x for x in bs if x["carteira"] == "por fora"), None)

    if dentro and fora:
        st.success(f"Usando os borderôs lidos: {dentro['numero']} (dentro) × "
                   f"{fora['numero']} (fora).")
        dias = st.number_input("Prazo médio (dias até o vencimento)", min_value=1, value=50)
        cr = custo_real_operacao(dentro["_obj"], fora["_obj"], int(dias))
        c1, c2, c3 = st.columns(3)
        c1.metric("Custo oficial (deságio)", rs(cr.custo_oficial),
                  formatar_pct(cr.taxa_oficial_am) + " a.m.")
        c2.metric("Custo por fora", rs(cr.custo_por_fora))
        c3.metric("Custo TOTAL real", rs(cr.custo_total),
                  formatar_pct(cr.taxa_real_am) + " a.m.")
        st.warning(
            f"O custo **real** (~{formatar_pct(cr.taxa_real_am)} a.m.) é maior que o "
            f"aparente (~{formatar_pct(cr.taxa_oficial_am)} a.m.). Compare com suas "
            f"linhas bancárias antes de decidir.", icon="💡")
    else:
        st.info("Leia um par de borderôs (por dentro + por fora) na página 📄 Borderôs "
                "para calcular o custo real automaticamente.", icon="📄")


# --------------------------------------------------------------------------- #
# Página: Usuários (somente admin)
# --------------------------------------------------------------------------- #
elif pagina == "👥 Usuários":
    st.title("👥 Usuários e permissões")
    if not db.configurado():
        st.info("A gestão de usuários só funciona com o banco configurado "
                "(modo multiusuário). Em modo local você já é admin.", icon="⚙️")
        st.stop()

    st.caption("Quem pode entrar e o que cada um pode fazer.")
    st.markdown(
        "- **admin** — tudo, inclusive gerenciar usuários.\n"
        "- **financeiro** — alimenta dados (borderôs, passivo, seleção) e consulta.\n"
        "- **leitura** — só consulta relatórios."
    )

    try:
        usuarios = db.listar_usuarios()
    except db.DBError as e:
        st.error(f"Não consegui ler os usuários: {e}")
        st.stop()

    if usuarios:
        st.dataframe(
            pd.DataFrame([{"E-mail": u["email"], "Nome": u.get("nome") or "",
                           "Papel": u["papel"]} for u in usuarios]),
            width="stretch", hide_index=True,
        )
    else:
        st.info("Nenhum usuário cadastrado ainda.", icon="👤")

    st.divider()
    st.subheader("Adicionar ou atualizar")
    with st.form("form_usuario", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        novo_email = c1.text_input("E-mail (conta Google)")
        novo_nome = c2.text_input("Nome (opcional)")
        novo_papel = c3.selectbox("Papel", auth.PAPEIS, index=1)
        if st.form_submit_button("Salvar", type="primary"):
            if not novo_email.strip():
                st.warning("Informe o e-mail.")
            else:
                db.upsert_usuario(novo_email, novo_papel, novo_nome or None)
                st.success(f"{novo_email} salvo como {novo_papel}.")
                st.rerun()

    st.subheader("Remover acesso")
    removiveis = [u["email"] for u in usuarios if u["email"] != email_usuario]
    if removiveis:
        alvo = st.selectbox("Usuário", removiveis, key="rm_user")
        if st.button("Remover", type="secondary"):
            db.remover_usuario(alvo)
            st.success(f"{alvo} removido.")
            st.rerun()
    else:
        st.caption("Nada a remover (você não pode remover a si mesmo).")
