-- MVP 1 schema (§7). facts/prices/forecasts/signals arrive with their MVPs.
create extension if not exists vector;

create table companies (
    ticker text primary key,
    name text not null,
    aliases text[] not null default '{}',
    sector_idxic text,
    subsector text,
    template text,                      -- general | bank | ...
    reporting_currency text,
    lq45_snapshot_date date,
    ticker_history jsonb not null default '[]'
);

create table documents (
    doc_id text primary key,            -- e.g. BBRI-AR-2025
    ticker text not null references companies,
    doc_type text not null check (doc_type in ('annual_report', 'fin_statement')),
    fiscal_year int not null,
    period text,
    source_url text not null,
    sha256 text not null,
    pages int,
    lang_layout text,                   -- en | id | side_by_side | mixed
    fetched_at timestamptz not null
);

create table pages (
    doc_id text not null references documents on delete cascade,
    page_no int not null,
    kind text not null check (kind in ('text', 'table', 'chart', 'image', 'scanned', 'mixed')),
    char_count int not null,
    parser text not null,
    primary key (doc_id, page_no)
);

create table figures (
    figure_id text primary key,         -- alias, e.g. BBRI-25-p212-c1 (§6.1)
    doc_id text not null references documents on delete cascade,
    page_no int not null,
    kind text not null check (kind in ('page', 'table', 'chart')),
    bbox real[],
    storage_path text,
    caption text,
    chart_table_md text,
    ocr_confidence real
);

-- D46: halfvec embeddings, lexical search through an expression index (no stored tsvector).
create table chunks (
    chunk_id text primary key,
    doc_id text not null references documents on delete cascade,
    ticker text not null,
    fiscal_year int not null,
    page_start int not null,
    page_end int not null,
    section_path text,
    seq int not null,
    kind text not null check (kind in ('text', 'table', 'chart')),
    lang text,
    pair_id text,
    text text not null,
    embedding halfvec(384),
    figure_id text references figures on delete set null,
    chunker text not null check (chunker in ('section', 'page'))
);
create index chunks_filter_idx on chunks (ticker, fiscal_year);
create index chunks_doc_seq_idx on chunks (doc_id, seq);
create index chunks_fts_idx on chunks using gin (to_tsvector('simple', text));
create index chunks_embedding_idx on chunks using hnsw (embedding halfvec_cosine_ops);

create table conversations (
    conv_id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    visitor_hash text not null
);

create table messages (
    conv_id uuid not null references conversations on delete cascade,
    turn int not null,
    role text not null,
    content text not null,
    lang text,
    focus jsonb,
    prompt_version text,
    trace_id text,
    created_at timestamptz not null default now(),
    primary key (conv_id, turn, role)
);

create table feedback (
    conv_id uuid not null,
    turn int not null,
    rating text not null check (rating in ('up', 'down')),
    reason text,
    created_at timestamptz not null default now()
);

create table tool_calls (
    conv_id uuid not null,
    turn int not null,
    tool text not null,
    args jsonb,
    result_summary text,
    latency_ms int,
    ok boolean
);

create table rate_limits (
    visitor_hash text not null,
    day date not null,
    count int not null default 0,
    primary key (visitor_hash, day)
);

create table answer_cache (
    key text primary key,
    response jsonb not null,
    created_at timestamptz not null default now()
);

create table eval_runs (
    run_id uuid primary key default gen_random_uuid(),
    git_sha text,
    phase text,
    metrics jsonb not null,
    created_at timestamptz not null default now()
);

-- Supabase exposes `public` through its REST API; RLS with no policies keeps anon/authenticated
-- roles out. The API connects as the table owner, which bypasses RLS.
alter table companies enable row level security;
alter table documents enable row level security;
alter table pages enable row level security;
alter table figures enable row level security;
alter table chunks enable row level security;
alter table conversations enable row level security;
alter table messages enable row level security;
alter table feedback enable row level security;
alter table tool_calls enable row level security;
alter table rate_limits enable row level security;
alter table answer_cache enable row level security;
alter table eval_runs enable row level security;
alter table schema_migrations enable row level security;
