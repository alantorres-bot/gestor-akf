-- Gestor de Antecipações AKF — schema do banco (Supabase / Postgres)
-- Rode este script UMA VEZ no projeto Supabase novo: Dashboard → SQL Editor → cole → Run.
--
-- Modelo de acesso: o app Streamlit roda no servidor e usa a SERVICE KEY do Supabase
-- (guardada em st.secrets, nunca no navegador). A autorização (quem pode alimentar vs.
-- só consultar) é feita NO APP pelos papéis da tabela `usuarios`. Por isso não usamos
-- RLS aqui — o acesso ao banco já é server-side e a hospedagem é privada (whitelist).

-- ----------------------------------------------------------------------------
-- Usuários e papéis
-- ----------------------------------------------------------------------------
create table if not exists usuarios (
    email      text primary key,
    nome       text,
    papel      text not null default 'leitura'
               check (papel in ('admin', 'financeiro', 'leitura')),
    criado_em  timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- Borderôs lidos por OCR (cabeçalho + títulos)
-- ----------------------------------------------------------------------------
create table if not exists borderos (
    id             bigint generated always as identity primary key,
    numero         text not null,
    conexao        text,
    cliente        text,
    data_bordero   date,
    carteira       text,            -- 'por dentro' / 'por fora'
    total_bordero  numeric(14, 2),
    desagio        numeric(14, 2),
    valor_liquido  numeric(14, 2),
    recompras      numeric(14, 2),
    creditos       numeric(14, 2),
    debitos        numeric(14, 2),
    abatimento     numeric(14, 2),
    desembolso     numeric(14, 2),
    origem_arquivo text,
    pdf_path       text,            -- caminho do PDF no Storage
    avisos         jsonb,
    criado_por     text references usuarios(email),
    criado_em      timestamptz not null default now(),
    unique (numero, carteira)
);

create table if not exists bordero_titulos (
    id          bigint generated always as identity primary key,
    bordero_id  bigint not null references borderos(id) on delete cascade,
    documento   text,
    sacado      text,
    sacado_cnpj text,
    vencimento  date,
    valor_face  numeric(14, 2),
    desagio     numeric(14, 2)
);

-- ----------------------------------------------------------------------------
-- Passivo "por fora" (lançamentos de juros, pagamentos e estornos)
-- ----------------------------------------------------------------------------
create table if not exists passivo_lancamentos (
    id          bigint generated always as identity primary key,
    data_lanc   date not null,
    base01      text,                       -- borderô por dentro (8xxx)
    base02      text,                       -- borderô por fora (7xxx)
    valor       numeric(14, 2) default 0,   -- custo gerado
    pagamento   numeric(14, 2) default 0,   -- quitação real
    estorno     numeric(14, 2) default 0,   -- devolução/estorno
    observacao  text,
    criado_por  text references usuarios(email),
    criado_em   timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- Seleções e instruções (histórico do que foi gerado)
-- ----------------------------------------------------------------------------
create table if not exists selecoes (
    id                  bigint generated always as identity primary key,
    data_ref            date,
    valor_alvo          numeric(14, 2),
    taxa_estimada_am    numeric(8, 5),
    desagio_estimado    numeric(14, 2),
    desembolso_estimado numeric(14, 2),
    itens               jsonb,              -- títulos selecionados (snapshot)
    criado_por          text references usuarios(email),
    criado_em           timestamptz not null default now()
);

create table if not exists instrucoes (
    id            bigint generated always as identity primary key,
    selecao_id    bigint references selecoes(id) on delete set null,
    assunto       text,
    destinatarios jsonb,
    corpo         text,
    criado_por    text references usuarios(email),
    criado_em     timestamptz not null default now()
);

-- Índices úteis para os relatórios
create index if not exists idx_passivo_data on passivo_lancamentos (data_lanc);
create index if not exists idx_borderos_data on borderos (data_bordero);
create index if not exists idx_bordero_titulos_bordero on bordero_titulos (bordero_id);
