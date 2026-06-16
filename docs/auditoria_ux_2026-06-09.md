# Re-auditoria UX/Conversão — ai.arq.br

**Data:** 2026-06-09
**Versão:** v0.5.0 · Beta · ~8 usuários
**Escopo:** verificar se os P0/P1 da auditoria de 02/06 (commits e9363fb + a8c989b) foram realmente corrigidos + re-auditar o funil atual
**Método:** leitura estática linha-a-linha dos HTMLs/JS do funil. Não rodei no navegador.

---

## Resumo

Os **4 bugs P0 da auditoria de 02/06 foram TODOS corrigidos de verdade** — onboarding-tour, bug Daniela (projeto.html + visualizar-prancha.html), CTA "Comece Grátis" e toast.js no login. O aviso de PDF vetorial (commit a8c989b) está implementado e correto. O único furo sério que **persiste** é a **fricção #3: retorno do Stripe pede pra subir os arquivos de novo** — era P1, não foi atacado, e o `localStorage.setItem('aiarq_pending_files', ...)` ficou como código morto (escreve, ninguém lê). O funil melhorou bastante; o que sobra é polimento + a decisão estrutural do fluxo de pagamento.

**Nota do funil: 8.3 / 10** (era 7.2 em 02/06)

---

## ✅ Fixes de 02/06 confirmados

### P0 #1 — Onboarding-tour conta a verdade ✅ CORRIGIDO
- **`onboarding-tour.js:38`** — step 3 agora diz **BRANCO** (com styling branco real: `color:#0f172a;background:#f8fafc;border:1px solid #cbd5e1`) e **LARANJA** (`color:#ea580c`). Cashback correto: **R$30** planilha revisada + **R$10** cotação + **até R$60**. Sem "VERDE", sem "R$0,10/item".
- **`onboarding-tour.js:45`** — CTA do step 5 = "Bora subir o primeiro projeto" (microcópia #2 aplicada).
- Bônus: o highlight do BRANCO usa fundo claro + borda (não confia só na palavra), e o LARANJA tem cor + texto. Daltônico-safe.

### P0 #2 — Bug Daniela (auth no download) ✅ CORRIGIDO (3 frentes)
- **`projeto.html:686`** — botão XLSX usa `downloadProtected(...)` via `addEventListener('click')`, com `href=javascript:void(0)` e `removeAttribute('target')`. Comentário no código cita o bug (linha 674-676).
- **`projeto.html:1479-1481`** — botões "Abrir/Baixar" dos arquivos da prancha: PDF → `openPdfProtected(...)`, DWG/DXF → `downloadProtected(...)`, ambos via `onclick` (não `<a href target=_blank>`). Comentário cita "FIX bug Daniela 2026-06-02" (linha 1473).
- **`projeto.html:705-706`** — exports do cronograma (PDF/PPTX) também migrados pra `downloadProtected`.
- **`visualizar-prancha.html:69-92`** — iframe NÃO usa mais `src={endpoint protegido}`. Faz `fetch` com `Authorization: Bearer`, gera `URL.createObjectURL(blob)` e atribui ao iframe. Revoga o blob no `beforeunload` (linha 122-124). Trata 401 com mensagem + link de login (linha 72-74) e erro de rede com link pro dashboard (linha 89).
- Helpers confirmados em **`aiarq-utils.js`**: `downloadProtected` (linha 100), `openPdfProtected` (linha 139).

### P0 #3 — "Comece Grátis" → cadastro.html ✅ CORRIGIDO
- **`index.html:76`** (nav), **`index.html:102`** (hero), **`index.html:443/460/470`** (tiers de preço), **`index.html:587`** (CTA bottom) — todos apontam pra `cadastro.html`. Nenhum "Comece Grátis" cai mais em login.html.
- ⚠️ Ressalva (ver Fricções #1): `cadastro.html:267` redireciona pra `login.html` se não houver sessão Supabase. Como o fluxo real é Google/email OAuth, o visitante novo ainda passa pelo login antes de preencher o cadastro. O destino do link foi corrigido, mas a porta de entrada continua sendo o login.

### P0 #4 — toast.js no login.html ✅ CORRIGIDO
- **`login.html:131`** — `<script src="toast.js" defer></script>` adicionado.
- **`login.html:156-157`** — `alert()` trocado por `window.toast?.error(msg)` com fallback pra `alert`. Microcópia aplicada: "Não rolou o login com Google. Tenta de novo ou usa e-mail/senha logo abaixo."
- `toast.js` tem `warn` (linha 175), `success`, `error`, `info`, todos com cor + ícone + texto (ICONS na linha 98).

### Caso Granado — Aviso PDF vetorial (commit a8c989b) ✅ IMPLEMENTADO e CORRETO
- **`dashboard.html:1872` `checkPdfTextAndWarn(file)`** — roda no `addFiles` (linha 1832) só pra PDFs.
- **`dashboard.html:1853` `loadPdfJs()`** — carrega pdf.js 3.11.174 sob demanda do jsDelivr + worker (linhas 1858-1862). Lazy, só na 1ª vez que entra um PDF.
- Lógica: lê texto das 3 primeiras páginas, se < 150 chars sem whitespace (`PDF_TEXT_THRESHOLD`, linha 1850) → avisa. Não bloqueia upload, só alerta.
- **Mensagem (linha 1890):** clara, daltônico-safe (começa com ⚠ + texto), explica o porquê e a ação: "...parece ser PDF vetorial sem cotas extraíveis (N caracteres lidos). Pra precisão nas divisórias, suba o DWG/DXF original. O quantitativo sai com itens identificados mas com quantidade em branco." Usa `toast.warn(msg, {duration:0})` (fica até fechar).
- Robusto: dedup por nome (`PDF_WARNED_FILES`, linha 1851), fallback se toast ainda não carregou (linha 1895), e `try/catch` que não opina se o PDF estiver corrompido/criptografado (linha 1897-1901).

---

## ⚠️ Fixes que NÃO foram feitos (ou ficaram pela metade)

### 🟠 Fricção #3 (Stripe) — PERSISTE, era P1
- **`dashboard.html:2191-2193`** salva só `selectedFiles.map(f => f.name)` em `localStorage['aiarq_pending_files']`. Objeto `File` não serializa, então só os nomes vão — e **esse valor nunca é lido em lugar nenhum** (grep confirma: 1 write na 2191, 0 reads). É código morto.
- **`dashboard.html:2215`** continua mostrando `notify.ok('Pagamento aprovado! Envie as pranchas novamente para processar.')` e zera o estado. O usuário que pagou R$97-247 volta como recém-chegado e re-arrasta tudo.
- Isso era P1 (corrige em 7 dias) na auditoria de 02/06 e o "pré-passo" sugerido (patch #8) não foi aplicado. Continua sendo o maior buraco do funil. Decisão estrutural ainda pendente (ver "Decisão pra Pedro").

### Observações
- Os P0 críticos (que mentiam/quebravam) foram 100% resolvidos. O que não foi feito é a fricção P1 e uma série de microcópias P2/bônus (a maioria não foi aplicada — ver seção de microcópia).

---

## 🎯 Fricções remanescentes (top 5)

### 1. 🟠 Retorno do Stripe perde o estado (re-upload pós-pagamento)
- **`dashboard.html:2191-2215`.** Detalhado acima. Maior impacto no funil pago. Risco de abandono / pedido de reembolso.

### 2. 🟡 "Comece Grátis" → cadastro → bounce pra login pra quem não tem sessão
- **`cadastro.html:265-269`.** O link foi corrigido pra cadastro.html, mas como cadastro exige sessão Supabase, o visitante novo é jogado pra `login.html` — que diz "Faça login com sua conta Google para começar" (login.html:51), texto que parece pedir credenciais que ele não tem. O fluxo "Comece Grátis" ainda não é um onboarding direto.
- Fix barato: na landing, deixar claro "Entre com Google pra começar (cria conta na hora)" ou abrir o login já em modo cadastro de e-mail.

### 3. 🟡 Cadastro de 8 campos (7 obrigatórios) antes do dashboard
- **`cadastro.html:56-190`.** Nome, WhatsApp, CPF (opcional), empresa, área, cargo, "como conheceu", código beta. Em mobile é scroll longo. Era P2 em 02/06 — decisão de Pedro pendente (Opção B recomendada: mover empresa/área/cargo/referral pro pós-1º-projeto). O auto-save de draft no localStorage (linha 356-410) já está bom e mitiga perda.

### 4. 🟡 Legenda de confiança incompleta na tela de revisão (sistema de 4 cores vira 2)
- **`revisao.html:344, 361-362`.** A revisão só distingue 2 estados: "✓ confirmado" (chip verde) vs "⚠ estimado" (chip âmbar). O sistema canônico do produto tem **4 níveis: BRANCO (medido) / LARANJA (estimado) / CINZA (metadado) / ROXO (indireto)** — CINZA e ROXO não aparecem na UI de revisão.
- Além disso, há **descasamento de vocabulário**: o tour fala "BRANCO = medido", a revisão chama o mesmo item de "confirmado" com chip **verde**. Verde↔vermelho/âmbar é justo o pior par pro daltonismo do Pedro — está mitigado pelos ícones ✓/⚠/✗ (bom), mas a cor verde para o "medido" diverge do BRANCO documentado.
- A "Legenda rápida" (`revisao.html:93-116`) explica botões e atalhos, mas **não explica o sistema de cores de confiança**. Quem nunca leu o tour não tem onde aprender o que branco/laranja/cinza/roxo significam dentro do app.

### 5. 🟡 Dead ends ainda abertos (parcialmente resolvidos)
- **`visualizar-prancha.html:58`** — quando falta `?job_id`/`?ref`, mostra `<div>Parâmetros ausentes</div>` sem header nem link de saída. O caso 401/erro de rede agora TEM link pro dashboard/login (bom), mas o caso de params ausentes continua dead end. Era dead-end #1 em 02/06.
- **`dashboard.html state-error`** — não verifiquei se ganhou botão "Reportar problema" ao lado de "Tentar novamente" (patch #7 de 02/06); vale conferir num próximo passe.

---

## 💬 Microcópias pra reescrever

A maioria das microcópias P-bônus de 02/06 NÃO foi aplicada. As de maior retorno agora:

| Onde | Atual | Sugerido |
|---|---|---|
| `dashboard.html:2215` | "Pagamento aprovado! Envie as pranchas novamente para processar." | "Pagamento confirmado ✓ — arrasta seus arquivos de novo aqui pra processar (tamo trabalhando pra você não precisar repetir isso)." |
| `dashboard.html:435` | "Seu levantamento de quantitativos foi gerado com sucesso." | "Tá pronto! Confere os itens — o que tá em laranja é palpite da IA, revisa antes de mandar pro fornecedor." |
| `revisao.html:115` | "Você pode exportar a qualquer momento — itens não revisados ficam como a IA gerou." | "Pode exportar quando quiser. Os que você não tocou saem como a IA gerou — em laranja na planilha." |
| `login.html:51` | "Faça login com sua conta Google para começar" | "Entre com Google ou e-mail pra começar — se ainda não tem conta, a gente cria na hora." |
| `revisao.html:93-116` (legenda) | só explica botões/atalhos | Adicionar bloco "O que as cores significam": ⬜ Branco = medido do CAD · 🟧 Laranja = estimativa, revisar · ⬛ Cinza = metadado · 🟪 Roxo = indireto. Com ícone + palavra + cor. |

---

## 🛠️ Top patches automáticos (Claude aplica em auto mode)

1. **Stripe — pré-passo do fix #3:** ler `aiarq_pending_files` no retorno (`payment=success`), mostrar UI "Recuperando sua sessão de pagamento — confirma os arquivos abaixo" e pré-selecionar tipologia/nome salvos. Hoje o write é morto. (Fix completo = decisão estrutural abaixo.)
2. **Legenda de cores na revisão:** adicionar bloco de 4 cores (branco/laranja/cinza/roxo) com ícone+texto na "Legenda rápida" do `revisao.html:93`. Resolve o gap de explicação e alinha vocabulário com o tour.
3. **Fallback no visualizar-prancha sem params:** trocar o `<div>Parâmetros ausentes</div>` (linha 58) por mensagem com link pro dashboard (igual já existe pro caso 401).
4. **Microcópia pós-pagamento** (`dashboard.html:2215`) e **planilha pronta** (`dashboard.html:435`) — versões acima.
5. **Cookie consent:** garantir que o banner sticky (bottom:0) não cubra o botão "Salvar e Continuar" do cadastro / "Entrar" do login em telas baixas — hoje ele auto-abre em TODAS as páginas (cookie-consent.js:318-327), inclusive no meio do funil. Sugerir `padding-bottom` no `<main>` quando o banner estiver visível, ou adiar o banner nas páginas de auth até a 1ª interação.

---

## ❓ Decisão pra Pedro

**Fluxo de pagamento: arquivos antes ou depois do checkout?** (re-pergunta de 02/06, ainda não decidida — é o que destrava a única fricção P1 que sobrou)

- **Opção A (barata, frágil):** salvar metadados no localStorage + tentar guardar o binário no IndexedDB. Reduz re-trabalho mas IndexedDB com `File` é instável entre navegadores.
- **Opção B (robusta, ~2-3 dias backend) — recomendada:** subir os arquivos pro backend ANTES do checkout (job em `awaiting_payment`); o webhook do Stripe libera o processamento; a success URL volta pra `dashboard.html?job=...` já "Analisando pranchas...". Zero re-upload, cobrança só após pagamento confirmado (webhook é a fonte da verdade).

Enquanto não decide, vale aplicar o patch #1 (recuperar nomes + ajustar a microcópia) pra pelo menos não tratar quem pagou como recém-chegado.

---

## Observações finais (não-blocking)

- **Acertos mantidos:** mensagens de loading temáticas, "Acordando o motor", toast acessível, empty states com CTA, breadcrumb no projeto.html, disclaimer "não precifica / quem precifica é seu orçamentista" forte no hero (`index.html:99, 110`) e no dashboard (`dashboard.html:299, 818`).
- **Disclaimer ausente na revisão:** `revisao.html` não tem o aviso "não precifica / revisão profissional necessária" visível — só aparece no dashboard e na landing. Como a revisão é onde o usuário decide o que vai pro fornecedor, vale repetir lá.
- **Cookie consent:** bem feito em acessibilidade (role=dialog, ESC=essenciais, cor+ícone+texto, foco gerenciado). Único ponto: auto-abre em páginas de auth/funil — checar sobreposição em mobile (patch #5).
- **Daltonismo:** badges de status (projeto.html), toast, chips de revisão e o aviso de PDF todos seguem cor+ícone+texto. O único deslize é o chip verde para "confirmado/medido" na revisão divergir do BRANCO documentado — mitigado por ícone, mas vale alinhar.
