# Post Instagram — Cashback novo (rascunho)

**Status:** ⏳ Aguardando geração do PNG e inserção em `instagram_scheduled_posts`.
**Encaixe na grade:** rubrica "Bastidor de segunda" da semana 21 (18/05/2026 22h).

---

## Caption proposta

```
Atualização nas regras de cashback do AI.arq. 💰

Antes:
• R$ 0,10 por item revisado dentro do site
• R$ 20 por planilha
• R$ 5 por cotação

A real: pra ganhar os R$ 20 inline, tinha que revisar 200 itens. Quase ninguém chegava lá.

Agora:
✓ Sobe a planilha revisada → +R$ 30
✓ Cada cotação de fornecedor → +R$ 10 (até 3)
✓ Total até R$ 60/projeto, abatido no próximo

A revisão direto no site continua — só não vira dinheiro. Suas correções continuam treinando a IA pro próximo projeto.

Menos clique. Mais cashback.

Quer testar? Link na bio. Primeiro projeto grátis.

#arquitetura #quantitativo #orcamentodeobra #AIarq
```

---

## Verificação contra regras duras

- ✅ Voz do cliente — não menciona "motor", "match", "deploy", "X furos de segurança"
- ✅ Sem promessa de preço — só fala de cashback, não calcula obra
- ✅ Sem citar nada interno — não diz "decidimos simplificar", apenas mostra a regra
- ✅ Honesto — admite que a regra antiga era difícil de atingir

---

## Brief pro PNG (1080×1080)

**Layout:** 2 colunas comparando.

**Esquerda (Antes — cinza apagado):**
- Título "Antes" em cinza
- R$ 0,10/item até R$20
- R$ 20 planilha
- R$ 5 cotação
- Total: R$ 45 max

**Direita (Agora — destaque indigo):**
- Título "Agora" em indigo
- R$ 30 planilha revisada
- R$ 10 × até 3 cotações
- Total: **R$ 60** max
- Setinha grande indicando "+33%"

**Fundo:** off-white #FAF7F2
**Tipografia:** Montserrat (Bold no título "Cashback novo", SemiBold nos números)
**Cores AI.arq:** Indigo `#4F46E5` + Cyan `#22D3EE` no acento

---

## Como inserir no banco (quando Pedro OK)

```sql
INSERT INTO instagram_scheduled_posts (slot_key, image_url, caption, publish_at, status, media_type)
VALUES (
  'feed_seg_w21',
  'https://kqjabzwgbfuivzlcfvvu.supabase.co/storage/v1/object/public/instagram-assets/semana_w21/cashback_v2.png',
  '[caption acima]',
  '2026-05-18 22:00:00-03',
  'pending',
  'image'
);
```

(Subir o PNG no bucket `instagram-assets/semana_w21/cashback_v2.png` antes.)
