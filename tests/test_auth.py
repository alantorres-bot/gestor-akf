"""Testes da lógica de papéis (sem depender do Streamlit nem do banco)."""

from __future__ import annotations

from gestor_akf import auth


def test_bootstrap_vira_admin_mesmo_sem_banco():
    assert auth.decidir_papel("chefe@neoformas.com.br", "chefe@neoformas.com.br", None) == "admin"


def test_bootstrap_ignora_caixa_e_espacos():
    assert auth.decidir_papel("  Chefe@Neoformas.com.br ", "chefe@neoformas.com.br", None) == "admin"


def test_usa_papel_do_banco_quando_nao_e_bootstrap():
    assert auth.decidir_papel("joao@x.com", "chefe@x.com", "financeiro") == "financeiro"


def test_sem_papel_no_banco_e_sem_bootstrap_fica_sem_acesso():
    assert auth.decidir_papel("estranho@x.com", "chefe@x.com", None) is None


def test_pode_escrever():
    assert auth.pode_escrever("admin") is True
    assert auth.pode_escrever("financeiro") is True
    assert auth.pode_escrever("leitura") is False
    assert auth.pode_escrever(None) is False


def test_is_admin():
    assert auth.is_admin("admin") is True
    assert auth.is_admin("financeiro") is False


def test_db_nao_configurado_sem_segredos(monkeypatch):
    from gestor_akf import db

    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert db.configurado() is False


def test_db_configurado_com_env(monkeypatch):
    from gestor_akf import db

    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "chave")
    assert db.configurado() is True
