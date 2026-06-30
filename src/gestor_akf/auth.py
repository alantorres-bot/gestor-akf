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
def _email_logado() -> Optional[str]:  # pragma: no cover - depende do Streamlit
    import streamlit as st

    email = None
    try:
        email = getattr(st.user, "email", None)
    except Exception:
        email = None
    if not email:
        email = db._segredo("DEV_EMAIL")  # fallback p/ testar deploy manualmente
    return email.lower().strip() if email else None


def exigir_login():  # pragma: no cover - depende do Streamlit
    """Garante usuário autorizado. Retorna (email, papel) ou interrompe a página.

    Sem Supabase configurado, opera em modo local (admin) para desenvolvimento.
    """
    import streamlit as st

    if not db.configurado():
        return EMAIL_LOCAL, "admin"

    email = _email_logado()
    if not email:
        st.error("Faça login para acessar o sistema.")
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
        st.error(
            f"Sem acesso para **{email}**. "
            "Peça a um administrador para liberar seu e-mail no sistema."
        )
        st.stop()

    return email, papel
