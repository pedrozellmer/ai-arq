---
description: Verifica se site, backend, blog e Instagram estão no ar e funcionais
allowed-tools: Bash(curl:*), Read
---

# /checksite — Health check do AI.arq

Verifica em paralelo todos os endpoints e serviços críticos. Reporta status agregado.

## Verificações

### 1. GitHub Pages (frontend)

```bash
curl -s -o /dev/null -w "%{http_code}" https://ai.arq.br/
curl -s -o /dev/null -w "%{http_code}" https://ai.arq.br/blog/
curl -s -o /dev/null -w "%{http_code}" https://ai.arq.br/sitemap.xml
curl -s -o /dev/null -w "%{http_code}" https://ai.arq.br/robots.txt
```

Esperado: 200 em todos.

### 2. Render backend

```bash
curl -s -o /dev/null -w "%{http_code}" https://ai-arq.onrender.com/
```

Esperado: 200 (mas se vier 503/504, free tier dormiu — espera 30-60s e tenta de novo).

### 3. Instagram scheduler

```bash
curl -s "https://ai-arq.onrender.com/api/instagram/scheduler/list" | head -50
```

Esperado: JSON com lista de posts agendados, dia1 status="published".

### 4. Supabase (via MCP)

Use `mcp__dbd6b42c-f7dd-4aa9-be26-d2a9422d2c8b__execute_sql` pra rodar:

```sql
select count(*) as profiles, (select count(*) from projects) as projects,
       (select count(*) from contact_messages where status='new') as new_msgs
from profiles;
```

### 5. Posts agendados

Confere que dia1 está como `published` e os 6 restantes como `pending`:

```sql
select slot_key, status from instagram_scheduled_posts order by publish_at;
```

## Output esperado

```
🟢 Site: 200 (https://ai.arq.br)
🟢 Blog: 200 (12 posts)
🟢 Sitemap: 200
🟢 Backend: 200
🟢 IG: 1 published, 6 pending
🟢 DB: X profiles, Y projects, Z mensagens novas

VEREDITO: Tudo no ar ✅
```

ou

```
🔴 Backend: 503 (Render dormiu, tentar de novo em 60s)
🟡 Blog: 200 mas só 11 posts visíveis (esperado 12 se hoje > 26/04)
🟢 Site: 200

VEREDITO: 1 problema crítico (backend)
AÇÃO: aguardar 60s e rerun do /checksite
```

## Quando usar

- Antes de demonstração pro cliente
- Após cada deploy pra validar
- De manhã pra checar se nada quebrou na noite
- Quando Pedro suspeita de problema

$ARGUMENTS
