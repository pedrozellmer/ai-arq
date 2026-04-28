# Stripe MCP — Configuração (TODO)

> Status: NÃO CONFIGURADO ainda. Esse arquivo é o roteiro pra ativar.

## O que é

MCP (Model Context Protocol) server da Stripe permite que o Claude consulte direto:
- Pagamentos recentes
- Customers cadastrados
- Receita por período
- Reembolsos
- Disputas

Útil pra:
- Pedro pedir "quantos pagamentos rolaram esse mês?" e Claude responder na hora
- Análises automáticas no admin
- Tickets de cobrança/suporte

## Como ativar

### 1. Instalar pacote (faz no PC, qualquer um)

```bash
npm install -g @stripe/mcp
```

### 2. Pegar Stripe API key (read-only ideal)

No painel Stripe:
- Settings → API keys
- Cria uma "Restricted key" com permissões SOMENTE LEITURA pra:
  - Charges
  - Customers
  - Invoices
  - Payouts
- Copia a chave (`rk_live_...` se prod, `rk_test_...` se teste)

### 3. Adicionar ao Claude Code

Roda no terminal:

```bash
claude mcp add stripe \
  --command "npx -y @stripe/mcp" \
  --env "STRIPE_API_KEY=rk_live_SUA_CHAVE_AQUI"
```

### 4. Restart Claude Code

Após adicionar, reinicia Claude Code pra ele detectar o novo MCP.

### 5. Testar

No Claude:
> "Quantos pagamentos vieram pelo Stripe nos últimos 7 dias?"

Se Claude consegue responder com dados reais, está funcionando.

## Segurança

⚠️ A chave API ficará na configuração local do Claude (não vai pro git).
⚠️ NUNCA use chave LIVE com permissão de escrita pro MCP.
⚠️ Revoga a chave imediatamente se PC for comprometido.

## Quando vale a pena ativar

Hoje (3 usuários, MRR ~R$0): NÃO. Não tem volume pra justificar a integração.

Quando atingir 30+ usuários ativos OU 10+ pagamentos/mês: SIM.
Aí o overhead de configurar paga (Pedro pergunta status financeiro a qualquer momento).
