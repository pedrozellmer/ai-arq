---
description: Faz commit + push do estado atual do projeto AI.arq
allowed-tools: Bash(git:*), Read
---

# /deploy — Commit + push pra deploy

Você vai fazer um commit e push do estado atual do projeto. Siga esta sequência:

## 1. Status check

```bash
cd "C:/Users/admin/Desktop/arq/projeto_arq" && git status --short
```

Se não tiver nada modificado, avise o Pedro e pare.

## 2. Análise rápida das mudanças

```bash
cd "C:/Users/admin/Desktop/arq/projeto_arq" && git diff --stat
```

Identifica:
- O que foi alterado (frontend, backend, blog, configs)
- Tem arquivo grande/binário inesperado?
- Tem secret no diff? (procura por `sk-ant-`, `EAA`, `eyJhbGc`)

## 3. Stage seletivo

NÃO use `git add -A` cegamente — adiciona arquivos não-desejados.

Em vez disso, adicione SELETIVAMENTE só os arquivos que fazem sentido:
- HTML, JS, Python (código)
- blog/ (se editou conteúdo)
- backend/ (se editou backend)
- .claude/ (se adicionou agent/command/skill/hook)
- CLAUDE.md, ROADMAP.md (se atualizou docs)

Exclua:
- TESTE_*.xlsx, _preview_*.json (outputs locais)
- Pastas de assets que não vão pro deploy

## 4. Mensagem de commit

Formato:
- Linha 1: resumo objetivo (máx 80 chars), começa com tipo (Fix/Add/Refactor/Update/Docs)
- Linha em branco
- Corpo: 1-3 parágrafos explicando o porquê (não o quê)
- Sempre termina com:
  ```
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```

Use HEREDOC pra evitar problemas de aspas:
```bash
git commit -m "$(cat <<'EOF'
Fix: descrição curta

Detalhes do que mudou e por quê.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

## 5. Push

```bash
cd "C:/Users/admin/Desktop/arq/projeto_arq" && git push origin main
```

## 6. Confirma deploy automático

Após push:
- GitHub Pages publica em ~2min
- Render faz deploy do backend em ~3min (se backend foi alterado)

Reporta ao Pedro:
- Commit hash
- O que vai estar no ar e quando
- Link pra testar (geralmente https://ai.arq.br)

$ARGUMENTS
