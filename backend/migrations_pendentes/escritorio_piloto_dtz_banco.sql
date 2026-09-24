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
