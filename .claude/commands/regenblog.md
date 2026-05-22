---
description: Regenera todos os HTMLs do blog a partir de blog/posts.json
allowed-tools: Bash(python:*), Read, Bash(cd:*)
---

# /regenblog — Regenera o blog

Roda `python blog/generate.py` pra recriar:
- `blog/index.html` (listagem dos posts)
- `blog/posts/*.html` (12 posts individuais)
- `sitemap.xml` (raiz)
- `robots.txt` (raiz)

## Sequência

```bash
cd "C:/Users/admin/Desktop/arq/projeto_arq/blog" && python generate.py
```

## Validação pós-geração

Confere que:
- 12 posts foram gerados (output deve ter "✅ Total: 12 posts gerados")
- `blog/index.html` existe e foi atualizado
- `sitemap.xml` na raiz contém todas as URLs

Se algum post ficou com encoding errado ou faltou seção, reporte.

## Pós-passos

Lembra ao Pedro:
- Pra ver online, precisa fazer `/deploy` (commit + push)
- Posts futuros (publish_date > hoje) ficam ocultos pro visitante

$ARGUMENTS
