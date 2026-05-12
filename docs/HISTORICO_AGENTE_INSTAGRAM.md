# Histórico — Criação do Agente Instagram AI.arq

**Data:** 14/04/2026
**Sessão:** Configuração completa do agente Instagram para @ai.arq.br

---

## O que foi feito

### 1. Arquivos criados no backend/

| Arquivo | Função |
|---------|--------|
| `instagram_api.py` | Cliente da Meta Graph API (enviar DMs, publicar posts, renovar token) |
| `instagram_store.py` | Persistência em JSON (conversas, config, logs, deduplicação) |
| `instagram_agent.py` | IA com Claude — system prompts para DMs e geração de conteúdo |
| `instagram_webhook.py` | 10 endpoints FastAPI + auto-poster (desativado por padrão) |
| `instagram_image.py` | Gerador de imagens para posts (fotos Unsplash + Montserrat) |
| `assets/fonts/` | Fontes Montserrat (Bold, SemiBold, Medium, Regular, Light) |
| `assets/photos/` | 5 fotos de arquitetura do Unsplash (workspace, interior, building, blueprint, office) |

### 2. Arquivos modificados

| Arquivo | Mudança |
|---------|---------|
| `backend/main.py` | Adicionado `app.include_router(instagram_router)` |
| `backend/requirements.txt` | Adicionado `httpx==0.27.0` |
| `backend/.env` | Adicionadas variáveis META_APP_SECRET, META_ACCESS_TOKEN, META_VERIFY_TOKEN, IG_USER_ID, BACKEND_URL |

### 3. Endpoints criados

| Método | Rota | Função |
|--------|------|--------|
| GET | `/api/instagram/webhook` | Verificação do webhook do Meta (hub.challenge) |
| POST | `/api/instagram/webhook` | Recebe DMs do Instagram |
| POST | `/api/instagram/post` | Gera e publica um post com IA |
| GET | `/api/instagram/image/{filename}` | Serve imagens geradas |
| GET | `/api/instagram/status` | Status do agente |
| POST | `/api/instagram/toggle` | Liga/desliga agente |
| GET | `/api/instagram/conversations` | Lista conversas de DM |
| GET | `/api/instagram/conversations/{id}` | Histórico de uma conversa |
| GET | `/api/instagram/activity` | Log de atividade |
| GET | `/api/instagram/posts` | Posts publicados |

### 4. Templates de imagem disponíveis

- `generate_how_it_works()` — "Como Funciona" com 3 passos
- `generate_features_post()` — Lista de funcionalidades
- `generate_promo_post()` — Post promocional/institucional
- `generate_stat_post()` — Número/estatística em destaque
- `generate_tip_post()` — Dica de arquitetura
- `generate_pricing_post()` — Tabela de preços (não usar por enquanto)

### 5. Temas de conteúdo pré-definidos

30 temas rotativos em `instagram_agent.py > CONTENT_THEMES`:
- Dicas de arquitetura (revestimentos, pisos, forros, iluminação, acústica, etc.)
- Divulgação da AI.arq (como funciona, o que extrai, velocidade)
- Educação sobre orçamento (SINAPI, TCPO, quantitativos, disciplinas)
- Estatísticas (números de reformas, desperdício, itens identificados)
- Curiosidades (história do concreto, evolução do design)

---

## Configuração no Meta Developer Console

- **App:** AI.arq-IG (ID: 1421819986294553)
- **Conta Instagram:** ai.arq.br (ID: 17841427729064017)
- **Permissões:** instagram_business_basic, instagram_manage_comments, instagram_business_manage_messages
- **Webhook URL:** `https://ai-arq.onrender.com/api/instagram/webhook`
- **Verify Token:** `aiarq_ig_verify_2024`
- **Token de acesso:** Gerado em 14/04/2026 (expira em ~60 dias)
- **Assinatura webhook:** Ativada
- **Campos assinados:** messages, messaging_postbacks, comments, message_reactions, messaging_seen, messaging_referral

---

## Variáveis de ambiente no Render

| Variável | Descrição |
|----------|-----------|
| `ANTHROPIC_API_KEY` | Chave da API do Claude (já existia) |
| `STRIPE_SECRET_KEY` | Chave do Stripe (já existia) |
| `META_APP_SECRET` | Chave secreta do app Instagram |
| `META_ACCESS_TOKEN` | Token de acesso (expira em ~60 dias, renovar antes de 13/06/2026) |
| `META_VERIFY_TOKEN` | Token de verificação do webhook: `aiarq_ig_verify_2024` |
| `IG_USER_ID` | ID da conta Instagram: `17841427729064017` |
| `BACKEND_URL` | `https://ai-arq.onrender.com` |

---

## Commits realizados

1. `c6b4148` — Agente Instagram AI.arq: DMs automáticas + posts com IA (7 arquivos, +1495 linhas)
2. `22f9b7f` — Imagens Instagram profissionais: fotos Unsplash + Montserrat + overlay (11 arquivos)
3. `4c34e2d` — Desativar agente Instagram por padrão — nada roda sem ativação manual

---

## Estado atual (14/04/2026)

- **Agente:** DESATIVADO (tudo desligado por padrão)
- **Auto-poster:** DESATIVADO e removido do startup
- **DMs automáticas:** DESATIVADAS
- **Webhook:** Configurado e verificado (funciona, mas agente ignora mensagens quando desativado)
- **Imagens:** Gerador funcional mas qualidade precisa melhorar para padrão profissional de Instagram

---

## Pendências / Próximos passos

1. **Melhorar imagens** — As geradas por código ficaram amadoras. Ideal: criar no Canva/Figma e usar o agente só para legendas
2. **Revisar posts antes de publicar** — Nunca publicar automaticamente sem aprovação
3. **Solicitar App Review no Meta** — App em modo de desenvolvimento, só testadores interagem
4. **Renovar token** — META_ACCESS_TOKEN expira em ~60 dias (antes de 13/06/2026)
5. **Deletar post ruim** — O primeiro post automático que saiu com imagem de baixa qualidade

---

## Como ligar/desligar o agente

```bash
# Ligar tudo
curl -X POST "https://ai-arq.onrender.com/api/instagram/toggle" \
  -H "Content-Type: application/json" \
  -d '{"agent_enabled": true, "auto_reply_enabled": true, "auto_post_enabled": true}'

# Desligar tudo
curl -X POST "https://ai-arq.onrender.com/api/instagram/toggle" \
  -H "Content-Type: application/json" \
  -d '{"agent_enabled": false, "auto_reply_enabled": false, "auto_post_enabled": false}'

# Ver status
curl "https://ai-arq.onrender.com/api/instagram/status"

# Publicar um post manualmente
curl -X POST "https://ai-arq.onrender.com/api/instagram/post" \
  -H "Content-Type: application/json" \
  -d '{"topic": "Dica sobre pisos para áreas de alto tráfego"}'
```
