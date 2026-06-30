"""Acesso ao banco compartilhado (Supabase / Postgres).

O app roda no servidor e usa a **service key** do Supabase (em st.secrets / env),
nunca exposta ao navegador. A autorização por papel é feita na camada de auth.

A biblioteca ``supabase`` é importada **sob demanda** — assim o resto do app e os
testes funcionam mesmo sem ela instalada / sem o banco configurado.

Config (ordem): variável de ambiente, depois ``st.secrets`` (quando no Streamlit):
  - ``SUPABASE_URL``
  - ``SUPABASE_SERVICE_KEY``  (preferida; cai em ``SUPABASE_KEY``)
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional


class DBError(RuntimeError):
    """Falha de configuração ou acesso ao banco."""


def _segredo(nome: str, padrao: Optional[str] = None) -> Optional[str]:
    """Lê um segredo de env var ou de st.secrets (se rodando no Streamlit)."""
    v = os.environ.get(nome)
    if v:
        return v
    try:
        import streamlit as st  # import tardio: pode não existir em scripts/testes

        if nome in st.secrets:
            return str(st.secrets[nome])
    except Exception:
        pass
    return padrao


def configurado() -> bool:
    """True se há URL + chave do Supabase — i.e., estamos em modo multiusuário."""
    return bool(_segredo("SUPABASE_URL") and
                (_segredo("SUPABASE_SERVICE_KEY") or _segredo("SUPABASE_KEY")))


@lru_cache(maxsize=1)
def cliente():
    """Cliente Supabase (cacheado). Levanta DBError se não configurado."""
    url = _segredo("SUPABASE_URL")
    key = _segredo("SUPABASE_SERVICE_KEY") or _segredo("SUPABASE_KEY")
    if not url or not key:
        raise DBError(
            "Banco não configurado. Defina SUPABASE_URL e SUPABASE_SERVICE_KEY "
            "(em st.secrets, no deploy, ou em variáveis de ambiente)."
        )
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover - depende de instalação
        raise DBError(
            "Biblioteca 'supabase' não instalada. Rode: pip install -r requirements.txt"
        ) from exc
    return create_client(url, key)


# --------------------------------------------------------------------------- #
# Usuários e papéis
# --------------------------------------------------------------------------- #
def listar_usuarios() -> list[dict]:
    r = cliente().table("usuarios").select("*").order("email").execute()
    return r.data or []


def get_papel(email: str) -> Optional[str]:
    """Papel do usuário ('admin'/'financeiro'/'leitura') ou None se não cadastrado."""
    if not email:
        return None
    r = (
        cliente()
        .table("usuarios")
        .select("papel")
        .eq("email", email.lower().strip())
        .limit(1)
        .execute()
    )
    return r.data[0]["papel"] if r.data else None


def upsert_usuario(email: str, papel: str, nome: Optional[str] = None) -> None:
    registro = {"email": email.lower().strip(), "papel": papel}
    if nome is not None:
        registro["nome"] = nome
    cliente().table("usuarios").upsert(registro).execute()


def remover_usuario(email: str) -> None:
    cliente().table("usuarios").delete().eq("email", email.lower().strip()).execute()
