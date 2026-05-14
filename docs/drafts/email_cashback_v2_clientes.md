# Email pros clientes existentes — Cashback novo (rascunho)

**Status:** ⏳ Aguardando Pedro aprovar tom + disparar manualmente via Supabase Auth ou cliente de email.

**Destinatários:** 8 cadastrados ativos no AI.arq (lista no admin → Cadastros).

**Sugestão de envio:** depois que Pedro fizer o WhatsApp inicial pros 5 inativos — esse email reforça o canal.

---

## Versão 1 — Curto, direto

**Subject:** Cashback do AI.arq mudou: agora vai até R$ 60 por projeto

Olá [primeiro nome do cliente],

Atualizamos as regras de cashback do AI.arq pra simplificar e premiar melhor as ações que mais ajudam:

**Antes:** R$ 0,10 por item revisado + R$ 20 por planilha + R$ 5 por cotação = até R$ 45/projeto
**Agora:** R$ 30 por planilha revisada + R$ 10 por cotação de fornecedor (até 3) = **até R$ 60/projeto**

A revisão direto no site (aprovar/editar/remover itens) deixa de gerar cashback, mas continua treinando a IA pro próximo projeto — suas correções não somem.

Em resumo: **menos cliques pra ganhar mais.**

Vale dar uma olhada no seu próximo projeto. Se tiver dúvida, responde esse email.

[assinatura padrão]

---

## Versão 2 — Mais coloquial, com case

**Subject:** Novidade no cashback — agora dá até R$ 60

Olá [primeiro nome],

Boa semana. Atualizamos como o cashback funciona no AI.arq.

A regra antiga (R$ 0,10 por item) era difícil de chegar no limite — pra ganhar os R$ 20 do bônus inline, precisava revisar 200 itens. Praticamente ninguém chegava lá.

**Nova regra:**
- Sobe a planilha revisada offline → **+R$ 30**
- Cada cotação de fornecedor que você sobe → **+R$ 10** (até 3 cotações = R$ 30 max)
- **Total possível: R$ 60 por projeto**, abatido no próximo

A revisão dentro do site continua, agora só não gera dinheiro — mas suas correções ainda treinam a IA.

Qualquer dúvida, responde aqui.

[assinatura padrão]

---

## Anotações pro Pedro

- Versão 2 é mais alinhada com tom AI.arq (coloquial, honesto sobre o problema antigo)
- **NÃO mencionar:** "decisão do product-strategist", "agente disse X", números privados (8 cadastrados, 3 ativos)
- Disparar via: cliente de email manual (Gmail/Outlook), OU criar template no Supabase Auth + invocar `sb.auth.admin.sendEmail`
- Lista de destinatários: rodar SQL `SELECT email, raw_user_meta_data->>'full_name' as nome FROM auth.users WHERE email != 'zarelalopes@gmail.com'`
