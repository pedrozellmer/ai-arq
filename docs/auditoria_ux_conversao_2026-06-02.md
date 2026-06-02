# Auditoria UX/Conversão — ai.arq.br

**Data:** 2026-06-02
**Versão:** v0.5.0 · Beta · ~8 usuários
**Escopo:** funil completo visitante → 1º projeto → projeto pago → cashback → cronograma → comparativo
**Método:** leitura linha-a-linha dos 11 HTMLs principais + JS críticos (toast, onboarding-tour). Sem rodar nada no navegador — auditoria estática.

---

## Resumo executivo

O produto tem **UX surpreendentemente boa pra um beta de v0.5**: hero focado, microcópia em PT-BR coloquial, mensagens de loading temáticas ("Pegando a trena e medindo paredes…"), toast acessível, empty states com CTA, breadcrumb, e disclaimer de "não precificar" repetido nos lugares certos. Mas o funil tem **3 buracos sérios de conversão e 2 regressões silenciosas** que vão minar o crescimento: (1) onboarding-tour ainda fala "VERDE" e "R$0,10/item" — mente sobre o produto na primeira impressão; (2) `visualizar-prancha.html` e botões "Abrir" de PDF em `projeto.html` repetem o bug Daniela (auth não chega ao backend); (3) o fluxo de retorno do Stripe pede pro usuário "subir os arquivos de novo" — perde a intenção do clique original. Sem isso, o produto tá pronto pra escalar.

**Nota geral do funil: 7.2 / 10**

---

## Top 5 fricções de conversão (priorizadas por impacto × esforço)

### 1. 🔴 Onboarding-tour conta o produto errado pro novo usuário
- **Onde:** `onboarding-tour.js:38`
- **Problema:** texto do step 3 fala "Itens em VERDE foram medidos do CAD" e "cada item validado vira R$0,10 de cashback (até R$20)". Os dois estão errados desde 2026-05-13:
  - O sistema usa **BRANCO** pra medido, **LARANJA** pra estimado, não VERDE (regra dura nº 1 do produto).
  - Cashback por item foi eliminado em 2026-05-13. Hoje é **R$30 planilha revisada + R$10/cotação cap 3 = R$60 max**.
- **Impacto:** primeira tela educativa do produto mente. Quando o usuário abre a planilha e vê branco/laranja em vez de verde/laranja, percebe inconsistência → confiança cai antes mesmo de processar o 1º projeto. Pior: o usuário tenta revisar item por item esperando R$0,10 cada, não vê o crédito, sente que foi enganado.
- **Fix sugerido:** reescrever step 3 do tour pra refletir a verdade atual (ver "Top 10 microcópias").
- **Prioridade:** 🚨 P0 — corrige hoje.

### 2. 🔴 Bug Daniela voltou em PDFs do projeto + visualizar-prancha
- **Onde:**
  - `projeto.html:1514, 1530` — botão "Abrir" do PDF usa `<a href="${API_BASE}/api/sheet/..." target="_blank">`.
  - `visualizar-prancha.html:53-55` — `<iframe src="...">` carrega o PDF protegido.
- **Problema:** mesma armadilha conhecida (CLAUDE.md item 9): `<a href>`, `window.open()`, `<iframe src>` NÃO enviam o header `Authorization`. Resultado: o backend retorna 401 e o usuário vê um PDF cinza/erro ao tentar abrir uma prancha.
- **Impacto:** **mata o caso de uso "abro a prancha em nova aba pra medir enquanto reviso"** — que é exatamente o que o produto promete em vários lugares (index.html, dashboard "Todo plano inclui"). Para a Daniela específico, esse caminho é o mais usado, então é regressão direta sobre a usuária mais ativa.
- **Fix sugerido:** ou (a) trocar pra `downloadProtected()` que já existe no projeto.html, ou (b) fazer o endpoint `/api/sheet` aceitar token via query string `?token=...` assinado curto (5min). Opção (a) é mais rápida.
- **Prioridade:** 🚨 P0 — corrige hoje.

### 3. 🟠 Retorno do Stripe pede pra "subir os arquivos de novo"
- **Onde:** `dashboard.html:2169-2178`. Após pagamento aprovado, mostra toast `"Pagamento aprovado! Envie as pranchas novamente para processar."` e zera o estado.
- **Problema:** o usuário acabou de pagar R$97/157/247 numa intenção clara (subir o projeto Y). Quando volta, é tratado como recém-chegado. Tem que arrastar tudo de novo, escolher tipologia de novo, digitar nome de novo. Em mobile, isso é fricção fatal.
- **Impacto:** taxa de abandono pós-pagamento. Usuário desiste OU pede reembolso achando que pagou em vão.
- **Fix sugerido:** salvar `selectedFiles` (nomes + metadados + tipologia + nome) no `localStorage` ou Supabase antes do redirect. Na volta, **disparar `startProcessing()` automaticamente** com base no que foi salvo. O arquivo binário em si fica no IndexedDB do navegador (já que `File` não serializa) — ou: subir os arquivos pro backend ANTES do checkout e só liberar o processing após confirmação. Implementação 2 é mais robusta.
- **Prioridade:** 🟠 P1 — corrige em até 7 dias.

### 4. 🟠 CTA "Comece Grátis" não é grátis — vai pro login.html, não cadastro
- **Onde:** `index.html:70, 95, 580`, `precos.html:165`. Todos os "Comece Grátis" levam pra `login.html`, que mostra "Faça login com sua conta Google **para começar**" — texto sugere que precisa ter conta.
- **Problema:** o link "Não tem conta? Cadastre-se" no login.html é um pequeno texto cinza depois do botão Google. Em mobile, fica abaixo da dobra. Usuário que clica "Comece Grátis" esperando um onboarding chega numa tela que parece pedir credenciais que ele não tem.
- **Impacto:** drop entre landing → cadastro. Especialmente para tráfego do Instagram (onde o user veio justamente pra "testar").
- **Fix sugerido:** ou (a) mudar landing CTAs pra `login.html#signup` e abrir o login.html já em modo cadastro; ou (b) criar `cadastro-rapido.html` com só "email + Google" sem fricção. Opção (a) é mais barata.
- **Prioridade:** 🟠 P1.

### 5. 🟡 Cadastro de 8 campos quebra promessa de "1 minuto pra começar"
- **Onde:** `cadastro.html:58-191`.
- **Problema:** o form pede 8 perguntas (nome, whatsapp, CPF/CNPJ opcional, empresa, área, cargo, "como nos conheceu", código beta). Em mobile, é um scroll longo só de inputs. Mesmo com CPF opcional, são 7 campos obrigatórios antes do dashboard.
- **Impacto:** quem aceitou criar conta cansa antes de chegar no produto. Especialmente arquitetos não-tech.
- **Fix sugerido:** dividir em 2 etapas. Etapa 1 (essencial): nome + WhatsApp + cargo (3 campos). Etapa 2 (depois do 1º projeto pronto, dentro do dashboard): empresa, área, como conheceu, código beta. Manter draft no localStorage como já tá.
- **Prioridade:** 🟡 P2 — depois de validar com 20+ usuários.

---

## 🟢 5 acertos (manter e replicar)

1. **Hero focado no wedge** — H1 "Levantamento de quantitativos da sua prancha em minutos, não em dias" + chips "Também faz: comparativo / PPT / cronograma" embaixo. Não dilui a promessa central. Mantém a regra dura do hero (decisão 2026-05-24).

2. **Mensagens de loading temáticas** — "Pegando a trena e medindo paredes…", "Contando luminárias no teto com o facho da lanterna…", "Folheando cada camada do seu projeto…". 12 mensagens rotativas por fase. Humaniza a espera de 2-5min e disfarça quando o Render dorme. Excelente.

3. **Aviso explícito "Acordando o motor"** — `dashboard.html:2300`. Detecta que o Render free-tier dormiu e fala em PT-BR coloquial em vez de fazer a barra ficar travada em silêncio. Tratamento de degradação raro pra v0.5.

4. **Toast acessível com cor + ícone + texto** — `toast.js`. Verde + ✓, vermelho + ✗, âmbar + ⚠, azul + ℹ. Border-left de 6px, role aria. Daltonismo respeitado em todo lugar que usa `notify.*`. Plug-and-play vanilla.

5. **Empty states com CTA** — dashboard.html ("Nenhum projeto ainda → Criar Primeiro Projeto"), projetos sem cashback ("Entre num projeto e faça uma revisão"), cronograma sem itens ("Gere a planilha primeiro → Voltar pro projeto"). Cada empty tem caminho de saída.

---

## 🟡 12 problemas de UX / microcópia (cada um com fix)

### P1. `dashboard.html:530` — Mensagem de erro genérica
- **Atual:** "Ocorreu um erro inesperado. Tente novamente."
- **Sugerido:** "Algo travou no processamento. Vou tentar de novo? Se persistir, manda pra gente pelo botão de Reportar problema." (+ link pro contato)

### P2. `dashboard.html:2322` — Erro de polling sem caminho
- **Atual:** "O servidor perdeu a conexão. Por favor, tente novamente."
- **Sugerido:** "O servidor caiu no meio do processamento. Seu projeto pode estar salvo — vai em Meus Projetos pra conferir. Se não aparecer, suba os arquivos de novo." + link pra Meus Projetos.

### P3. `cadastro.html:439` — Validação WhatsApp robótica
- **Atual:** "Por favor, informe um número de WhatsApp válido."
- **Sugerido:** "Esse WhatsApp tá curto. Vai com DDD: (21) 99999-9999."

### P4. `cadastro.html:449` — Erro CPF/CNPJ "lixo no profile"
- **Atual:** "CPF tem 11 dígitos e CNPJ tem 14. Você pode deixar em branco e preencher antes do 1º pagamento."
- **Sugerido:** "Tá faltando dígito. CPF tem 11 (000.000.000-00) e CNPJ tem 14 (00.000.000/0000-00). Ou deixa em branco — só pedimos antes de pagar."

### P5. `login.html:155` — `alert()` em vez de toast
- **Atual:** `alert('Erro ao iniciar login. Tente novamente.');`
- **Problema:** quebra padrão, bloqueia thread, sem aria-live. login.html não importa toast.js.
- **Sugerido:** importar `toast.js`, trocar pra `toast.error('Não rolou o login com Google. Tenta de novo ou usa e-mail/senha logo abaixo.')`.

### P6. `dashboard.html:2177` — Toast pós-pagamento ambíguo
- **Atual:** "Pagamento aprovado! Envie as pranchas novamente para processar."
- **Sugerido:** "Pagamento confirmado ✓ — agora arrasta seus arquivos de novo aqui (vamos resolver isso em breve)." (placeholder até fix P1 do Top 5)

### P7. `revisao.html:25` — `text-decoration: line-through` em item rejeitado + `opacity: 0.6`
- **Problema:** combinação dificulta leitura pra qualquer pessoa, inclusive não-daltônico. Item "removido" precisa ficar visível pra usuário poder reverter.
- **Sugerido:** subir opacity pra 0.8, manter line-through. Adicionar botão "↩ Reverter" inline no row removido.

### P8. `projeto.html:1503` — Mensagem "Nomes de arquivo não disponíveis"
- **Atual:** "Nomes de arquivo não disponíveis pra este projeto."
- **Problema:** dead end. Usuário não sabe por que nem o que fazer.
- **Sugerido:** "Esse projeto foi processado antes de a gente começar a salvar os nomes. Os arquivos originais não voltam, mas a planilha continua disponível pra download e revisão." (com link pra revisão).

### P9. `dashboard.html:584` — Empty state genérico de "Nenhum projeto"
- **Atual:** "Comece enviando suas pranchas!"
- **Problema:** "pranchas" é jargão técnico — usuário novato pensa "prancha de surf?".
- **Sugerido:** "Manda os PDFs ou DWGs do seu projeto pra gerar o primeiro quantitativo. É grátis e leva ~5 minutos."

### P10. `cronograma.html:78` — Link "Voltar pro projeto" como `href="#"`
- **Atual:** `<a id="link-projeto" href="#"`
- **Problema:** o href é setado no JS depois — se o JS quebrar, link vira `#` e leva a lugar nenhum.
- **Sugerido:** default `href="dashboard.html#meus-projetos"` no HTML. JS sobrescreve se for mais específico.

### P11. `dashboard.html:2097` — Microcópia de termos legalese
- **Atual:** "Você precisa aceitar os Termos de Uso e a Política de Privacidade antes de processar."
- **Sugerido:** "Marca a caixinha dos Termos pra liberar o botão." (linka diretamente pro checkbox).

### P12. `projeto.html:489` — "Enviar e ganhar R$ 30" é claro mas botão muito amarelo
- **Visual:** botão `bg-amber-600` chamativo demais ao lado dos outros cinzas/indigo. Compete com CTAs principais.
- **Sugerido:** manter copy, deixar botão `bg-amber-50 text-amber-700 border-amber-300` — alinha com o tier secundário do botão "Reportar problema".

### P13 (bônus). `dashboard.html:3115` — Toast warn pra "selecione projeto"
- **Atual:** "Por favor, selecione o projeto que você está revisando."
- **Sugerido:** "Antes: escolhe pra qual projeto é essa planilha (campo logo acima)." (mais curto, sem "Por favor" formal).

### P14 (bônus). `index.html:101` — Subtexto do hero não explica formato suportado
- **Atual:** "Primeiro projeto grátis, sem cartão. Revisão por arquiteto/engenheiro é sempre necessária."
- **Sugerido:** quebrar em 2 micro-frases visualmente: "Aceita PDF, DWG e DXF. Sem cartão. Revisão por arquiteto/engenheiro sempre necessária."

### P15 (bônus). `cadastro.html:163` — Hint do código beta
- **Atual:** "Tem um código beta? Insira para acesso gratuito"
- **Sugerido:** "Tem um código de convite? Cola aqui pra ganhar projetos grátis." (mais conversacional, beta é jargão de SaaS).

---

## 🚪 Dead ends (telas/estados sem caminho de saída)

1. **`visualizar-prancha.html:51`** — Quando falta `?job_id=` ou `?ref=`, página mostra `<div>Parâmetros ausentes</div>` sem botão de voltar, sem header, sem link pro dashboard. Usuário fica preso. Botão "Fechar" usa `window.close()` que só funciona em janelas abertas via `window.open()`.

2. **`visualizar-prancha.html` quando o PDF 401** — iframe carrega mensagem de erro do backend (texto cru de FastAPI) dentro do frame cinza. Usuário não tem indicação clara do que aconteceu nem como agir.

3. **`dashboard.html:2382-2384`** — `state-error` mostra a mensagem de erro do backend mas o único botão é "Tentar Novamente" (re-tenta o mesmo arquivo que falhou). Não tem "Reportar problema", "Voltar pra Meus Projetos" ou "Falar com a gente".

4. **`projeto.html` quando o status do job é `error`** — A página tenta renderizar tudo mesmo que o projeto não tenha itens. Resulta em "--" em todos os campos sem explicação. Falta um overlay tipo "Esse projeto não foi processado. Quer reprocessar (grátis) ou apagar?"

5. **`cronograma.html:75` (no-items)** — Tem o link "Voltar pro projeto", mas se o usuário chegou direto via URL do PDF/PPT que foi salvo num e-mail, o `back-projeto` href tá em branco até o JS carregar. Veja P10 acima.

6. **Modal CPF (`dashboard.html:961`) quando o usuário fecha sem preencher** — Volta ao botão "Processar" disabilitado momentaneamente, sem feedback. Deveria mostrar um toast tipo "Sem CPF não rola checkout. Marca de novo quando estiver com o documento à mão."

---

## 💬 Top 10 microcópias pra reescrever (PT-BR coloquial pro arquiteto)

| # | Onde | Atual | Sugerido |
|---|---|---|---|
| 1 | `onboarding-tour.js:38` | "Itens em VERDE foram medidos do CAD (confiável). Itens em LARANJA foram estimados (revisar antes de usar). Cada item validado vira R$ 0,10 de cashback (até R$ 20)." | "Itens em **BRANCO** foram medidos do CAD (confia). Itens em **LARANJA** são estimativa da IA (revisa antes de mandar). Você ganha **R$30** subindo a planilha revisada e **R$10** por cotação de fornecedor (até R$60 abatidos no próximo)." |
| 2 | `onboarding-tour.js:38` (CTA do step 5) | "Subir meu CAD agora" | "Bora subir o primeiro projeto" |
| 3 | `dashboard.html:294` | "⚠️ Aviso importante: As planilhas geradas por IA são estimativas e devem ser revisadas por um profissional antes de uso em orçamento." | "⚠️ Lembra: tudo em laranja é palpite da IA, precisa o seu olho profissional. O que tá em branco veio medido do CAD." |
| 4 | `dashboard.html:357` | "Arraste os arquivos do projeto aqui" | "Joga as pranchas aqui (PDF, DWG ou DXF)" |
| 5 | `dashboard.html:399` | "Enviando arquivos..." | "Carregando suas pranchas pro motor..." |
| 6 | `dashboard.html:427` | "Planilha pronta!" | "Sua planilha tá pronta!" |
| 7 | `dashboard.html:584` | "Comece enviando suas pranchas!" | "Manda os PDFs ou DWGs do seu projeto. É grátis e sai em ~5 min." |
| 8 | `dashboard.html:529` | "Erro no processamento" | "Algo travou. Vou te ajudar a desencalhar." |
| 9 | `cronograma.html:114` | "Gerando cronograma..." | "Montando seu cronograma físico-financeiro..." |
| 10 | `revisao.html:117` | "Você pode exportar a qualquer momento — itens não revisados ficam como a IA gerou." | "Pode exportar quando quiser. Os que você não tocou saem como a IA gerou — laranja na planilha." |

---

## 📞 CTAs avaliadas

| CTA | Onde | Funciona? | Sugestão |
|---|---|---|---|
| "Comece Grátis" (hero) | `index.html:70, 95` | 🟡 leva pra login.html que parece pedir senha | A/B: "Comece Grátis (sem cartão)" vs "Quero ver no meu projeto" |
| "Veja como funciona" | `index.html:99` | 🟢 secundário claro, scroll suave pra #como-funciona | manter |
| "Testar Grátis" (CTA bottom) | `index.html:580` | 🟢 cor invertida do hero, funciona | manter |
| "Calculadora de preço" | `index.html:421` | 🟢 link sutil, redireciona pra precos.html | manter |
| "Começar" nos 3 tiers | `index.html:436, 453, 463` | 🟡 3 botões iguais competem entre si — usuário pode travar | A/B: marcar o "Médio" como `primary`, os outros `outline`. Já tá feito visualmente; reforçar verbalmente: "Quero o Médio" vs "Começar com Pequeno". |
| "Salvar e Continuar" (cadastro) | `cadastro.html:189` | 🟢 verbo de baixo compromisso | manter |
| "Processar Projeto" | `dashboard.html:384` | 🟡 verbo seco — não vende o resultado | A/B: "Gerar meu quantitativo" |
| "Baixar .xlsx direto" vs "Revisar no navegador" | `dashboard.html:452-459` | 🟡 dois CTAs do mesmo peso visual após "Planilha pronta" | A/B: tornar "Revisar no navegador" o primary (gera mais engajamento + cashback futuro). Hoje os dois competem. |
| "Reportar problema" | `projeto.html:276` | 🟢 cor laranja secundária, tom amigável "rapidinho" | manter |
| "Reprocessar" | `projeto.html:101` | 🟢 explica o "porquê" (motor atualizado + 1 grátis) | manter |
| "Enviar e ganhar R$ 30" | `projeto.html:489` | 🟢 promessa explícita | manter, mas suavizar visual (ver P12) |

**Sugestões de A/B test prioritárias:**
1. CTA hero: "Comece Grátis" vs "Gerar meu primeiro quantitativo grátis"
2. CTA dashboard pós-upload: "Processar Projeto" vs "Gerar meu quantitativo"
3. Cards de preço: posição visual do "Mais Comum" + reforço verbal no botão

---

## 🛠️ Top 10 patches que Claude consegue aplicar (auto mode)

1. **Reescrever steps 3 e 5 do onboarding-tour.js** com cor correta (BRANCO) e cashback correto (R$30/R$10). Veja microcópia #1 e #2.
2. **Trocar PDF `<a href>` no projeto.html pelo `downloadProtected`** (ou abrir via JS que injeta o token). Veja fricção #2.
3. **Adicionar fallback header + breadcrumb no visualizar-prancha.html** quando faltar params, em vez do `<div>Parâmetros ausentes</div>` solto.
4. **Importar `toast.js` no login.html** e trocar o `alert()` por `toast.error()`.
5. **Setar `href="dashboard.html#meus-projetos"` default no link `#link-projeto`** do cronograma.html.
6. **Substituir mensagens de erro genéricas (P1, P2, P8, P9)** por versões com caminho de saída.
7. **Adicionar botão "Reportar problema" no `#state-error` do dashboard.html** ao lado de "Tentar novamente".
8. **Salvar `selectedFiles` metadata no localStorage** antes do redirect do Stripe e mostrar UI específica no retorno ("Recuperando sua sessão de pagamento — confirma os arquivos abaixo"). Pré-passo do fix completo da fricção #3.
9. **Renomear "Comece Grátis" no nav e hero** pra "Comece Grátis · sem cartão" ou trocar destino pra `login.html#signup`.
10. **Adicionar `<noscript>` em todas as páginas** com mensagem "AI.arq precisa de JavaScript ligado. Liga e atualiza." — hoje quem entra sem JS vê tela em branco.

---

## ❓ Decisões pra Pedro (exige opinião de produto)

### 1. Cadastro: 2 etapas ou 8 campos numa só?
Como tratado em "Fricção #5", o cadastro hoje tem 8 perguntas pré-dashboard. A regra "CPF só antes do pagamento" já foi tomada. **Cabe estender a mesma lógica pra empresa, área, cargo, "como conheceu"?**

- Opção A: manter 8 campos (rico em dados pra calibrar marketing, mas atrito alto).
- Opção B: mover empresa/área/cargo/referral pro pós-1º-projeto (mostra modal "Conta um pouco mais pra gente te ajudar melhor" após a 1ª planilha pronta — momento de maior boa vontade).
- Recomendação minha: **B**. Como tu já decidiste isso pro CPF, faz sentido replicar.

### 2. Fluxo de pagamento: arquivos antes ou depois?
Hoje: usuário sobe arquivos → vê preço → paga Stripe → volta → sobe **de novo** → processa. (Fricção #3.)

- Opção A: salvar metadados no localStorage e tentar usar IndexedDB pra File binário (frágil).
- Opção B: subir arquivos pro backend ANTES do checkout (job em estado `awaiting_payment`). Stripe webhook libera o processing. O Stripe success URL volta direto pra `dashboard.html?job=...` já em estado "Analisando pranchas...".
- Recomendação minha: **B**. Custa 2-3 dias de backend, mas elimina a fricção de vez. Tu segue cobrando só depois do pagamento (webhook é fonte da verdade), e o usuário tem zero re-trabalho.

### 3. Onboarding tour: mexer agora ou substituir por checklist?
O tour de 5 steps em modal escuro funciona, mas tem uma desvantagem: usuário fecha e nunca mais volta. Uma alternativa moderna é um **checklist persistente no dashboard** ("☐ Cadastro completo · ☐ Subir 1º projeto · ☐ Revisar planilha · ☐ Subir cotação"). Acumula em vez de bloquear.

- Opção A: corrigir o texto do tour atual (que mente sobre VERDE/R$0,10) e seguir com ele.
- Opção B: corrigir o texto E adicionar checklist persistente no dashboard como camada complementar.
- Recomendação minha: **A agora (corrige urgente), B daqui 30 dias quando tiver 20+ usuários** pra medir efeito do checklist.

### 4. Calculadora de preço na home: vale o esforço?
O `index.html` linka pra `precos.html` mas a calculadora interativa de slider tá só lá. Pedro listou "Calculadora de preço interativa na landing" em PENDENTES no CLAUDE.md.

- Opção A: copiar a calculadora de precos.html pra dentro de index.html (na seção de preços).
- Opção B: manter como tá, foca a home no produto e deixa precos como destino do clique.
- Recomendação minha: **A**. Slider de pranchas → preço aparece é magia visual que converte. Esforço baixo (já existe o código).

---

## Observações finais (não-blocking)

- **Mobile**: o cadastro de 8 campos é o pior gargalo mobile. Cronograma editor parece desktop-first também — vale teste em 375px.
- **Acessibilidade**: a regra "cor + ícone + texto" foi seguida bem nos badges de status e no toast.js. Único deslize: cronograma usa cores das fases (custom) que podem cair em pares verde↔vermelho dependendo do que o usuário customizar. Garantir que cada fase tenha label textual sempre presente, não só patch de cor.
- **SEO**: bom — schema.org SoftwareApplication, FAQPage, Product/Offer estão no lugar. og-image presente em todas as públicas.
- **Banners "EM BREVE"** (Memorial, Caderno, BDI no projeto.html) — mantêm a expectativa de roadmap sem prometer data. Boa prática.
- **Dashboard sidebar com 8 abas** — tá no limite. Quando entrar Indique-e-ganhe + Notificações vai precisar repensar agrupamento.
