# 💰 Cobrança — checklist do "flip-day" (ligar a cobrança)

> **Estado atual (2026-06-17):** BETA GRÁTIS intencional. 1º projeto grátis silencioso; do 2º em diante mostra "ainda é beta, continua grátis" e processa. Ninguém é cobrado. Decisão do Pedro: cobrar só quando o produto estiver confiável + tiver sinal de valor.

## Como está ligado/desligado hoje

- **Frontend:** `dashboard.html` → `const BETA_FREE = true;` (logo antes do `btnProcess` handler). Enquanto `true`, o 2º+ projeto cai no ramo "beta grátis" (toast + processa). Virar `false` faz cair no checkout Stripe que já existe.
- **`isFirstProject()`** (dashboard.html) — corrigido em 2026-06-17: lia a chave errada `aiarq_projects` (nunca escrita) → dava sempre true → tudo grátis. Agora lê `aiarq_project_history` (a real). Mesmo assim é **localStorage = por-navegador, burlável** — só serve pra UX, não é trava de receita.

## 🚨 O que FALTA pra cobrança ser REAL (não burlável) — fazer no flip-day

Hoje o **backend `/api/process` (`process_files`, main.py ~3122) NÃO verifica pagamento** — processa qualquer POST autenticado. A decisão grátis/pago vive só no JS. Pra cobrar de verdade:

1. **Webhook do Stripe** (NÃO existe hoje): criar `POST /api/stripe/webhook` que escuta `checkout.session.completed`, valida a assinatura, e credita um "direito de processar" pro `user_id` (o user_id já vai no metadata da sessão, main.py ~4991). Sem webhook, pagar e processar são fluxos paralelos que nunca se cruzam.
2. **Gate server-side em `process_files`** (antes de criar o job): contar projetos do user no banco (server-truth, não localStorage). Liberar só se: (a) 1º projeto grátis ainda não usado **por-usuário** (flag `free_used` em `profiles` OU contagem server-side), OU (b) beta válido server-side, OU (c) existe um "direito de processar" (do webhook) não consumido. Senão → HTTP 402. **Consumir o direito atomicamente** ao criar o job.
3. **Frontend:** virar `BETA_FREE=false`. O checkout Stripe já está implementado (`/api/checkout` main.py ~4917 + `dashboard.html` ~2173).

### Régua sugerida pra ligar (sinal de que dá pra cobrar sem queimar)
- 3-5 usuários completando projeto de ponta a ponta **sem erro**.
- 1-2 dizendo que a planilha foi útil / pagariam.
- Os erros de estreia (DWG, sobrecarga IA) controlados (ver commits de confiabilidade 16-17/06).

### Peças que JÁ existem (reaproveitar)
- `/api/checkout` (cria sessão Stripe) — main.py ~4917-5036.
- `/api/checkout/verify/{session_id}` — main.py ~5039 (hoje não é gate; pode virar parte da verificação).
- `_consume_credits` (débito de cashback/cupom) — main.py ~4875.
- Gate de reprocessar (REPROCESS_FREE_LIMIT=1) — main.py ~6503/6548: **único gate de cobrança server-side que já funciona hoje**; serve de molde pro gate do processamento inicial.

## Caso que originou tudo
ivaldogss@gmail.com (16/06): usuário comum, sem beta/crédito, fez 3 projetos `done` sem pagar — por causa do bug da chave de localStorage + ausência de gate server-side. Não foi fraude; o caminho normal já era grátis pra todo projeto ≤5 pranchas.
