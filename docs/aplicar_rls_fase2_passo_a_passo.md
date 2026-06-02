# 🔒 Aplicar RLS Fase 2 em produção — guia rápido pro Pedro

> Pedro, esse é o passo-a-passo pra fechar o banco AI.arq pra anon (RLS).
> Tempo total estimado: **15-25 min**, dos quais ~10s é o SQL rodando, o resto é smoke test.
> Se algo der errado, rollback é **<30s** (passo 3f).

**Data planejada:** noite de 02/06/2026 (a partir das 23h BRT) ou madrugada de 03/06.
**Versão deste guia:** sessão 2026-06-02.

---

## 1. Pré-requisitos confirmados ✅

Antes de começar, esses pontos JÁ estão prontos. Não precisa fazer nada — só leia pra ficar tranquilo:

- [x] **Backend Render usando `SUPABASE_SERVICE_ROLE_KEY`** — Pedro confirmou que a env var está setada no painel do Render. Sem isso, aplicar as policies quebra criação de projeto, upload, cashback e agente IG.
- [x] **Commits `48ed35a` + `7a260cc` no `main`** — backend já está deployado lendo a service_role key.
- [x] **Migrations escritas em** `docs/migrations_rls_planejadas.sql` — 38 policies, idempotente (tem `DROP POLICY IF EXISTS` antes de cada `CREATE`).
- [x] **SQL de rollback escrito em** `docs/migrations_rls_rollback_2026-06-02.sql` — reverte tudo num único comando.

> ⚠️ Se o arquivo de rollback NÃO existir na pasta `docs/`, **NÃO siga adiante** — me chame (Claude) pra gerar antes.

---

## 2. Janela ideal pra aplicar 🕐

**Madrugada 02h-05h BRT.** Por quê:
- Baixo tráfego (Daniela/Yuri/Wilker/Vinícius/Rafael não trabalham nesse horário).
- Não tem nenhum usuário pagante em fluxo de produção 24/7.
- Se algo travar, dá pra resolver com calma sem cliente esperando.

**Hoje 02/06 a partir das 23h** ou **amanhã 03/06 madrugada** estão liberados.

### Antes de começar, manda no WhatsApp:
> Mensagem sugerida pra grupo de beta-testers (Daniela, Yuri, Wilker):
> *"Pessoal, vou fazer uma manutenção rápida no banco do AI.arq agora à noite. Se algo der erro entre 23h e 1h, tenta de novo em 2min — é só uma janela curta de update. Qualquer coisa me avisa."*

Não precisa avisar pelo site (não tem usuário 24/7).

---

## 3. Passo a passo

### a. Avisar Pedro do beta team ⏱️ 2min

Manda a mensagem sugerida acima no WhatsApp. **Não espera resposta** — só pra deixar gente que pode estar logada sabendo. Se ninguém responder, segue.

### b. Abrir Supabase Dashboard ⏱️ 1min

1. Vai em https://supabase.com/dashboard/project/kqjabzwgbfuivzlcfvvu
2. Menu esquerdo → **SQL Editor**
3. Clica em **+ New Query** (canto superior direito)

### c. Colar o SQL de aplicação ⏱️ 1min

1. Abre o arquivo `C:\Users\admin\Desktop\arq\projeto_arq\docs\migrations_rls_planejadas.sql` no editor de texto (ou me peça pra abrir aqui)
2. **Seleciona tudo** (Ctrl+A)
3. **Copia** (Ctrl+C)
4. **Cola** no SQL Editor do Supabase
5. Confere que apareceu o cabeçalho `-- Migrations RLS planejadas — AI.arq Supabase` no topo

### d. Rodar ⏱️ ~10s

1. Clica no botão **RUN** (canto inferior direito do SQL Editor) — ou `Ctrl+Enter`
2. Aguarda. Pra 38 policies é **menos de 10 segundos**.
3. Resultado esperado: `Success. No rows returned` (ou similar verde). Se aparecer erro vermelho, **vai pro passo 3f (rollback) imediatamente**.

### e. Smoke test imediato ⏱️ 5-7min

Abre https://ai.arq.br **em duas abas**: uma anônima (modo incógnito) e uma logada com sua conta admin (`zarelalopes@gmail.com`).

**Testa os 4 fluxos críticos, nessa ordem:**

| # | Aba | Ação | Esperado |
|---|---|---|---|
| 1 | Logada | Dashboard → **lista projetos** aparece | ✓ Vê seus projetos |
| 2 | Logada | Clica num projeto → **abre detalhe** | ✓ Carrega itens, fornecedores, cashback |
| 3 | Logada | Clica em **Baixar planilha** num projeto qualquer | ✓ Download começa (.xlsx) |
| 4 | Anônima | Vai em https://ai.arq.br → rola até o **form de contato** → preenche + envia | ✓ Mensagem "obrigado, retornaremos" |

**Se TODOS os 4 passarem:** ✅ Aplicação OK, segue pro passo 4.

**Se QUALQUER um falhar:** ⚠️ Vai imediatamente pro passo 3f (rollback). Não tenta debugar agora — reverte primeiro, debuga depois.

### f. ROLLBACK (se precisar) ⏱️ <30s

> Esse passo só é executado se algo deu errado no 3d ou 3e.

1. Volta no **SQL Editor** do Supabase (mesma aba que usou)
2. Clica em **+ New Query** (cria query nova, não sobrescreve a anterior — pra ter histórico)
3. Abre `C:\Users\admin\Desktop\arq\projeto_arq\docs\migrations_rls_rollback_2026-06-02.sql`
4. Copia tudo, cola no Editor
5. Clica **RUN**
6. Roda os 4 smoke tests do passo 3e de novo — agora devem passar
7. Me avisa (Claude) que rolou rollback + qual smoke falhou — vou investigar antes da próxima tentativa

### g. Confirmar sucesso (se 3e passou) ⏱️ 1min

Manda mensagem pro WhatsApp:
> *"Pessoal, manutenção feita. Banco fechado pra anon, tudo continua igual pra vocês. Qualquer estranheza me avisa."*

E me marca aqui (Claude) com:
> *"policies aplicadas, banco fechado pra anon. bora rotacionar a key."*

---

## 4. Próximo passo após aplicação OK 🔑

**Rotacionar a anon key.** A key antiga ainda funciona pra acessar o que policies permitem (basicamente nada de sensível agora), mas se algum bot já capturou ela, melhor invalidar.

### Pedro faz:

1. Supabase Dashboard → **Settings** (engrenagem, canto inferior esquerdo)
2. **API**
3. Procura a seção **Project API keys**
4. Encontra `anon` `public` → botão **Reset** (ou três pontinhos → Reset)
5. Confirma → Supabase gera nova key
6. **COPIA** a nova anon key (vai começar com `eyJhbGc...`)
7. Cola num bloco de notas temporário ou manda direto pra mim aqui no chat

### Claude (eu) faço:

8. Atualizo `aiarq-utils.js` com a nova anon key
9. Commit: `chore: rotaciona supabase anon key pós-RLS Fase 2`
10. Push pro main
11. GitHub Pages republica em ~2min
12. Roda smoke test rápido pra confirmar que o frontend tá lendo a key nova

**Tempo total dessa etapa: ~5min.**

> ⚠️ Não rotaciona a `service_role` key. Essa fica intacta — só Render conhece ela.

---

## 5. Riscos conhecidos ⚠️

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| **Daniela ou outro user tenta baixar planilha durante a janela** | Baixa (madrugada) | Baixo — backend tem retry 3x automático | Avisar no WhatsApp antes. Se acontecer, a primeira tentativa pode dar 500 mas a segunda passa. |
| **Webhook IG dispara durante a janela** | Média (pg_cron roda a cada 15min) | **Zero** — webhook usa `service_role`, bypassa RLS sempre | Nada a fazer. Pode rolar tranquilo. |
| **Cron de scheduler IG (`/api/instagram/scheduler/tick`)** | Alta (15min) | **Zero** — mesma razão, service_role | Nada a fazer. |
| **Stripe webhook recebido** | **Zero** — não existe. Backend só usa Stripe SDK em chamadas outbound (checkout.Session.create / retrieve). Não tem rota `/api/stripe/webhook` em `backend/main.py`. | — | Nada a fazer. |
| **Form de contato anônimo bloqueado** | Média se policy de INSERT não está liberada pra `anon` no `contacts` | Médio — fica 30s sem captar lead até rollback | Smoke #4 cobre isso. Se falhar → rollback. |
| **Smoke #1 (listar projetos) falha** | Baixa — RLS cobre `SELECT` via JOIN com `auth.uid()` | Alto — usuário não vê dashboard | Rollback imediato. |
| **Erro de sintaxe no SQL** | Muito baixa (arquivo testado mentalmente, idempotente) | Médio — SQL não roda, mas também não muda nada | Reler erro, corrigir, rodar de novo. Nada quebra. |

---

## 6. Resumo executivo (pra Pedro reler antes de começar)

1. Abre Supabase SQL Editor
2. Cola `migrations_rls_planejadas.sql` → RUN → espera 10s
3. Smoke (4 testes em 5min) → se algum falhar, cola `migrations_rls_rollback_2026-06-02.sql` → RUN
4. Se passou, me chama pra rotacionar anon key
5. Eu atualizo `aiarq-utils.js` + push → 2min depois tá no ar

**Janela total bloqueada: ~25min.** Risco real: baixo (rollback em 30s, backend já usa service_role, webhooks imunes).

---

**Pedro, qualquer dúvida antes de começar me chama aqui. Quando estiver pronto, é só dizer "vou começar" e eu fico de plantão pra te ajudar com smoke + rotação da key.** 🚀
