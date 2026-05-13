# 📨 Spec — Indique e Ganhe

> Status: **rascunho pendente aprovação Pedro** · Criado em 2026-05-13
> Origem: recomendação do agent `product-strategist` (sessão Onda 1 dos 9 agentes)

---

## 🎯 Objetivo

Criar loop viral entre arquitetos (pares confiam mais em par que em ad). Meta: gerar **5+ indicações ativas em 30 dias** com custo zero de aquisição.

Calibração com mercado: Vobi (sem programa público), Wise (£50→£50, cap £75), Nubank (5-10% do ticket). A proposta abaixo é 51% do ticket Pequeno — **acima do padrão BR**, mas justificado porque o ticket é baixo (R$97) e indicação entre arquitetos é alta-confiança.

---

## 💰 Estrutura financeira

| Agente | O que ganha | Quando libera |
|---|---|---|
| **Indicador** (quem indicou) | **R$ 50 em crédito** (não cash) | Quando o indicado paga o 1º projeto |
| **Indicado** (quem entrou) | **2º projeto grátis** (não o 1º — já é grátis pra todo mundo) | Disponível assim que pagar o 1º |

**Cap:** 10 indicações por usuário por ano (limita farm sem cortar usuário legítimo).

**Expiração do crédito:** 90 dias (força urgência, libera contabilidade).

**Por que crédito e não cash:** força retorno ao produto. Cliente que ganhou R$ 50 cash some; cliente que ganhou crédito volta pra usar.

**Por que dar 2º grátis ao indicado (não o 1º):** o 1º já é grátis pra todo mundo, então não diferencia. Dar o 2º vale R$97-247 percebidos pelo indicado — incentivo real.

---

## 🛠️ Implementação técnica

### 1. Banco de dados (migration)

```sql
-- Código de indicação único por usuário (gerado na criação da conta)
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS referral_code text UNIQUE;

-- Tabela de indicações
CREATE TABLE IF NOT EXISTS public.referrals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  referrer_user_id text NOT NULL,           -- quem indicou
  referred_user_id text,                    -- quem foi indicado (preenche no cadastro)
  referred_email text,                      -- email no momento da indicação (pra match no cadastro)
  status text DEFAULT 'pending',            -- pending | signed_up | converted | expired
  signed_up_at timestamptz,
  converted_at timestamptz,                 -- quando o indicado pagou 1º projeto
  credit_amount_cents integer DEFAULT 5000, -- R$ 50 pro indicador
  credit_id uuid,                           -- FK pro user_credits após conversão
  created_at timestamptz DEFAULT now()
);

CREATE INDEX idx_referrals_referrer ON referrals(referrer_user_id);
CREATE INDEX idx_referrals_referred ON referrals(referred_user_id);
CREATE INDEX idx_referrals_email ON referrals(referred_email);

-- RLS (igual padrão das outras tabelas com PII)
ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;
```

### 2. Endpoints backend

| Método | Path | Função |
|---|---|---|
| `GET` | `/api/referral/my-code` | Devolve `referral_code` do usuário logado. Gera se não existe |
| `GET` | `/api/referral/my-stats` | `{count_total, count_converted, credits_earned_cents}` |
| `POST` | `/api/referral/track-signup` | Chamado no momento do cadastro: se `?ref=ABC123` na URL, cria referral.pending |
| `GET` | `/api/referral/list` (admin) | Lista todas as indicações pro painel admin |

### 3. Trigger de conversão

Quando o indicado paga o 1º projeto:
- Webhook do Stripe (`/api/stripe/webhook`) checa se o user tem entrada em `referrals` com `referred_user_id` e `status='signed_up'`
- Marca `status='converted'`, cria entrada em `user_credits` (R$50, expires_at=now+90d, source='referral')
- Envia email "🎉 Sua indicação rendeu R$50 de crédito" pro `referrer_user_id`
- Envia email "Você ganhou seu 2º projeto grátis" pro indicado (já tinha cadastrado)

### 4. UI no dashboard

Nova aba "Indique e Ganhe" no menu do avatar (já existe template em `dashboard.html`):

```
┌─────────────────────────────────────────┐
│  📨 Indique e ganhe R$ 50               │
├─────────────────────────────────────────┤
│  Seu link:                              │
│  [ ai.arq.br/?ref=PEDRO2026  ] [Copiar] │
│                                         │
│  Suas indicações:                       │
│  • 3 pessoas usaram seu link            │
│  • 1 já fez o 1º projeto = R$ 50 ✓     │
│  • R$ 50 disponível no seu saldo        │
│                                         │
│  Compartilhe:                           │
│  [WhatsApp]  [LinkedIn]  [Email]        │
└─────────────────────────────────────────┘
```

### 5. UI no cadastro

Se cair em `ai.arq.br/?ref=PEDRO2026`:
- Salva `ref` em sessionStorage
- No formulário de cadastro, mostra: *"🎁 Você foi indicado(a). Ganhe seu 2º projeto grátis ao completar o primeiro pago."*
- Após cadastro completo, POST `/api/referral/track-signup` com o código

### 6. Email transacional

Template novo: "indicacao_convertida" (pro indicador) e "voce_foi_indicado" (pro indicado, ao se cadastrar).

---

## ⚠️ Anti-fraude

1. **Self-referral:** se o email do indicado == email do indicador, descarta
2. **Mesmo CPF/CNPJ:** se tiver, bloqueia
3. **Mesmo IP no mesmo dia:** flag pra admin revisar manualmente
4. **Cap de 10/ano:** limita farm em massa

---

## 📊 Métricas a acompanhar

- `referrals.count_pending` (link clicado mas não cadastrou)
- `referrals.count_signed_up` (cadastrou mas não pagou)
- `referrals.conversion_rate` (signed_up → converted)
- Tempo médio entre indicação e conversão
- Top 5 indicadores

---

## 🚀 Plano de lançamento

1. **Dia 1:** Aplica migration (Supabase) + cria endpoints backend (~2h)
2. **Dia 1:** Cria UI no dashboard + cadastro (~3h)
3. **Dia 2:** Webhook Stripe + emails transacionais (~2h)
4. **Dia 2:** Teste end-to-end (criar 2 contas, fazer fluxo completo)
5. **Dia 2:** Push pra produção + comunicado pros 8 cadastrados atuais (email)
6. **Semana 2-3:** Acompanha métricas, ajusta cap se houver abuso

**Tempo total:** ~7-9h de dev (1 dia de Claude trabalhando direto)

---

## 💡 Variantes consideradas (descartadas)

- **Cash em vez de crédito:** descartado porque cliente que recebe cash some; crédito força retorno
- **% do ticket (10% recurring):** descartado porque AI.arq é pay-as-you-go, não SaaS recorrente
- **Tier escalável (1ª indicação R$30, 2ª R$50, 3ª R$70):** descartado por complexidade — fica pra v2 se virar relevante
- **Indicação em troca de feature beta exclusiva:** ainda não temos features beta exclusivas

---

## ✅ Critério de aprovação

Pedro, antes de implementar, confirme:

1. **R$50 crédito pro indicador / 2º grátis pro indicado** está OK? Ou ajustar valor?
2. **Cap 10/ano** está confortável? Vobi tem ilimitado.
3. **Crédito expira em 90d** OK? Ou prazo diferente?
4. **Disparar email comunicado pros 8 cadastrados** no lançamento?
5. Algum outro detalhe pra refinar antes de mexer no banco?

Responde aqui e eu implemento.
