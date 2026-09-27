-- ════════════════════════════════════════════════════════════════════════
-- ESCRITÓRIO (piloto DTZ) — etapa 2: o banco
-- Primeira área do AI.arq em que alguém além do dono acessa dados: o freela
-- entra NO PROJETO (nunca no escritório). Toda a regra de acesso mora aqui,
-- no banco (RLS + gatilhos), não só na tela.
-- Tabelas: projetos · membros · atas · tarefas · tarefa_pessoas ·
--          comentarios · emissoes · emissao_eventos · atividade
-- Fica pra etapa 3 (Drive): tokens do Google.
-- ════════════════════════════════════════════════════════════════════════

-- ── 1. Projeto do escritório (nasce sem prancha) ─────────────────────────
create table public.escritorio_projetos (
  id                    uuid primary key default gen_random_uuid(),
  dono                  uuid not null references auth.users(id) on delete cascade,
  nome                  text not null check (char_length(btrim(nome)) between 1 and 160),
  cliente_nome          text check (char_length(cliente_nome) <= 160),
  etapas                text[] not null default '{}' check (cardinality(etapas) <= 30),
  etapa_atual           text check (etapa_atual is null or etapa_atual = any (etapas)),
  inicio                date,
  entrega               date,
  proxima_entrega       text check (char_length(proxima_entrega) <= 200),
  proxima_entrega_data  date,
  drive_pasta_id        text check (char_length(drive_pasta_id) <= 200),
  drive_pasta_caminho   text check (char_length(drive_pasta_caminho) <= 500),
  job_id                text references public.projects(job_id) on delete set null,
  criado_em             timestamptz not null default now(),
  atualizado_em         timestamptz not null default now(),
  check (entrega is null or inicio is null or entrega >= inicio)
);
comment on table public.escritorio_projetos is
  'Projeto do escritório (piloto DTZ, 23/09/2026). Nasce sem prancha; job_id liga ao quantitativo quando houver. O dono vira membro papel=dono por gatilho.';

-- ── 2. Membros: o dono e os freelas convidados ───────────────────────────
create table public.escritorio_membros (
  id             uuid primary key default gen_random_uuid(),
  projeto_id     uuid not null references public.escritorio_projetos(id) on delete cascade,
  user_id        uuid references auth.users(id) on delete set null,
  email          text check (email = lower(btrim(email)) and char_length(email) <= 254
                             and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  nome           text check (char_length(nome) <= 120),
  papel          text not null check (papel in ('dono','freela')),
  funcao         text check (char_length(funcao) <= 60),
  status         text not null default 'convidado' check (status in ('convidado','ativo','removido')),
  convite_hash   text check (char_length(convite_hash) <= 128),
  convite_expira timestamptz,
  convidado_em   timestamptz not null default now(),
  aceito_em      timestamptz,
  removido_em    timestamptz,
  check (papel = 'dono' or email is not null),
  check (status <> 'ativo' or (user_id is not null and aceito_em is not null)),
  check (status <> 'removido' or removido_em is not null),
  unique (projeto_id, email),
  unique (id, projeto_id)
);
create unique index escritorio_membros_um_user_por_projeto on public.escritorio_membros (projeto_id, user_id) where user_id is not null;
create unique index escritorio_membros_um_dono on public.escritorio_membros (projeto_id) where papel = 'dono';
create index escritorio_membros_user on public.escritorio_membros (user_id) where status = 'ativo';
comment on table public.escritorio_membros is
  'Quem entra em cada projeto do escritório. Freela nasce convidado (sem user_id); só o servidor (service_role) liga o user_id e ativa, ao aceitar o convite.';

-- ── 3. O papel de quem está logado num projeto (base de todas as regras) ──
create or replace function public.escritorio_papel(p_projeto uuid)
returns text language sql stable security definer set search_path = '' as $$
  select m.papel from public.escritorio_membros m
   where m.projeto_id = p_projeto and m.user_id = (select auth.uid()) and m.status = 'ativo'
   limit 1
$$;
revoke all on function public.escritorio_papel(uuid) from public, anon;
grant execute on function public.escritorio_papel(uuid) to authenticated, service_role;

-- quem roda como servidor (service_role) ou manutenção passa pelas guardas
create or replace function public.escritorio_eh_servidor()
returns boolean language sql stable set search_path = '' as $$
  select current_user in ('service_role','postgres','supabase_admin')
$$;

-- ── 4. Atas ──────────────────────────────────────────────────────────────
create table public.escritorio_atas (
  id               uuid primary key default gen_random_uuid(),
  projeto_id       uuid not null references public.escritorio_projetos(id) on delete cascade,
  data             date not null,
  titulo           text not null check (char_length(btrim(titulo)) between 1 and 200),
  texto_original   text check (char_length(texto_original) <= 50000),
  decisoes         text[] not null default '{}' check (cardinality(decisoes) <= 60),
  participantes    text[] not null default '{}' check (cardinality(participantes) <= 40),
  proxima_reuniao  text check (char_length(proxima_reuniao) <= 200),
  drive_doc_id     text check (char_length(drive_doc_id) <= 200),
  criado_por       uuid default auth.uid() references auth.users(id) on delete set null,
  criado_em        timestamptz not null default now(),
  atualizado_em    timestamptz not null default now(),
  unique (id, projeto_id)
);
create index escritorio_atas_projeto on public.escritorio_atas (projeto_id, data desc);

-- ── 5. Tarefas (quadro) ──────────────────────────────────────────────────
create table public.escritorio_tarefas (
  id               uuid primary key default gen_random_uuid(),
  projeto_id       uuid not null references public.escritorio_projetos(id) on delete cascade,
  titulo           text not null check (char_length(btrim(titulo)) between 1 and 300),
  descricao        text check (char_length(descricao) <= 5000),
  status           text not null default 'afazer'
                   check (status in ('afazer','dev','revdtz','revsol','cliente','aprov','ok')),
  posicao          double precision not null default 0 check (posicao = posicao and posicao between -1e15 and 1e15),
  etapa            text check (char_length(etapa) <= 80),
  prazo            date,
  do_cliente       boolean not null default false,
  ata_id           uuid,
  criado_por       uuid default auth.uid() references auth.users(id) on delete set null,
  criado_em        timestamptz not null default now(),
  atualizado_em    timestamptz not null default now(),
  status_mudou_em  timestamptz not null default now(),
  unique (id, projeto_id),
  foreign key (ata_id, projeto_id) references public.escritorio_atas(id, projeto_id) on delete set null (ata_id)
);
create index escritorio_tarefas_quadro on public.escritorio_tarefas (projeto_id, status, posicao);
comment on column public.escritorio_tarefas.status is
  'Esteira DTZ: afazer → dev → revdtz (aguardando revisão DTZ) → revsol (revisão solicitada) → cliente → aprov → ok. Freela só move entre afazer/dev/revdtz (e pega revsol de volta); o resto é do dono.';
comment on column public.escritorio_tarefas.posicao is
  'Ordem dentro da coluna (arrastar pra cima/baixo). A tela grava o ponto médio entre os vizinhos.';

-- Pessoas marcadas na tarefa (como os membros do cartão do Trello).
-- FKs compostas com projeto_id: ninguém marca gente de OUTRO projeto (regra nº2).
create table public.escritorio_tarefa_pessoas (
  tarefa_id   uuid not null,
  membro_id   uuid not null,
  projeto_id  uuid not null,
  marcado_em  timestamptz not null default now(),
  primary key (tarefa_id, membro_id),
  foreign key (tarefa_id, projeto_id) references public.escritorio_tarefas(id, projeto_id) on delete cascade,
  foreign key (membro_id, projeto_id) references public.escritorio_membros(id, projeto_id) on delete cascade
);
create index escritorio_tarefa_pessoas_membro on public.escritorio_tarefa_pessoas (membro_id);

create table public.escritorio_comentarios (
  id          uuid primary key default gen_random_uuid(),
  tarefa_id   uuid not null,
  projeto_id  uuid not null,
  autor       uuid default auth.uid() references auth.users(id) on delete set null,
  texto       text not null check (char_length(btrim(texto)) between 1 and 5000),
  mencoes     uuid[] not null default '{}' check (cardinality(mencoes) <= 20),
  criado_em   timestamptz not null default now(),
  editado_em  timestamptz,
  foreign key (tarefa_id, projeto_id) references public.escritorio_tarefas(id, projeto_id) on delete cascade
);
create index escritorio_comentarios_tarefa on public.escritorio_comentarios (tarefa_id, criado_em);

-- ── 6. Emissões (cópia R00/R01… no Drive) e o que o cliente fez ─────────
create table public.escritorio_emissoes (
  id                uuid primary key default gen_random_uuid(),
  projeto_id        uuid not null references public.escritorio_projetos(id) on delete cascade,
  drive_arquivo_id  text not null check (char_length(drive_arquivo_id) <= 200),
  arquivo_nome      text not null check (char_length(arquivo_nome) between 1 and 300),
  revisao           integer not null check (revisao between 0 and 99),
  drive_copia_id    text check (char_length(drive_copia_id) <= 200),
  copia_nome        text check (char_length(copia_nome) <= 320),
  nota              text check (char_length(nota) <= 1000),
  emitido_por       uuid default auth.uid() references auth.users(id) on delete set null,
  emitido_em        timestamptz not null default now(),
  unique (projeto_id, drive_arquivo_id, revisao),
  unique (id, projeto_id)
);
create table public.escritorio_emissao_eventos (
  id              uuid primary key default gen_random_uuid(),
  emissao_id      uuid not null,
  projeto_id      uuid not null,
  tipo            text not null check (tipo in ('enviado','aprovado','revisao')),
  em              date not null,
  nota            text check (char_length(nota) <= 1000),
  registrado_por  uuid default auth.uid() references auth.users(id) on delete set null,
  criado_em       timestamptz not null default now(),
  foreign key (emissao_id, projeto_id) references public.escritorio_emissoes(id, projeto_id) on delete cascade
);
create index escritorio_emissao_eventos_emissao on public.escritorio_emissao_eventos (emissao_id, em);

-- ── 7. "O que andou" — só o servidor escreve ─────────────────────────────
create table public.escritorio_atividade (
  id          bigint generated always as identity primary key,
  projeto_id  uuid not null references public.escritorio_projetos(id) on delete cascade,
  autor       uuid references auth.users(id) on delete set null,
  tipo        text not null check (char_length(tipo) <= 40),
  resumo      text not null check (char_length(resumo) <= 500),
  criado_em   timestamptz not null default now()
);
create index escritorio_atividade_projeto on public.escritorio_atividade (projeto_id, criado_em desc);

-- ── 8. Gatilhos ──────────────────────────────────────────────────────────
create or replace function public.escritorio_toca()
returns trigger language plpgsql set search_path = '' as $$
begin new.atualizado_em := now(); return new; end $$;
create trigger escritorio_projetos_toca before update on public.escritorio_projetos for each row execute function public.escritorio_toca();
create trigger escritorio_atas_toca     before update on public.escritorio_atas     for each row execute function public.escritorio_toca();

-- Quem cria o projeto vira o membro "dono", ativo.
create or replace function public.escritorio_dono_vira_membro()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.escritorio_membros (projeto_id, user_id, email, papel, status, aceito_em)
  select new.id, new.dono, nullif(lower(btrim(u.email)),''), 'dono', 'ativo', now()
    from auth.users u where u.id = new.dono;
  return new;
end $$;
create trigger escritorio_projetos_dono after insert on public.escritorio_projetos
  for each row execute function public.escritorio_dono_vira_membro();

-- O dono não se troca; o projeto não muda de dono pela tela.
create or replace function public.escritorio_projeto_guarda()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.dono is distinct from old.dono and not public.escritorio_eh_servidor() then
    raise exception 'o dono do projeto não muda por aqui' using errcode = '42501';
  end if;
  return new;
end $$;
create trigger escritorio_projetos_guarda before update on public.escritorio_projetos
  for each row execute function public.escritorio_projeto_guarda();

-- Membros: a linha do dono é intocável; ativar/ligar user_id é só do servidor (aceite do convite).
create or replace function public.escritorio_membro_guarda()
returns trigger language plpgsql set search_path = '' as $$
begin
  if public.escritorio_eh_servidor() then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  if tg_op = 'DELETE' then
    if old.papel = 'dono' and exists (select 1 from public.escritorio_projetos p where p.id = old.projeto_id) then
      raise exception 'o dono não sai do próprio projeto' using errcode = '42501';
    end if;
    return old;
  end if;
  if old.papel = 'dono' then
    raise exception 'a linha do dono não se edita' using errcode = '42501';
  end if;
  if new.projeto_id <> old.projeto_id or new.papel <> old.papel
     or new.user_id is distinct from old.user_id
     or new.convite_hash is distinct from old.convite_hash
     or (new.status = 'ativo' and old.status <> 'ativo')
     or (old.status = 'removido' and new.status <> 'removido') then
    raise exception 'só o aceite do convite (servidor) ativa ou liga uma pessoa' using errcode = '42501';
  end if;
  if new.status = 'removido' and old.status <> 'removido' then new.removido_em := coalesce(new.removido_em, now()); end if;
  return new;
end $$;
create trigger escritorio_membros_guarda before update or delete on public.escritorio_membros
  for each row execute function public.escritorio_membro_guarda();

-- A esteira: freela anda entre A fazer / Em desenvolvimento / Aguardando revisão DTZ
-- (e pega de volta o que veio como Revisão solicitada). Daí pra frente é do dono.
create or replace function public.escritorio_tarefa_guarda()
returns trigger language plpgsql set search_path = '' as $$
declare v_papel text;
begin
  if tg_op = 'UPDATE' then
    if new.projeto_id <> old.projeto_id then
      raise exception 'tarefa não muda de projeto' using errcode = '42501';
    end if;
    new.atualizado_em := now();
    if new.status is distinct from old.status then new.status_mudou_em := now(); end if;
  end if;
  if public.escritorio_eh_servidor() then return new; end if;
  v_papel := public.escritorio_papel(new.projeto_id);
  if v_papel = 'dono' then return new; end if;
  if tg_op = 'INSERT' then
    if not (new.status in ('afazer','dev','revdtz') or (new.do_cliente and new.status = 'cliente')) then
      raise exception 'freela cria tarefa em A fazer, Em desenvolvimento ou Aguardando revisão DTZ' using errcode = '42501';
    end if;
  elsif new.status is distinct from old.status then
    if old.status not in ('afazer','dev','revdtz','revsol') or new.status not in ('afazer','dev','revdtz') then
      raise exception 'daqui pra frente quem move é a dona do projeto' using errcode = '42501';
    end if;
  end if;
  return new;
end $$;
create trigger escritorio_tarefas_guarda before insert or update on public.escritorio_tarefas
  for each row execute function public.escritorio_tarefa_guarda();

-- ── 9. RLS ───────────────────────────────────────────────────────────────
alter table public.escritorio_projetos        enable row level security;
alter table public.escritorio_membros         enable row level security;
alter table public.escritorio_atas            enable row level security;
alter table public.escritorio_tarefas         enable row level security;
alter table public.escritorio_tarefa_pessoas  enable row level security;
alter table public.escritorio_comentarios     enable row level security;
alter table public.escritorio_emissoes        enable row level security;
alter table public.escritorio_emissao_eventos enable row level security;
alter table public.escritorio_atividade       enable row level security;

revoke all on public.escritorio_projetos, public.escritorio_membros, public.escritorio_atas,
              public.escritorio_tarefas, public.escritorio_tarefa_pessoas, public.escritorio_comentarios,
              public.escritorio_emissoes, public.escritorio_emissao_eventos, public.escritorio_atividade
  from anon;

-- projetos
-- o dono entra direto (o RETURNING do INSERT é checado ANTES do gatilho que o torna membro)
create policy escritorio_projetos_ver    on public.escritorio_projetos for select to authenticated
  using (dono = (select auth.uid()) or public.escritorio_papel(id) is not null);
create policy escritorio_projetos_criar  on public.escritorio_projetos for insert to authenticated
  with check (dono = (select auth.uid()));
create policy escritorio_projetos_editar on public.escritorio_projetos for update to authenticated
  using (public.escritorio_papel(id) = 'dono') with check (dono = (select auth.uid()));
create policy escritorio_projetos_apagar on public.escritorio_projetos for delete to authenticated
  using (public.escritorio_papel(id) = 'dono');

-- membros: dono vê todos (inclusive convites); freela vê só quem está ativo
create policy escritorio_membros_ver on public.escritorio_membros for select to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono'
         or (public.escritorio_papel(projeto_id) is not null and status = 'ativo'));
create policy escritorio_membros_convidar on public.escritorio_membros for insert to authenticated
  with check (public.escritorio_papel(projeto_id) = 'dono' and papel = 'freela'
              and status = 'convidado' and user_id is null);
create policy escritorio_membros_editar on public.escritorio_membros for update to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono')
  with check (public.escritorio_papel(projeto_id) = 'dono' and papel = 'freela');
create policy escritorio_membros_apagar on public.escritorio_membros for delete to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono' and papel = 'freela');

-- atas: todo membro lê e cria; edita/apaga o dono ou quem criou
create policy escritorio_atas_ver    on public.escritorio_atas for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_atas_criar  on public.escritorio_atas for insert to authenticated
  with check (public.escritorio_papel(projeto_id) is not null and criado_por = (select auth.uid()));
create policy escritorio_atas_editar on public.escritorio_atas for update to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono' or criado_por = (select auth.uid()))
  with check (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_atas_apagar on public.escritorio_atas for delete to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono'
         or (criado_por = (select auth.uid()) and public.escritorio_papel(projeto_id) is not null));

-- tarefas: todo membro lê, cria e move (a esteira é o gatilho); apaga o dono ou quem criou
create policy escritorio_tarefas_ver    on public.escritorio_tarefas for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_tarefas_criar  on public.escritorio_tarefas for insert to authenticated
  with check (public.escritorio_papel(projeto_id) is not null and criado_por = (select auth.uid()));
create policy escritorio_tarefas_editar on public.escritorio_tarefas for update to authenticated
  using (public.escritorio_papel(projeto_id) is not null)
  with check (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_tarefas_apagar on public.escritorio_tarefas for delete to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono'
         or (criado_por = (select auth.uid()) and public.escritorio_papel(projeto_id) is not null));

-- pessoas marcadas: qualquer membro marca/desmarca
create policy escritorio_tarefa_pessoas_ver on public.escritorio_tarefa_pessoas for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_tarefa_pessoas_marcar on public.escritorio_tarefa_pessoas for insert to authenticated
  with check (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_tarefa_pessoas_desmarcar on public.escritorio_tarefa_pessoas for delete to authenticated
  using (public.escritorio_papel(projeto_id) is not null);

-- comentários: membro lê e escreve como ele mesmo; edita/apaga o autor (o dono também apaga)
create policy escritorio_comentarios_ver    on public.escritorio_comentarios for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_comentarios_criar  on public.escritorio_comentarios for insert to authenticated
  with check (public.escritorio_papel(projeto_id) is not null and autor = (select auth.uid()));
create policy escritorio_comentarios_editar on public.escritorio_comentarios for update to authenticated
  using (autor = (select auth.uid()) and public.escritorio_papel(projeto_id) is not null)
  with check (autor = (select auth.uid()) and public.escritorio_papel(projeto_id) is not null);
create policy escritorio_comentarios_apagar on public.escritorio_comentarios for delete to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono'
         or (autor = (select auth.uid()) and public.escritorio_papel(projeto_id) is not null));

-- emissões e eventos do cliente: membro lê; só o dono escreve ("Emitir" é do admin)
create policy escritorio_emissoes_ver on public.escritorio_emissoes for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_emissoes_dono on public.escritorio_emissoes for all to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono')
  with check (public.escritorio_papel(projeto_id) = 'dono');
create policy escritorio_emissao_eventos_ver on public.escritorio_emissao_eventos for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_emissao_eventos_dono on public.escritorio_emissao_eventos for all to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono')
  with check (public.escritorio_papel(projeto_id) = 'dono');

-- atividade: membro lê; só o servidor escreve (sem política de escrita)
create policy escritorio_atividade_ver on public.escritorio_atividade for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);

-- ── 10. (2ª migração, mesmo dia) funções de gatilho fechadas pra chamada direta via /rpc ──
revoke all on function public.escritorio_dono_vira_membro() from public, anon, authenticated;
revoke all on function public.escritorio_membro_guarda() from public, anon, authenticated;
revoke all on function public.escritorio_tarefa_guarda() from public, anon, authenticated;
revoke all on function public.escritorio_projeto_guarda() from public, anon, authenticated;
revoke all on function public.escritorio_toca() from public, anon, authenticated;
revoke all on function public.escritorio_eh_servidor() from public, anon;
grant execute on function public.escritorio_eh_servidor() to authenticated, service_role;

-- ── 11. (3ª migração) dados de contato editáveis de cada pessoa convidada ──
alter table public.escritorio_membros
  add column telefone   text check (char_length(telefone) <= 40),
  add column observacao text check (char_length(observacao) <= 1000);

-- ── 12. (4ª migração) armazenamento neutro: Google Drive hoje; OneDrive e Dropbox depois ──
alter table public.escritorio_projetos rename column drive_pasta_id to pasta_id;
alter table public.escritorio_projetos rename column drive_pasta_caminho to pasta_caminho;
alter table public.escritorio_projetos
  add column armazenamento text not null default 'google_drive'
  check (armazenamento in ('google_drive','onedrive','dropbox'));
alter table public.escritorio_emissoes rename column drive_arquivo_id to arquivo_id;
alter table public.escritorio_emissoes rename column drive_copia_id to copia_id;
alter table public.escritorio_atas rename column drive_doc_id to doc_id;

-- ── 13. (5ª migração) a nota do admin mora em tabela própria (a equipe LÊ escritorio_membros);
--        o admin nasce com o nome do cadastro; flag do piloto no perfil (liga por SQL — o repo é público) ──
alter table public.escritorio_membros drop column observacao;
create table public.escritorio_membro_notas (
  membro_id   uuid primary key,
  projeto_id  uuid not null,
  observacao  text not null check (char_length(observacao) <= 1000),
  atualizado_em timestamptz not null default now(),
  foreign key (membro_id, projeto_id) references public.escritorio_membros(id, projeto_id) on delete cascade
);
alter table public.escritorio_membro_notas enable row level security;
revoke all on public.escritorio_membro_notas from anon;
create policy escritorio_membro_notas_admin on public.escritorio_membro_notas for all to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono')
  with check (public.escritorio_papel(projeto_id) = 'dono');
create or replace function public.escritorio_dono_vira_membro()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.escritorio_membros (projeto_id, user_id, email, nome, papel, status, aceito_em)
  select new.id, new.dono, nullif(lower(btrim(u.email)),''),
         nullif(left(btrim((select p.full_name from public.profiles p where p.user_id = new.dono::text limit 1)), 120), ''),
         'dono', 'ativo', now()
    from auth.users u where u.id = new.dono;
  return new;
end $$;
revoke all on function public.escritorio_dono_vira_membro() from public, anon, authenticated;
alter table public.profiles add column if not exists piloto_escritorio boolean not null default false;

-- ── 14. (24/09, revisão de segurança) apagar a conta NÃO pode travar num projeto de terceiro ──
-- 🩸 user_id ON DELETE SET NULL batia no CHECK "ativo exige user_id"; e a guarda do dono barrava a
-- exclusão da conta do próprio admin. Direito de apagar a conta (LGPD) não trava.
alter table public.escritorio_membros drop constraint escritorio_membros_user_id_fkey;
alter table public.escritorio_membros
  add constraint escritorio_membros_user_id_fkey foreign key (user_id) references auth.users(id) on delete cascade;
create or replace function public.escritorio_conta_existe(p_user uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from auth.users u where u.id = p_user)
$$;
revoke all on function public.escritorio_conta_existe(uuid) from public, anon;
grant execute on function public.escritorio_conta_existe(uuid) to authenticated, service_role, supabase_auth_admin;
-- (escritorio_membro_guarda: o bloqueio do DELETE da linha do dono passa a exigir escritorio_conta_existe(old.user_id))
-- a exclusão de conta roda como supabase_auth_admin: não é gente usando a tela
create or replace function public.escritorio_eh_servidor()
returns boolean language sql stable set search_path = '' as $$
  select current_user in ('service_role','postgres','supabase_admin','supabase_auth_admin')
$$;

-- ── 15. (24/09) contato da equipe só o admin vê (minimização): RPC do admin ──
create or replace function public.escritorio_contatos(p_projeto uuid)
returns table (membro_id uuid, email text, telefone text)
language sql stable security definer set search_path = '' as $$
  select m.id, m.email, m.telefone from public.escritorio_membros m
   where m.projeto_id = p_projeto and public.escritorio_papel(p_projeto) = 'dono'
$$;
revoke all on function public.escritorio_contatos(uuid) from public, anon;
grant execute on function public.escritorio_contatos(uuid) to authenticated;
-- ── 16. (24/09, aplicado DEPOIS do deploy 4b1afcc da tela que pede colunas por nome) ──
-- e-mail, telefone e hash do convite fora do alcance de quem está logado (9/9 provado em transação desfeita)
revoke select on public.escritorio_membros from authenticated;
grant select (id, projeto_id, user_id, nome, papel, funcao, status, convidado_em, aceito_em, removido_em)
  on public.escritorio_membros to authenticated;

-- ── 17. (24/09) URGENTES da varredura (A1, A3, A4, A7) ──
-- A1: o piloto era só o card do painel; o banco deixava QUALQUER conta criar projeto e,
--     pela rota, mandar convite pelo nosso SMTP. Agora a lista do piloto mora no banco e
--     só o servidor/manutenção escreve nela.
create table public.escritorio_piloto (
  user_id     uuid primary key references auth.users(id) on delete cascade,
  liberado_em timestamptz not null default now()
);
comment on table public.escritorio_piloto is
  'Quem pode CRIAR projeto no Escritório (piloto). Só servidor/manutenção escreve. Convidado não precisa estar aqui.';
alter table public.escritorio_piloto enable row level security;
revoke all on public.escritorio_piloto from anon, authenticated;

create or replace function public.escritorio_no_piloto()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.escritorio_piloto p where p.user_id = (select auth.uid()))
$$;
revoke all on function public.escritorio_no_piloto() from public, anon;
grant execute on function public.escritorio_no_piloto() to authenticated, service_role;

drop policy escritorio_projetos_criar on public.escritorio_projetos;
create policy escritorio_projetos_criar on public.escritorio_projetos for insert to authenticated
  with check (dono = (select auth.uid()) and public.escritorio_no_piloto());

-- A3: o teto contava LINHAS (reenvio contava 1, cancelar zerava). Agora conta ENVIOS, numa
--     tabela que só o servidor escreve; o destino guardado é o SHA-256 do e-mail, não o e-mail.
create table public.escritorio_convites_enviados (
  id           bigint generated always as identity primary key,
  admin        uuid not null references auth.users(id) on delete cascade,
  projeto_id   uuid references public.escritorio_projetos(id) on delete set null,
  destino_hash text not null check (char_length(destino_hash) = 64),
  enviado_em   timestamptz not null default now()
);
create index escritorio_convites_enviados_admin on public.escritorio_convites_enviados (admin, enviado_em desc);
create index escritorio_convites_enviados_destino on public.escritorio_convites_enviados (destino_hash, enviado_em desc);
comment on table public.escritorio_convites_enviados is
  'Cada envio de convite (teto por admin e por destinatário). Só o servidor escreve; destino = sha256(email).';
alter table public.escritorio_convites_enviados enable row level security;
revoke all on public.escritorio_convites_enviados from anon, authenticated;

-- A3: convite só nasce pelo servidor (que conta, limita e manda o e-mail).
drop policy escritorio_membros_convidar on public.escritorio_membros;

-- A3/A7: datas do convite e e-mail não mudam pela tela; só o servidor.
create or replace function public.escritorio_membro_guarda()
returns trigger language plpgsql set search_path = '' as $$
begin
  if public.escritorio_eh_servidor() then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  if tg_op = 'DELETE' then
    if old.papel = 'dono'
       and exists (select 1 from public.escritorio_projetos p where p.id = old.projeto_id)
       and public.escritorio_conta_existe(old.user_id) then
      raise exception 'o dono não sai do próprio projeto' using errcode = '42501';
    end if;
    return old;
  end if;
  if old.papel = 'dono' then
    raise exception 'a linha do dono não se edita' using errcode = '42501';
  end if;
  if new.projeto_id <> old.projeto_id or new.papel <> old.papel
     or new.user_id is distinct from old.user_id
     or new.convite_hash is distinct from old.convite_hash
     or (new.status = 'ativo' and old.status <> 'ativo')
     or (old.status = 'removido' and new.status <> 'removido') then
    raise exception 'só o aceite do convite (servidor) ativa ou liga uma pessoa' using errcode = '42501';
  end if;
  if new.email is distinct from old.email
     or new.convite_expira is distinct from old.convite_expira
     or new.convidado_em is distinct from old.convidado_em
     or new.aceito_em is distinct from old.aceito_em then
    raise exception 'e-mail e datas do convite só mudam por um convite novo' using errcode = '42501';
  end if;
  if new.status = 'removido' and old.status <> 'removido' then new.removido_em := coalesce(new.removido_em, now()); end if;
  return new;
end $$;
revoke all on function public.escritorio_membro_guarda() from public, anon, authenticated;

-- A7: apagar linha de membro só enquanto NÃO está ativo (cancelar convite; quem saiu).
drop policy escritorio_membros_apagar on public.escritorio_membros;
create policy escritorio_membros_apagar on public.escritorio_membros for delete to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono' and papel = 'freela' and status <> 'ativo');

-- A4: autoria e datas da tarefa não mudam pela tela; a equipe só apaga cartão nas colunas dela.
create or replace function public.escritorio_tarefa_guarda()
returns trigger language plpgsql set search_path = '' as $$
declare v_papel text;
begin
  if tg_op = 'UPDATE' then
    if new.projeto_id <> old.projeto_id then
      raise exception 'tarefa não muda de projeto' using errcode = '42501';
    end if;
    new.atualizado_em := now();
    if new.status is distinct from old.status then new.status_mudou_em := now();
    else new.status_mudou_em := old.status_mudou_em; end if;
  end if;
  if public.escritorio_eh_servidor() then return new; end if;
  if tg_op = 'INSERT' then
    new.criado_em := now(); new.atualizado_em := now(); new.status_mudou_em := now();
  elsif new.criado_por is distinct from old.criado_por or new.criado_em is distinct from old.criado_em then
    raise exception 'autoria e data de criação da tarefa não mudam' using errcode = '42501';
  end if;
  v_papel := public.escritorio_papel(new.projeto_id);
  if v_papel = 'dono' then return new; end if;
  if tg_op = 'INSERT' then
    if not (new.status in ('afazer','dev','revdtz') or (new.do_cliente and new.status = 'cliente')) then
      raise exception 'freela cria tarefa em A fazer, Em desenvolvimento ou Aguardando revisão DTZ' using errcode = '42501';
    end if;
  elsif new.status is distinct from old.status then
    if old.status not in ('afazer','dev','revdtz','revsol') or new.status not in ('afazer','dev','revdtz') then
      raise exception 'daqui pra frente quem move é a dona do projeto' using errcode = '42501';
    end if;
  end if;
  return new;
end $$;
revoke all on function public.escritorio_tarefa_guarda() from public, anon, authenticated;

create or replace function public.escritorio_tarefa_apagar_guarda()
returns trigger language plpgsql set search_path = '' as $$
begin
  if public.escritorio_eh_servidor() then return old; end if;
  -- papel NULO (projeto já sumindo na cascata, ou não-membro que a RLS já barra) não trava.
  if public.escritorio_papel(old.projeto_id) = 'freela'
     and old.status not in ('afazer','dev','revdtz') then
    raise exception 'cartão nesta coluna só a admin do projeto apaga' using errcode = '42501';
  end if;
  return old;
end $$;
revoke all on function public.escritorio_tarefa_apagar_guarda() from public, anon, authenticated;
create trigger escritorio_tarefas_apagar_guarda before delete on public.escritorio_tarefas
  for each row execute function public.escritorio_tarefa_apagar_guarda();

-- A4 (irmão): comentário não muda de autor, tarefa nem data; editar o texto carimba editado_em.
create or replace function public.escritorio_comentario_guarda()
returns trigger language plpgsql set search_path = '' as $$
begin
  if public.escritorio_eh_servidor() then return new; end if;
  if tg_op = 'INSERT' then
    new.criado_em := now(); new.editado_em := null;
    return new;
  end if;
  if new.autor is distinct from old.autor or new.tarefa_id <> old.tarefa_id
     or new.projeto_id <> old.projeto_id or new.criado_em is distinct from old.criado_em then
    raise exception 'autor, tarefa e data do comentário não mudam' using errcode = '42501';
  end if;
  if new.texto is distinct from old.texto then new.editado_em := now();
  else new.editado_em := old.editado_em; end if;
  return new;
end $$;
revoke all on function public.escritorio_comentario_guarda() from public, anon, authenticated;
create trigger escritorio_comentarios_guarda before insert or update on public.escritorio_comentarios
  for each row execute function public.escritorio_comentario_guarda();
-- (piloto: Pedro e a arquiteta do piloto inseridos por SQL à parte; ids não entram no repo)

-- ── 18. (24/09, revisão adversarial) o cartão LEMBRA que passou pela admin ──
-- A equipe contornava a trava de apagar em duas jogadas (revsol → afazer → apagar).
-- A marca liga quando o cartão entra em revsol/cliente/aprov/ok e nunca desliga; cartão marcado só a admin apaga.
alter table public.escritorio_tarefas add column passou_pela_admin boolean not null default false;
comment on column public.escritorio_tarefas.passou_pela_admin is
  'Liga quando o cartão entra em revsol/cliente/aprov/ok e nunca desliga. Cartão marcado só a admin apaga.';

create or replace function public.escritorio_tarefa_guarda()
returns trigger language plpgsql set search_path = '' as $$
declare v_papel text;
begin
  if tg_op = 'UPDATE' then
    if new.projeto_id <> old.projeto_id then
      raise exception 'tarefa não muda de projeto' using errcode = '42501';
    end if;
    new.atualizado_em := now();
    if new.status is distinct from old.status then new.status_mudou_em := now();
    else new.status_mudou_em := old.status_mudou_em; end if;
  end if;
  if new.status in ('revsol','cliente','aprov','ok') then new.passou_pela_admin := true;
  elsif tg_op = 'UPDATE' then new.passou_pela_admin := new.passou_pela_admin or old.passou_pela_admin; end if;
  if public.escritorio_eh_servidor() then return new; end if;
  if tg_op = 'INSERT' then
    new.criado_em := now(); new.atualizado_em := now(); new.status_mudou_em := now();
    new.passou_pela_admin := new.status in ('revsol','cliente','aprov','ok');
  else
    if new.criado_por is distinct from old.criado_por or new.criado_em is distinct from old.criado_em then
      raise exception 'autoria e data de criação da tarefa não mudam' using errcode = '42501';
    end if;
    new.passou_pela_admin := old.passou_pela_admin or new.status in ('revsol','cliente','aprov','ok');
  end if;
  v_papel := public.escritorio_papel(new.projeto_id);
  if v_papel = 'dono' then return new; end if;
  if tg_op = 'INSERT' then
    if not (new.status in ('afazer','dev','revdtz') or (new.do_cliente and new.status = 'cliente')) then
      raise exception 'freela cria tarefa em A fazer, Em desenvolvimento ou Aguardando revisão DTZ' using errcode = '42501';
    end if;
  elsif new.status is distinct from old.status then
    if old.status not in ('afazer','dev','revdtz','revsol') or new.status not in ('afazer','dev','revdtz') then
      raise exception 'daqui pra frente quem move é a dona do projeto' using errcode = '42501';
    end if;
  end if;
  return new;
end $$;
revoke all on function public.escritorio_tarefa_guarda() from public, anon, authenticated;

create or replace function public.escritorio_tarefa_apagar_guarda()
returns trigger language plpgsql set search_path = '' as $$
begin
  if public.escritorio_eh_servidor() then return old; end if;
  if public.escritorio_papel(old.projeto_id) = 'freela'
     and (old.status not in ('afazer','dev','revdtz') or old.passou_pela_admin) then
    raise exception 'cartão que já passou pela admin só a admin apaga' using errcode = '42501';
  end if;
  return old;
end $$;
revoke all on function public.escritorio_tarefa_apagar_guarda() from public, anon, authenticated;

-- ── 19. (24/09, 2ª revisão) o convite sabe QUAL CONTA o abriu ──
-- A varredura de e-mails reconhecia o convidado pelo e-mail do convite (falha se ele entra com outro) ou por um
-- texto livre do cadastro (pegava cliente comum por engano). Agora o servidor grava, com JWT + token, a conta que
-- chegou na confirmação do convite; "Agora não" apaga; convite cancelado/vencido/aceito libera sozinho.
-- A coluna NÃO entra no GRANT de SELECT por coluna de authenticated (seção 16): a tela não lê.
alter table public.escritorio_membros add column visto_por uuid references auth.users(id) on delete set null;
comment on column public.escritorio_membros.visto_por is
  'Conta que abriu a confirmação deste convite pendente. Só o servidor escreve. Tira a pessoa da esteira de cliente.';

create or replace function public.escritorio_membro_guarda()
returns trigger language plpgsql set search_path = '' as $$
begin
  if public.escritorio_eh_servidor() then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  if tg_op = 'DELETE' then
    if old.papel = 'dono'
       and exists (select 1 from public.escritorio_projetos p where p.id = old.projeto_id)
       and public.escritorio_conta_existe(old.user_id) then
      raise exception 'o dono não sai do próprio projeto' using errcode = '42501';
    end if;
    return old;
  end if;
  if old.papel = 'dono' then
    raise exception 'a linha do dono não se edita' using errcode = '42501';
  end if;
  if new.projeto_id <> old.projeto_id or new.papel <> old.papel
     or new.user_id is distinct from old.user_id
     or new.convite_hash is distinct from old.convite_hash
     or new.visto_por is distinct from old.visto_por
     or (new.status = 'ativo' and old.status <> 'ativo')
     or (old.status = 'removido' and new.status <> 'removido') then
    raise exception 'só o aceite do convite (servidor) ativa ou liga uma pessoa' using errcode = '42501';
  end if;
  if new.email is distinct from old.email
     or new.convite_expira is distinct from old.convite_expira
     or new.convidado_em is distinct from old.convidado_em
     or new.aceito_em is distinct from old.aceito_em then
    raise exception 'e-mail e datas do convite só mudam por um convite novo' using errcode = '42501';
  end if;
  if new.status = 'removido' and old.status <> 'removido' then new.removido_em := coalesce(new.removido_em, now()); end if;
  return new;
end $$;
revoke all on function public.escritorio_membro_guarda() from public, anon, authenticated;

-- ── 20. (24/09, depois do deploy 524f67c) a flag antiga do piloto sai de profiles ──
-- O próprio usuário podia ligar `profiles.piloto_escritorio` (achado A1). A lista do piloto mora em
-- escritorio_piloto (só o servidor escreve). Os 2 marcados já estavam lá; nenhuma política/função/view
-- nem página no ar lia a coluna. Aplicada como migração `profiles_drop_piloto_escritorio`.
alter table public.profiles drop column if exists piloto_escritorio;

-- ── 21. (24/09) projeto do Escritório LIGADO a um projeto medido (grupo "Escritório" no menu do projeto) ──
-- Um projeto medido liga no máximo UM projeto do Escritório, e só o DONO do projeto medido liga.
-- 🪤 A conta de administração do site LÊ os projetos de todos os clientes (política "Admin reads all
-- projects" em public.projects): "consigo ver o projeto" não prova "o projeto é meu". A trava confere
-- projects.user_id = dono. A função é INVOKER de propósito: dentro de SECURITY DEFINER o current_user
-- vira o dono da função e escritorio_eh_servidor() diria "servidor" pra todo mundo.
create unique index escritorio_projetos_um_por_job on public.escritorio_projetos (job_id) where job_id is not null;

create or replace function public.escritorio_projeto_job_guarda()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.job_id is null or public.escritorio_eh_servidor() then return new; end if;
  if tg_op = 'UPDATE' and new.job_id is not distinct from old.job_id then return new; end if;
  if not exists (select 1 from public.projects p where p.job_id = new.job_id and p.user_id = new.dono::text) then
    raise exception 'só o dono do projeto medido liga ele ao Escritório' using errcode = '42501';
  end if;
  return new;
end $$;
revoke all on function public.escritorio_projeto_job_guarda() from public, anon, authenticated;
create trigger escritorio_projetos_job before insert or update of job_id on public.escritorio_projetos
  for each row execute function public.escritorio_projeto_job_guarda();

-- ── 22. (24/09, Parte 2) quem da EQUIPE pode BAIXAR arquivos do projeto medido ligado ──
-- A equipe VÊ o quantitativo, as pranchas, o cronograma e o memorial do projeto medido ligado (servidor:
-- `_require_project_viewer`). BAIXAR (planilha, exports do cronograma, memorial .docx/.pdf) só com
-- autorização da admin, POR PESSOA (decisão do Pedro, 24/09). Só quem é dono do projeto edita linha de
-- membro (política escritorio_membros_editar): ensaio em transação desfeita — o freela tentou se liberar
-- e 0 linhas mudaram; a admin liberou e 1 mudou. Aplicada como `escritorio_membros_pode_baixar`.
alter table public.escritorio_membros add column pode_baixar boolean not null default false;
comment on column public.escritorio_membros.pode_baixar is
  'A admin autoriza esta pessoa a baixar planilha/cronograma/memorial do projeto medido ligado. Padrão: não.';
grant select (pode_baixar) on public.escritorio_membros to authenticated;

-- ── 23. (24/09) Escritório × Google Drive — as duas tabelas são SÓ do servidor ──
-- RLS ligada sem política e sem grant pra anon/authenticated: a tela nunca vê a chave de acesso ao Drive.
-- Ensaio em transação desfeita: authenticated e anon não leem; service_role lê e escreve.
-- Aplicada como `escritorio_drive_tabelas`. Código: backend/escritorio_drive.py.
create table public.escritorio_drive_conexoes (
  user_id uuid primary key references auth.users(id) on delete cascade,
  google_email text,
  token_cifrado text not null,
  conectado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);
comment on table public.escritorio_drive_conexoes is
  'Conta do Google Drive ligada por quem administra projetos do Escritório. token_cifrado = refresh token cifrado pelo servidor (Fernet; chave derivada do segredo do servidor). Só o servidor lê e escreve.';
alter table public.escritorio_drive_conexoes enable row level security;
revoke all on public.escritorio_drive_conexoes from anon, authenticated;

create table public.escritorio_drive_permissoes (
  id bigint generated always as identity primary key,
  projeto_id uuid not null references public.escritorio_projetos(id) on delete cascade,
  membro_id uuid references public.escritorio_membros(id) on delete set null,
  email text not null,
  pasta_id text not null,
  permission_id text not null,
  criado_em timestamptz not null default now()
);
comment on table public.escritorio_drive_permissoes is
  'Compartilhamentos da pasta do projeto que o SERVIDOR criou (um por membro ativo). Quem sai perde; o que a admin compartilhou à mão no Drive não passa por aqui.';
create unique index escritorio_drive_permissoes_um on public.escritorio_drive_permissoes (projeto_id, membro_id, pasta_id) where membro_id is not null;
alter table public.escritorio_drive_permissoes enable row level security;
revoke all on public.escritorio_drive_permissoes from anon, authenticated;

-- ── 24. (26/09) CHECKLIST e ETIQUETAS do cartão (Pedro: "o Trello é a referência") ──
-- Mesmo molde de escritorio_tarefa_pessoas/comentarios: a tarefa e o projeto andam JUNTOS na chave
-- estrangeira (tarefa_id, projeto_id) — não dá pra pendurar item de um projeto em tarefa de outro — e
-- quem vê/mexe é quem tem papel no projeto (escritorio_papel). Etiqueta é do PROJETO: criar, renomear e
-- apagar é da admin (dono); marcar/desmarcar numa tarefa é de qualquer um da equipe, como pessoas.
-- Aplicada como `escritorio_checklist_etiquetas`.
create table public.escritorio_checklist (
  id          uuid primary key default gen_random_uuid(),
  tarefa_id   uuid not null,
  projeto_id  uuid not null,
  texto       text not null check (char_length(btrim(texto)) between 1 and 300),
  feito       boolean not null default false,
  posicao     double precision not null default 0,
  criado_por  uuid default auth.uid() references auth.users(id) on delete set null,
  criado_em   timestamptz not null default now(),
  foreign key (tarefa_id, projeto_id) references public.escritorio_tarefas(id, projeto_id) on delete cascade
);
create index escritorio_checklist_tarefa on public.escritorio_checklist (tarefa_id, posicao);

create table public.escritorio_etiquetas (
  id          uuid primary key default gen_random_uuid(),
  projeto_id  uuid not null references public.escritorio_projetos(id) on delete cascade,
  nome        text not null check (char_length(btrim(nome)) between 1 and 40),
  cor         text not null check (cor ~ '^#[0-9A-Fa-f]{6}$'),
  criado_em   timestamptz not null default now(),
  unique (id, projeto_id),
  unique (projeto_id, nome)
);

create table public.escritorio_tarefa_etiquetas (
  tarefa_id   uuid not null,
  etiqueta_id uuid not null,
  projeto_id  uuid not null,
  primary key (tarefa_id, etiqueta_id),
  foreign key (tarefa_id, projeto_id)   references public.escritorio_tarefas(id, projeto_id)   on delete cascade,
  foreign key (etiqueta_id, projeto_id) references public.escritorio_etiquetas(id, projeto_id) on delete cascade
);
create index escritorio_tarefa_etiquetas_etq on public.escritorio_tarefa_etiquetas (etiqueta_id);

alter table public.escritorio_checklist        enable row level security;
alter table public.escritorio_etiquetas        enable row level security;
alter table public.escritorio_tarefa_etiquetas enable row level security;
revoke all on public.escritorio_checklist, public.escritorio_etiquetas, public.escritorio_tarefa_etiquetas from anon;
grant select, insert, update, delete on public.escritorio_checklist, public.escritorio_etiquetas, public.escritorio_tarefa_etiquetas to authenticated;
-- Ensaio em transação desfeita (26/09), projeto de teste: dono vê/cria/marca; trocar a tarefa do item e
-- apontar item pra outro projeto = 42501; estranho vê 0 e é barrado; anon barrado.

create policy escritorio_checklist_ver    on public.escritorio_checklist for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_checklist_criar  on public.escritorio_checklist for insert to authenticated
  with check (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_checklist_editar on public.escritorio_checklist for update to authenticated
  using (public.escritorio_papel(projeto_id) is not null) with check (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_checklist_apagar on public.escritorio_checklist for delete to authenticated
  using (public.escritorio_papel(projeto_id) is not null);

create policy escritorio_etiquetas_ver    on public.escritorio_etiquetas for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_etiquetas_criar  on public.escritorio_etiquetas for insert to authenticated
  with check (public.escritorio_papel(projeto_id) = 'dono');
create policy escritorio_etiquetas_editar on public.escritorio_etiquetas for update to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono') with check (public.escritorio_papel(projeto_id) = 'dono');
create policy escritorio_etiquetas_apagar on public.escritorio_etiquetas for delete to authenticated
  using (public.escritorio_papel(projeto_id) = 'dono');

create policy escritorio_tarefa_etiquetas_ver      on public.escritorio_tarefa_etiquetas for select to authenticated
  using (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_tarefa_etiquetas_marcar   on public.escritorio_tarefa_etiquetas for insert to authenticated
  with check (public.escritorio_papel(projeto_id) is not null);
create policy escritorio_tarefa_etiquetas_desmarcar on public.escritorio_tarefa_etiquetas for delete to authenticated
  using (public.escritorio_papel(projeto_id) is not null);

-- item do checklist: tarefa, projeto, autor e data de criação não mudam depois de criados
create or replace function public.escritorio_checklist_guarda()
returns trigger language plpgsql set search_path to '' as $$
begin
  if public.escritorio_eh_servidor() then return new; end if;
  if tg_op = 'INSERT' then
    new.criado_em := now(); new.criado_por := (select auth.uid());
    return new;
  end if;
  if new.tarefa_id <> old.tarefa_id or new.projeto_id <> old.projeto_id
     or new.criado_por is distinct from old.criado_por or new.criado_em is distinct from old.criado_em then
    raise exception 'tarefa, autor e data do item não mudam' using errcode = '42501';
  end if;
  return new;
end $$;
create trigger escritorio_checklist_guarda before insert or update on public.escritorio_checklist
  for each row execute function public.escritorio_checklist_guarda();

-- etiqueta: não muda de projeto
create or replace function public.escritorio_etiqueta_guarda()
returns trigger language plpgsql set search_path to '' as $$
begin
  if public.escritorio_eh_servidor() then return new; end if;
  if tg_op = 'UPDATE' and new.projeto_id <> old.projeto_id then
    raise exception 'a etiqueta não muda de projeto' using errcode = '42501';
  end if;
  return new;
end $$;
create trigger escritorio_etiquetas_guarda before update on public.escritorio_etiquetas
  for each row execute function public.escritorio_etiqueta_guarda();

-- ── 25. (26/09, auditoria completa do Escritório) o e-mail CONFIRMADO da conta ganha a pasta do Drive ──
-- Antes o compartilhamento usava profiles.email — que a própria pessoa edita pela API (política sem WITH CHECK
-- + UPDATE na coluna). Agora o servidor grava, no aceite, o e-mail confirmado da conta numa coluna que só ele
-- escreve (o gatilho barra qualquer outro), e a sincronização do Drive usa ela.
alter table public.escritorio_membros add column if not exists email_conta text
  check (email_conta is null or (char_length(email_conta) between 3 and 254 and email_conta = lower(email_conta)));
comment on column public.escritorio_membros.email_conta is
  'E-mail confirmado da conta que aceitou o convite (quem recebe a pasta do Drive). Só o servidor escreve.';
-- (não entra no GRANT de SELECT por coluna de authenticated — seção 16: a tela não lê; a admin vê pelo RPC)

create or replace function public.escritorio_membro_guarda()
returns trigger language plpgsql set search_path to '' as $$
begin
  if public.escritorio_eh_servidor() then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  if tg_op = 'DELETE' then
    if old.papel = 'dono'
       and exists (select 1 from public.escritorio_projetos p where p.id = old.projeto_id)
       and public.escritorio_conta_existe(old.user_id) then
      raise exception 'o dono não sai do próprio projeto' using errcode = '42501';
    end if;
    return old;
  end if;
  if old.papel = 'dono' then
    raise exception 'a linha do dono não se edita' using errcode = '42501';
  end if;
  if new.projeto_id <> old.projeto_id or new.papel <> old.papel
     or new.user_id is distinct from old.user_id
     or new.convite_hash is distinct from old.convite_hash
     or new.visto_por is distinct from old.visto_por
     or new.email_conta is distinct from old.email_conta
     or (new.status = 'ativo' and old.status <> 'ativo')
     or (old.status = 'removido' and new.status <> 'removido') then
    raise exception 'só o aceite do convite (servidor) ativa ou liga uma pessoa' using errcode = '42501';
  end if;
  if new.email is distinct from old.email
     or new.convite_expira is distinct from old.convite_expira
     or new.convidado_em is distinct from old.convidado_em
     or new.aceito_em is distinct from old.aceito_em then
    raise exception 'e-mail e datas do convite só mudam por um convite novo' using errcode = '42501';
  end if;
  if new.status = 'removido' and old.status <> 'removido' then new.removido_em := coalesce(new.removido_em, now()); end if;
  return new;
end $$;

-- quem já está ativo hoje: o e-mail confirmado da conta dele (auth.users), uma vez
update public.escritorio_membros m
   set email_conta = lower(u.email)
  from auth.users u
 where u.id = m.user_id and m.status = 'ativo' and m.papel = 'freela'
   and m.email_conta is null and u.email_confirmed_at is not null and u.email is not null;

-- acesso à pasta que a admin JÁ tinha dado à mão: o AI.arq registra, mas nunca tira (nem ao sair do projeto)
alter table public.escritorio_drive_permissoes add column if not exists ja_existia boolean not null default false;

-- a admin vê com qual conta cada pessoa entrou (pode ser outro e-mail que o do convite). Mudar o retorno pede
-- DROP + CREATE: as permissões voltam iguais às de antes (authenticated e service_role; anon e public não).
drop function if exists public.escritorio_contatos(uuid);
create function public.escritorio_contatos(p_projeto uuid)
returns table(membro_id uuid, email text, telefone text, email_conta text)
language sql stable security definer set search_path to '' as $$
  select m.id, m.email, m.telefone, m.email_conta
    from public.escritorio_membros m
   where m.projeto_id = p_projeto
     and public.escritorio_papel(p_projeto) = 'dono'
$$;
revoke all on function public.escritorio_contatos(uuid) from public, anon;
grant execute on function public.escritorio_contatos(uuid) to authenticated, service_role;

-- ── 26. (26/09) PERFIS: cliente e fornecedor (maquete aprovada pelo Pedro, 26/09) ──
-- Antes: quase toda leitura era `escritorio_papel(...) is not null` — quem entrasse no projeto via TUDO.
-- Agora 'freela' continua sendo a EQUIPE e vê o mesmo de antes (o ensaio compara a equipe real antes/depois).
--   fornecedor: só as tarefas marcadas pra ele (move entre A fazer / Em desenvolvimento / Aguardando revisão,
--               marca item do checklist, comenta), as emissões mandadas pra ele e as fotos (sobe pelo servidor).
--   cliente:    só as tarefas "do cliente" ou marcadas pra ele (sem comentários nem checklist), as emissões
--               mandadas pra ele — e RESPONDE (aprova ou pede revisão; fica registrado, ninguém edita nem apaga)
--               — e as fotos marcadas "pro cliente".
--   atas, atividade, etiquetas e a lista da equipe com contato: só a equipe.
--   Nenhum dos dois lê a linha do projeto direto (tem job_id e a pasta do Drive): o resumo vem por
--   escritorio_resumo_externo(). Só o servidor cria cliente/fornecedor, manda emissão e sobe foto (Drive).
-- 26.1 papéis novos e a subpasta do Drive que o fornecedor vê
alter table public.escritorio_membros drop constraint escritorio_membros_papel_check;
alter table public.escritorio_membros add constraint escritorio_membros_papel_check
  check (papel in ('dono','freela','fornecedor','cliente'));
alter table public.escritorio_membros
  add column drive_pasta_id   text check (char_length(drive_pasta_id) <= 200),
  add column drive_pasta_nome text check (char_length(drive_pasta_nome) <= 300);
alter table public.escritorio_membros add constraint escritorio_membros_pasta_so_do_fornecedor
  check ((drive_pasta_id is null and drive_pasta_nome is null) or papel = 'fornecedor');
-- o NOME da pasta aparece na tela; o id fica com o servidor (é ele que dá o acesso no Drive)
grant select (drive_pasta_nome) on public.escritorio_membros to authenticated;
-- a pasta do fornecedor só muda pelo servidor (mudar a pasta = mudar o acesso no Drive)
create or replace function public.escritorio_membro_guarda()
returns trigger language plpgsql set search_path to '' as $$
begin
  if public.escritorio_eh_servidor() then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  if tg_op = 'DELETE' then
    if old.papel = 'dono'
       and exists (select 1 from public.escritorio_projetos p where p.id = old.projeto_id)
       and public.escritorio_conta_existe(old.user_id) then
      raise exception 'o dono não sai do próprio projeto' using errcode = '42501';
    end if;
    return old;
  end if;
  if old.papel = 'dono' then
    raise exception 'a linha do dono não se edita' using errcode = '42501';
  end if;
  if new.projeto_id <> old.projeto_id or new.papel <> old.papel
     or new.user_id is distinct from old.user_id
     or new.convite_hash is distinct from old.convite_hash
     or new.visto_por is distinct from old.visto_por
     or new.email_conta is distinct from old.email_conta
     or new.drive_pasta_id is distinct from old.drive_pasta_id
     or new.drive_pasta_nome is distinct from old.drive_pasta_nome
     or (new.status = 'ativo' and old.status <> 'ativo')
     or (old.status = 'removido' and new.status <> 'removido') then
    raise exception 'só o aceite do convite (servidor) ativa ou liga uma pessoa' using errcode = '42501';
  end if;
  if new.email is distinct from old.email
     or new.convite_expira is distinct from old.convite_expira
     or new.convidado_em is distinct from old.convidado_em
     or new.aceito_em is distinct from old.aceito_em then
    raise exception 'e-mail e datas do convite só mudam por um convite novo' using errcode = '42501';
  end if;
  if new.status = 'removido' and old.status <> 'removido' then new.removido_em := coalesce(new.removido_em, now()); end if;
  return new;
end $$;
-- 26.2 as perguntas das regras. A equipe = a admin (dono) ou quem ela chamou como equipe (freela)
create or replace function public.escritorio_eh_equipe(p_projeto uuid)
returns boolean language sql stable set search_path to '' as $$
  select coalesce(public.escritorio_papel(p_projeto) in ('dono','freela'), false)
$$;
-- esta linha de membro é de quem está logado?
create or replace function public.escritorio_sou_eu(p_membro uuid)
returns boolean language sql stable security definer set search_path to '' as $$
  select exists (select 1 from public.escritorio_membros m
                  where m.id = p_membro and m.user_id = (select auth.uid()) and m.status = 'ativo')
$$;
-- a tarefa aparece pra quem está logado? (fornecedor: marcada pra ele; cliente: "do cliente" ou marcada pra ele)
create or replace function public.escritorio_tarefa_visivel(p_tarefa uuid)
returns boolean language sql stable security definer set search_path to '' as $$
  select coalesce((
    select case public.escritorio_papel(t.projeto_id)
             when 'dono' then true
             when 'freela' then true
             when 'fornecedor' then exists (
               select 1 from public.escritorio_tarefa_pessoas tp
                 join public.escritorio_membros m on m.id = tp.membro_id and m.projeto_id = tp.projeto_id
                where tp.tarefa_id = t.id and m.user_id = (select auth.uid()) and m.status = 'ativo')
             when 'cliente' then t.do_cliente or exists (
               select 1 from public.escritorio_tarefa_pessoas tp
                 join public.escritorio_membros m on m.id = tp.membro_id and m.projeto_id = tp.projeto_id
                where tp.tarefa_id = t.id and m.user_id = (select auth.uid()) and m.status = 'ativo')
             else false end
      from public.escritorio_tarefas t where t.id = p_tarefa), false)
$$;
-- 26.3 pra quem cada emissão foi (o servidor grava junto com o acesso ao ARQUIVO no Drive — nunca a pasta Emitidos)
create table public.escritorio_emissao_destinos (
  emissao_id     uuid not null,
  projeto_id     uuid not null,
  membro_id      uuid not null,
  enviado_em     timestamptz not null default now(),
  enviado_por    uuid references auth.users(id) on delete set null,
  permission_id  text check (char_length(permission_id) <= 200),
  primary key (emissao_id, membro_id),
  foreign key (emissao_id, projeto_id) references public.escritorio_emissoes(id, projeto_id) on delete cascade,
  foreign key (membro_id, projeto_id) references public.escritorio_membros(id, projeto_id) on delete cascade
);
create index escritorio_emissao_destinos_membro on public.escritorio_emissao_destinos (membro_id);
-- a emissão foi mandada pra quem está logado?
create or replace function public.escritorio_emissao_minha(p_emissao uuid)
returns boolean language sql stable security definer set search_path to '' as $$
  select exists (select 1 from public.escritorio_emissao_destinos d
                   join public.escritorio_membros m on m.id = d.membro_id and m.projeto_id = d.projeto_id
                  where d.emissao_id = p_emissao and m.user_id = (select auth.uid()) and m.status = 'ativo'
                    and m.papel in ('cliente','fornecedor'))
$$;
alter table public.escritorio_emissao_destinos enable row level security;
revoke all on public.escritorio_emissao_destinos from anon;
revoke insert, update, delete, truncate on public.escritorio_emissao_destinos from authenticated;
create policy escritorio_emissao_destinos_ver on public.escritorio_emissao_destinos for select to authenticated
  using (public.escritorio_eh_equipe(projeto_id) or public.escritorio_sou_eu(membro_id));
-- a resposta que o cliente deu pelo sistema ("pelo sistema" x "registrado por você")
alter table public.escritorio_emissao_eventos add column pelo_cliente boolean not null default false;
-- o cliente não escolhe a data nem o autor; a resposta dele ninguém edita nem apaga (só some com a emissão)
create or replace function public.escritorio_emissao_evento_guarda()
returns trigger language plpgsql set search_path to '' as $$
begin
  if public.escritorio_eh_servidor() then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  if tg_op = 'DELETE' then
    if old.pelo_cliente then
      raise exception 'a resposta do cliente fica registrada: não se apaga' using errcode = '42501';
    end if;
    return old;
  end if;
  if tg_op = 'INSERT' then
    new.criado_em := now();
    new.pelo_cliente := coalesce(public.escritorio_papel(new.projeto_id) = 'cliente', false);
    if new.pelo_cliente then
      new.registrado_por := (select auth.uid());
      new.em := (now() at time zone 'America/Sao_Paulo')::date;
    end if;
    return new;
  end if;
  if old.pelo_cliente or new.pelo_cliente then
    raise exception 'a resposta do cliente fica registrada: não se edita' using errcode = '42501';
  end if;
  return new;
end $$;
revoke all on function public.escritorio_emissao_evento_guarda() from public, anon, authenticated;
create trigger escritorio_emissao_eventos_guarda before insert or update or delete on public.escritorio_emissao_eventos
  for each row execute function public.escritorio_emissao_evento_guarda();
create policy escritorio_emissao_eventos_cliente_responde on public.escritorio_emissao_eventos for insert to authenticated
  with check (public.escritorio_papel(projeto_id) = 'cliente' and public.escritorio_emissao_minha(emissao_id)
              and tipo in ('aprovado','revisao') and registrado_por = (select auth.uid()));
-- 26.4 fotos: o arquivo mora na pasta Fotos do Drive; aqui só legenda, etapa, data e "pro cliente"
create table public.escritorio_fotos (
  id             uuid primary key default gen_random_uuid(),
  projeto_id     uuid not null references public.escritorio_projetos(id) on delete cascade,
  drive_file_id  text not null check (char_length(drive_file_id) between 1 and 200),
  legenda        text check (char_length(legenda) <= 200),
  etapa          text check (char_length(etapa) <= 80),
  pro_cliente    boolean not null default false,
  enviada_por    uuid references auth.users(id) on delete set null,
  enviada_em     timestamptz not null default now(),
  unique (id, projeto_id),
  unique (projeto_id, drive_file_id)
);
create index escritorio_fotos_projeto on public.escritorio_fotos (projeto_id, enviada_em desc);
alter table public.escritorio_fotos enable row level security;
revoke all on public.escritorio_fotos from anon;
-- subir e apagar passa pelo servidor (o arquivo do Drive vai junto)
revoke insert, delete, truncate on public.escritorio_fotos from authenticated;
create policy escritorio_fotos_ver on public.escritorio_fotos for select to authenticated
  using (public.escritorio_papel(projeto_id) in ('dono','freela','fornecedor')
         or (public.escritorio_papel(projeto_id) = 'cliente' and pro_cliente));
create policy escritorio_fotos_editar on public.escritorio_fotos for update to authenticated
  using (public.escritorio_eh_equipe(projeto_id)
         or (enviada_por = (select auth.uid()) and public.escritorio_papel(projeto_id) = 'fornecedor'))
  with check (public.escritorio_papel(projeto_id) in ('dono','freela','fornecedor'));
-- o fornecedor edita a legenda da foto dele, mas "pro cliente" é decisão da equipe
create or replace function public.escritorio_foto_guarda()
returns trigger language plpgsql set search_path to '' as $$
begin
  if public.escritorio_eh_servidor() then return new; end if;
  if new.projeto_id <> old.projeto_id or new.drive_file_id <> old.drive_file_id
     or new.enviada_por is distinct from old.enviada_por or new.enviada_em is distinct from old.enviada_em then
    raise exception 'a foto não muda de projeto, arquivo, autor nem data' using errcode = '42501';
  end if;
  if new.pro_cliente is distinct from old.pro_cliente and not public.escritorio_eh_equipe(new.projeto_id) then
    raise exception 'só a equipe decide o que o cliente vê' using errcode = '42501';
  end if;
  return new;
end $$;
revoke all on function public.escritorio_foto_guarda() from public, anon, authenticated;
create trigger escritorio_fotos_guarda before update on public.escritorio_fotos
  for each row execute function public.escritorio_foto_guarda();
-- 26.5 cliente e fornecedor não leem escritorio_projetos (job_id, pasta): o resumo vem por aqui, só dos projetos dele
create or replace function public.escritorio_resumo_externo(p_projeto uuid default null)
returns table (projeto_id uuid, nome text, escritorio text, papel text, etapas text[], etapa_atual text,
               inicio date, entrega date, proxima_entrega text, proxima_entrega_data date)
language sql stable security definer set search_path to '' as $$
  select p.id, p.nome,
         (select d.nome from public.escritorio_membros d where d.projeto_id = p.id and d.papel = 'dono' limit 1),
         m.papel, p.etapas, p.etapa_atual, p.inicio, p.entrega, p.proxima_entrega, p.proxima_entrega_data
    from public.escritorio_membros m
    join public.escritorio_projetos p on p.id = m.projeto_id
   where m.user_id = (select auth.uid()) and m.status = 'ativo' and m.papel in ('cliente','fornecedor')
     and (p_projeto is null or p.id = p_projeto)
$$;
revoke all on function public.escritorio_eh_equipe(uuid) from public, anon;
grant execute on function public.escritorio_eh_equipe(uuid) to authenticated, service_role;
revoke all on function public.escritorio_sou_eu(uuid) from public, anon;
grant execute on function public.escritorio_sou_eu(uuid) to authenticated, service_role;
revoke all on function public.escritorio_tarefa_visivel(uuid) from public, anon;
grant execute on function public.escritorio_tarefa_visivel(uuid) to authenticated, service_role;
revoke all on function public.escritorio_emissao_minha(uuid) from public, anon;
grant execute on function public.escritorio_emissao_minha(uuid) to authenticated, service_role;
revoke all on function public.escritorio_resumo_externo(uuid) from public, anon;
grant execute on function public.escritorio_resumo_externo(uuid) to authenticated, service_role;
-- 26.6 as regras que eram "is not null". Projeto: só o dono e a equipe leem a linha
alter policy escritorio_projetos_ver on public.escritorio_projetos
  using (dono = (select auth.uid()) or public.escritorio_eh_equipe(id));
-- membros: a equipe vê quem está ativo (como antes); cliente/fornecedor veem a si e a equipe do escritório — não um ao outro
alter policy escritorio_membros_ver on public.escritorio_membros
  using (public.escritorio_papel(projeto_id) = 'dono'
         or (public.escritorio_papel(projeto_id) = 'freela' and status = 'ativo')
         or (public.escritorio_papel(projeto_id) in ('fornecedor','cliente')
             and (user_id = (select auth.uid()) or (status = 'ativo' and papel in ('dono','freela')))));
alter policy escritorio_membros_editar on public.escritorio_membros
  with check (public.escritorio_papel(projeto_id) = 'dono' and papel <> 'dono');
alter policy escritorio_membros_apagar on public.escritorio_membros
  using (public.escritorio_papel(projeto_id) = 'dono' and papel <> 'dono' and status <> 'ativo');
-- atas e atividade: só a equipe
alter policy escritorio_atas_ver on public.escritorio_atas using (public.escritorio_eh_equipe(projeto_id));
alter policy escritorio_atas_criar on public.escritorio_atas with check (public.escritorio_eh_equipe(projeto_id) and criado_por = (select auth.uid()));
alter policy escritorio_atas_editar on public.escritorio_atas
  using (public.escritorio_papel(projeto_id) = 'dono' or (criado_por = (select auth.uid()) and public.escritorio_eh_equipe(projeto_id))) with check (public.escritorio_eh_equipe(projeto_id));
alter policy escritorio_atas_apagar on public.escritorio_atas
  using (public.escritorio_papel(projeto_id) = 'dono' or (criado_por = (select auth.uid()) and public.escritorio_eh_equipe(projeto_id)));
alter policy escritorio_atividade_ver on public.escritorio_atividade using (public.escritorio_eh_equipe(projeto_id));
-- tarefas
alter policy escritorio_tarefas_ver on public.escritorio_tarefas
  using (public.escritorio_eh_equipe(projeto_id) or public.escritorio_tarefa_visivel(id));
alter policy escritorio_tarefas_criar on public.escritorio_tarefas with check (public.escritorio_eh_equipe(projeto_id) and criado_por = (select auth.uid()));
alter policy escritorio_tarefas_editar on public.escritorio_tarefas
  using (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(id)))
  with check (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(id)));
alter policy escritorio_tarefas_apagar on public.escritorio_tarefas
  using (public.escritorio_papel(projeto_id) = 'dono' or (criado_por = (select auth.uid()) and public.escritorio_eh_equipe(projeto_id)));
-- quem está marcado: a equipe vê tudo; os de fora, só a própria marcação
alter policy escritorio_tarefa_pessoas_ver on public.escritorio_tarefa_pessoas
  using (public.escritorio_eh_equipe(projeto_id) or public.escritorio_sou_eu(membro_id));
alter policy escritorio_tarefa_pessoas_marcar on public.escritorio_tarefa_pessoas with check (public.escritorio_eh_equipe(projeto_id));
alter policy escritorio_tarefa_pessoas_desmarcar on public.escritorio_tarefa_pessoas using (public.escritorio_eh_equipe(projeto_id));
-- comentários: a equipe; o fornecedor nas tarefas dele; o cliente não
alter policy escritorio_comentarios_ver on public.escritorio_comentarios using (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(tarefa_id)));
alter policy escritorio_comentarios_criar on public.escritorio_comentarios
  with check ((public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(tarefa_id))) and autor = (select auth.uid()));
alter policy escritorio_comentarios_editar on public.escritorio_comentarios
  using (autor = (select auth.uid()) and (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(tarefa_id)))) with check (autor = (select auth.uid()) and (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(tarefa_id))));
alter policy escritorio_comentarios_apagar on public.escritorio_comentarios
  using (public.escritorio_papel(projeto_id) = 'dono' or (autor = (select auth.uid()) and (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(tarefa_id)))));
-- checklist: a equipe; o fornecedor vê e marca "feito" nas tarefas dele
alter policy escritorio_checklist_ver on public.escritorio_checklist using (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(tarefa_id)));
alter policy escritorio_checklist_criar on public.escritorio_checklist with check (public.escritorio_eh_equipe(projeto_id));
alter policy escritorio_checklist_editar on public.escritorio_checklist using (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(tarefa_id))) with check (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'fornecedor' and public.escritorio_tarefa_visivel(tarefa_id)));
alter policy escritorio_checklist_apagar on public.escritorio_checklist using (public.escritorio_eh_equipe(projeto_id));
-- etiquetas: só a equipe
alter policy escritorio_etiquetas_ver on public.escritorio_etiquetas using (public.escritorio_eh_equipe(projeto_id));
alter policy escritorio_tarefa_etiquetas_ver on public.escritorio_tarefa_etiquetas using (public.escritorio_eh_equipe(projeto_id));
alter policy escritorio_tarefa_etiquetas_marcar on public.escritorio_tarefa_etiquetas with check (public.escritorio_eh_equipe(projeto_id));
alter policy escritorio_tarefa_etiquetas_desmarcar on public.escritorio_tarefa_etiquetas using (public.escritorio_eh_equipe(projeto_id));
-- emissões: a equipe todas; os de fora só as mandadas pra eles
alter policy escritorio_emissoes_ver on public.escritorio_emissoes
  using (public.escritorio_eh_equipe(projeto_id) or public.escritorio_emissao_minha(id));
-- o histórico de respostas: a equipe e o cliente a quem a emissão foi (o fornecedor não vê a conversa com o cliente)
alter policy escritorio_emissao_eventos_ver on public.escritorio_emissao_eventos
  using (public.escritorio_eh_equipe(projeto_id) or (public.escritorio_papel(projeto_id) = 'cliente' and public.escritorio_emissao_minha(emissao_id)));
-- 26.7 o fornecedor só MOVE a tarefa dele (mesma esteira da equipe); o cliente não mexe em tarefa
create or replace function public.escritorio_tarefa_guarda()
returns trigger language plpgsql set search_path to '' as $$
declare v_papel text;
begin
  if tg_op = 'UPDATE' then
    if new.projeto_id <> old.projeto_id then
      raise exception 'tarefa não muda de projeto' using errcode = '42501';
    end if;
    new.atualizado_em := now();
    if new.status is distinct from old.status then new.status_mudou_em := now();
    else new.status_mudou_em := old.status_mudou_em; end if;
  end if;
  if new.status in ('revsol','cliente','aprov','ok') then new.passou_pela_admin := true;
  elsif tg_op = 'UPDATE' then new.passou_pela_admin := new.passou_pela_admin or old.passou_pela_admin; end if;
  if public.escritorio_eh_servidor() then return new; end if;
  if tg_op = 'INSERT' then
    new.criado_em := now(); new.atualizado_em := now(); new.status_mudou_em := now();
    new.passou_pela_admin := new.status in ('revsol','cliente','aprov','ok');
  else
    if new.criado_por is distinct from old.criado_por or new.criado_em is distinct from old.criado_em then
      raise exception 'autoria e data de criação da tarefa não mudam' using errcode = '42501';
    end if;
    new.passou_pela_admin := old.passou_pela_admin or new.status in ('revsol','cliente','aprov','ok');
  end if;
  v_papel := public.escritorio_papel(new.projeto_id);
  if v_papel = 'dono' then return new; end if;
  if v_papel = 'fornecedor' then
    if tg_op = 'INSERT' then
      raise exception 'o fornecedor não cria tarefa' using errcode = '42501';
    end if;
    if (new.titulo, new.descricao, new.etapa, new.prazo, new.do_cliente, new.ata_id)
       is distinct from (old.titulo, old.descricao, old.etapa, old.prazo, old.do_cliente, old.ata_id) then
      raise exception 'o fornecedor só move a tarefa' using errcode = '42501';
    end if;
  elsif v_papel is distinct from 'freela' then
    raise exception 'só a equipe mexe nas tarefas' using errcode = '42501';
  end if;
  if tg_op = 'INSERT' then
    if not (new.status in ('afazer','dev','revdtz') or (new.do_cliente and new.status = 'cliente')) then
      raise exception 'freela cria tarefa em A fazer, Em desenvolvimento ou Aguardando revisão DTZ' using errcode = '42501';
    end if;
  elsif new.status is distinct from old.status then
    if old.status not in ('afazer','dev','revdtz','revsol') or new.status not in ('afazer','dev','revdtz') then
      raise exception 'daqui pra frente quem move é a dona do projeto' using errcode = '42501';
    end if;
  end if;
  return new;
end $$;
-- o fornecedor só marca o item como feito
create or replace function public.escritorio_checklist_guarda()
returns trigger language plpgsql set search_path to '' as $$
begin
  if public.escritorio_eh_servidor() then return new; end if;
  if tg_op = 'INSERT' then
    new.criado_em := now(); new.criado_por := (select auth.uid());
    return new;
  end if;
  if new.tarefa_id <> old.tarefa_id or new.projeto_id <> old.projeto_id
     or new.criado_por is distinct from old.criado_por or new.criado_em is distinct from old.criado_em then
    raise exception 'tarefa, autor e data do item não mudam' using errcode = '42501';
  end if;
  if public.escritorio_papel(new.projeto_id) = 'fornecedor'
     and (new.texto is distinct from old.texto or new.posicao is distinct from old.posicao) then
    raise exception 'o fornecedor só marca o item como feito' using errcode = '42501';
  end if;
  return new;
end $$;

-- ── 27. (27/09, board do Escritório) o registro do Drive não some com acesso pendente ──
-- APLICADA em 27/09/2026 como `escritorio_board_acesso_pendente_e_papel_antes` (ok do Pedro: "pode aplicar").
-- 1) SRV-1: quando a pessoa JÁ tinha um acesso menor à pasta (dado à mão pela admin) e o AI.arq promove, guarda o
--    papel de antes — na saída o servidor DEVOLVE esse papel em vez de apagar o acesso dela. null = nós criamos.
alter table public.escritorio_drive_permissoes add column if not exists papel_antes text;
alter table public.escritorio_drive_permissoes drop constraint if exists escritorio_drive_permissoes_papel_antes_chk;
alter table public.escritorio_drive_permissoes add constraint escritorio_drive_permissoes_papel_antes_chk
  check (papel_antes is null or papel_antes in ('reader', 'commenter', 'writer'));

-- 2) SEG-2: quem saiu e voltou (com outro perfil ou não) não vê as emissões antigas como "Aguardando você" — só as
--    que ainda estão compartilhadas com ele no Drive (permission_id preenchido).
create or replace function public.escritorio_emissao_minha(p_emissao uuid)
 returns boolean
 language sql
 stable security definer
 set search_path to ''
as $function$
  select exists (select 1 from public.escritorio_emissao_destinos d
                   join public.escritorio_membros m on m.id = d.membro_id and m.projeto_id = d.projeto_id
                  where d.emissao_id = p_emissao and m.user_id = (select auth.uid()) and m.status = 'ativo'
                    and m.papel in ('cliente','fornecedor') and d.permission_id is not null)
$function$;

-- 3) SEG-1/REG-1: apagar PROJETO só pela rota do servidor (ela tira os acessos do Drive ANTES e não apaga com
--    pendência). A política direta deixava a cascata levar o registro do que ainda estava compartilhado.
drop policy if exists escritorio_projetos_apagar on public.escritorio_projetos;

-- 4) SEG-1/REG-4: "Apagar dados" de quem saiu, ou apagar uma emissão, com o arquivo emitido AINDA compartilhado no
--    Drive → o banco recusa (a cascata levaria o único registro, e a faxina horária nunca mais tiraria o acesso).
--    O servidor (e a cascata que ele dispara) passa: ele revoga antes. 🔑 SEM security definer — senão o
--    current_user vira o dono da função e escritorio_eh_servidor() liberaria todo mundo.
create or replace function public.escritorio_acesso_pendente_guarda()
 returns trigger
 language plpgsql
 set search_path to ''
as $function$
begin
  if public.escritorio_eh_servidor() then
    return old;
  end if;
  if tg_table_name = 'escritorio_membros' then
    if exists (select 1 from public.escritorio_emissao_destinos d
                where d.membro_id = old.id and d.projeto_id = old.projeto_id and d.permission_id is not null) then
      raise exception 'ainda falta tirar no Google Drive o acesso desta pessoa aos arquivos emitidos (o AI.arq tenta de novo a cada hora); apague os dados depois'
        using errcode = '42501';
    end if;
  elsif exists (select 1 from public.escritorio_emissao_destinos d
                 where d.emissao_id = old.id and d.permission_id is not null) then
    raise exception 'esta emissão ainda está compartilhada no Google Drive com quem recebeu'
      using errcode = '42501';
  end if;
  return old;
end $function$;

drop trigger if exists escritorio_membros_acesso_pendente on public.escritorio_membros;
create trigger escritorio_membros_acesso_pendente before delete on public.escritorio_membros
  for each row execute function public.escritorio_acesso_pendente_guarda();
drop trigger if exists escritorio_emissoes_acesso_pendente on public.escritorio_emissoes;
create trigger escritorio_emissoes_acesso_pendente before delete on public.escritorio_emissoes
  for each row execute function public.escritorio_acesso_pendente_guarda();
