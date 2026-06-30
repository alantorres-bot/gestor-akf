"""Login e papéis do app multiusuário.

Como funciona o login:
  - **Produção** (Streamlit Community Cloud, app privado): o usuário entra com a
    conta Google e o e-mail fica disponível em ``st.user.email``. O papel
    ('admin'/'financeiro'/'leitura') vem da tabela ``usuarios`` no banco.
  - **Desenvolvimento local** (sem Supabase configurado): roda em "modo local" como
    admin, para não travar quem está testando na própria máquina.

Um e-mail "bootstrap" (segredo ``BOOTSTRAP_ADMIN_EMAIL``) é sempre admin, mesmo sem
estar na tabela — assim o primeiro administrador consegue entrar e cadastrar os demais.
"""

from __future__ import annotations

from typing import Optional

from . import db

PAPEIS = ("admin", "financeiro", "leitura")
EMAIL_LOCAL = "local@dev"


def decidir_papel(email: Optional[str], boot_email: Optional[str],
                  papel_banco: Optional[str]) -> Optional[str]:
    """Regra pura: bootstrap vira admin; senão usa o papel do banco."""
    e = (email or "").lower().strip()
    boot = (boot_email or "").lower().strip()
    if e and boot and e == boot:
        return "admin"
    return papel_banco


def pode_escrever(papel: Optional[str]) -> bool:
    """admin e financeiro alimentam dados; leitura só consulta."""
    return papel in ("admin", "financeiro")


def is_admin(papel: Optional[str]) -> bool:
    return papel == "admin"


# --------------------------------------------------------------------------- #
# Integração com o Streamlit (não usada nos testes)
# --------------------------------------------------------------------------- #
def _email_oidc() -> Optional[str]:  # pragma: no cover - depende do Streamlit
    """E-mail do usuário autenticado via OIDC (st.login). None se não logado."""
    import streamlit as st

    try:
        if not bool(st.user.is_logged_in):
            return None
        email = getattr(st.user, "email", None)
    except Exception:
        # fallback p/ testar deploy manualmente sem OIDC
        email = db._segredo("DEV_EMAIL")
    return email.lower().strip() if email else None


def exigir_login():  # pragma: no cover - depende do Streamlit
    """Garante usuário autorizado. Retorna (email, papel) ou interrompe a página.

    - Sem Supabase configurado: modo local (admin) para desenvolvimento.
    - Em produção: login com Google via OIDC (st.login), papel pela tabela usuarios.
    """
    import streamlit as st

    if not db.configurado():
        return EMAIL_LOCAL, "admin"

    email = _email_oidc()
    if not email:
        st.title("💸 Gestor de Antecipações AKF")
        st.info("Entre com sua conta **Google da Neo Formas** para acessar o sistema.")
        if st.button("🔐 Entrar com Google", type="primary"):
            st.login()  # usa a configuração [auth] dos secrets
        st.stop()

    boot = db._segredo("BOOTSTRAP_ADMIN_EMAIL")
    # O admin bootstrap entra sempre, sem depender do banco (mesmo antes do schema).
    if decidir_papel(email, boot, None) == "admin":
        return email, "admin"

    try:
        papel = db.get_papel(email)
    except db.DBError as e:
        st.error(f"Não consegui falar com o banco: {e}")
        st.stop()

    if not papel:
        st.warning(
            f"Você entrou como **{email}**, mas esse e-mail ainda não tem acesso "
            "liberado. Peça a um administrador para cadastrá-lo no sistema."
        )
        if st.button("Sair"):
            st.logout()
        st.stop()

    return email, papel
