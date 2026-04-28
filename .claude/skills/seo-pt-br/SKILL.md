---
name: seo-pt-br
description: Gera ou otimiza conteúdo de blog/landing em português brasileiro com foco em SEO orgânico pra arquitetos. Use quando precisar criar post novo do blog, otimizar copy de landing, escrever meta description, ou fazer pesquisa de keywords pra um tema.
---

# SEO PT-BR Content Generator (AI.arq)

Skill pra gerar/otimizar conteúdo SEO em PT-BR no contexto do AI.arq.

## Pra que serve

- Gerar post de blog completo a partir de um tema
- Otimizar copy de landing pra ranquear
- Pesquisar volume e dificuldade de keywords
- Escrever meta description efetiva
- Reescrever post existente pra melhorar SEO

## Workflow recomendado

### 1. Pesquisa de keyword (sempre primeiro)

Antes de escrever, pesquise via WebSearch:
- Volume de busca da keyword principal no Brasil
- Long-tail variations (cauda longa, menos competição)
- Concorrentes que ranqueiam top 3
- Perguntas que gente faz (PAA do Google, "Buscas relacionadas")

### 2. Estrutura SEO ideal

```
# Título (H1) — 50-70 chars, keyword nos primeiros 60 chars
> Meta description: 120-160 chars, com keyword e benefício claro
> Slug: keyword-principal-curto-claro
> Categoria + tags

## Intro (50-100 palavras)
- Hook na primeira frase
- Keyword principal nos primeiros 100 chars
- Promessa clara do que o post entrega

## H2 — primeira seção (sempre keyword variation)
[Conteúdo denso, 200-400 palavras]

## H2 — segunda seção (cobre dúvida do PAA)
...

[Total: 1500-2500 palavras pra ranquear bem]

## CTA final
- Específico pro AI.arq
- Reforça "1º grátis"
- Link pra signup
```

### 3. Densidade e distribuição de keywords

- Keyword principal: 1-2% do total (10-25 ocorrências em 1500 palavras)
- Aparece em: H1, primeiro parágrafo, 1-2 H2s, último parágrafo, meta description
- Long-tail variations distribuídas naturalmente
- LSI keywords (semanticamente relacionadas) ajudam

### 4. Schema.org Article (JSON-LD)

Sempre incluir no <head>:
```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "[título]",
  "description": "[meta description]",
  "datePublished": "2026-XX-XXT10:00:00-03:00",
  "author": {"@type": "Organization", "name": "AI.arq"},
  "publisher": {"@type": "Organization", "name": "AI.arq", "logo": {"@type": "ImageObject", "url": "..."}},
  "image": "https://ai.arq.br/og-image.png",
  "mainEntityOfPage": {"@type": "WebPage", "@id": "url-canonical"}
}
```

### 5. Open Graph + Twitter Cards

```html
<meta property="og:type" content="article">
<meta property="og:title" content="[título]">
<meta property="og:description" content="[descrição]">
<meta property="og:image" content="https://ai.arq.br/og-image.png">
<meta property="og:locale" content="pt_BR">
<meta name="twitter:card" content="summary_large_image">
```

### 6. Linkagem interna

Todo post deve linkar pra:
- Pelo menos 2 posts relacionados do mesmo blog
- A página inicial ou de signup (login.html)
- Página de FAQ se relevante

Anchor text descritivo: "como fazer planilha de quantitativos" > "clique aqui"

### 7. Fontes & Referências (bloco no rodapé)

Cada post deve citar 5-10 fontes em 3 categorias:
- **Normas ABNT** (sem URL, citação por número + descrição)
- **Livros e Manuais** (autor + editora + ano)
- **Web** (links externos com `rel="noopener nofollow"`)

## Tópicos de alto volume pra arquiteto BR

Em ordem de volume estimado mensal:

| Keyword | Volume | Dificuldade |
|---|---|---|
| memorial descritivo de obra | 5.000 | Baixa |
| quanto custa construir uma casa | 8.000 | Alta |
| BDI obra | 3.000 | Baixa |
| planilha de quantitativos de obra | 1.500 | Baixa |
| como pedir cotação fornecedor | 1.200 | Baixa |
| diferença SINAPI TCPO | 800 | Baixa |
| quadro de esquadrias | 800 | Baixa |
| como ler planta arquitetônica | 800 | Baixa |
| quanto cobrar projeto arquitetônico | 700 | Baixa |
| 7 erros levantamento obra | 600 | Baixa |
| diferença orçamento quantitativo | 500 | Muito baixa |
| disciplinas retrofit comercial | 300 | Baixa |
| IA arquitetura 2026 | 700 | Média |

Já cobertos no blog: todos esses (12 posts agendados de 26/04 a 12/07/2026).

## Tópicos pra próxima rodada (5+ ainda não cobertos)

Próximos posts sugeridos pra Semana 2:

1. **"Como calcular preço por m² de obra (com tabela 2026)"** — vol 1.500
2. **"Diferença entre alvenaria estrutural e convencional"** — vol 900
3. **"Como ler quadro de pisos num projeto"** — vol 600
4. **"Memorial descritivo residencial vs comercial"** — vol 500
5. **"O que é cronograma físico-financeiro PFUI Caixa"** — vol 400
6. **"Como fazer compatibilização de projetos"** — vol 400
7. **"Diferença entre vidro temperado e laminado"** — vol 300
8. **"Como ler curva ABC de obra"** — vol 300

## Regras especiais do AI.arq

1. NUNCA prometer "orçamento" ou "preço" — só quantitativo
2. Sempre lembrar: AI.arq não substitui profissional habilitado
3. Foco BR: SINAPI/TCPO/CAU/ABNT, NÃO ferramentas gringas
4. CTA padrão: "Primeiro projeto grátis em ai.arq.br"
5. Tom: técnico mas coloquial ("tô falando", "rola", "bora")
6. Tempo de leitura calculado por palavras / 220 wpm

## Como gerar um post novo

1. WebSearch o tema → coleta 3-5 fontes confiáveis
2. Define estrutura H1 + 7-10 H2s
3. Escreve cada seção com 150-300 palavras
4. Adiciona CTA específico no fim
5. Gera lista de fontes (3 normas ABNT + 3 livros + 4 web)
6. Adiciona ao `blog/posts.json`
7. Roda `python blog/generate.py`
8. Roda subagent `seo-auditor-br` pra validar
9. Commit via `/deploy`

## Como otimizar post existente

1. Lê o post atual em `blog/posts.json`
2. WebSearch atualiza o estado da arte do tema
3. Identifica gaps (faltam dados? exemplos? referências?)
4. Reescreve seções fracas
5. Atualiza estimated_read_min
6. Regenera + audita + commita
