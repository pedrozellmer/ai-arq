# -*- coding: utf-8 -*-
"""
Pre-commit secret scanner pro AI.arq.

Roda como hook PreToolUse antes de qualquer comando Bash que faça `git commit`.
Bloqueia o commit se detectar secrets nos arquivos staged.

Detecta:
- Anthropic API key (sk-ant-...)
- Meta access token (EAA + 50+ chars)
- Stripe keys (sk_live_, sk_test_, pk_live_, pk_test_, rk_live_, etc.)
- Supabase service_role JWT (eyJhbGc...com role:service_role)
- AWS access key (AKIA + 16 chars)
- Generic 'PRIVATE KEY' blocks
- .env files acidentalmente staged

Uso:
  python .claude/hooks/scan_secrets.py

Retorna:
  exit 0 = OK, pode commitar
  exit 1 = secret detectado, commit bloqueado
"""
import json
import re
import subprocess
import sys


# Padrões de secret reais (não strings tipo 'EXAMPLE' ou placeholders)
SECRET_PATTERNS = [
    (r'sk-ant-[a-zA-Z0-9_-]{50,}',      'Anthropic API key'),
    (r'EAA[A-Za-z0-9]{50,}',            'Meta (Facebook/Instagram) access token'),
    (r'sk_live_[a-zA-Z0-9]{20,}',       'Stripe secret key (LIVE)'),
    (r'sk_test_[a-zA-Z0-9]{20,}',       'Stripe secret key (test)'),
    (r'rk_live_[a-zA-Z0-9]{20,}',       'Stripe restricted key (LIVE)'),
    (r'AKIA[0-9A-Z]{16}',               'AWS access key ID'),
    (r'-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----', 'Private key block'),
    (r'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{40,}',
     'JWT token (verifique se não é service_role)'),
    (r'github_pat_[A-Za-z0-9_]{50,}',   'GitHub Personal Access Token'),
    (r'ghp_[A-Za-z0-9]{36}',            'GitHub PAT (legacy)'),
    (r'glpat-[A-Za-z0-9_-]{20,}',       'GitLab PAT'),
    (r'AIza[0-9A-Za-z_-]{35}',          'Google API key'),
]

# Arquivos que NUNCA devem ser commitados
FORBIDDEN_FILES = [
    r'\.env$',
    r'\.env\.[^.]+$',  # .env.local, .env.production
    r'backend/\.env$',
    r'secrets\.json$',
    r'credentials\.json$',
    r'.*\.pem$',
    r'.*\.key$',
    r'api\.txt$',
    r'api_keys\.txt$',
]

# Allowlist: arquivos onde patterns parecidos podem aparecer legitimamente
# (ex: .env.example com placeholder)
ALLOWLIST_FILES = [
    r'\.env\.example$',
    r'\.gitignore$',
    r'CLAUDE\.md$',           # docs podem mencionar formato
    r'\.claude/hooks/scan_secrets\.py$',  # esse próprio arquivo (tem regex)
    r'.*test_.*\.py$',
    r'.*\.test\.(js|py)$',
]


def get_staged_files():
    """Retorna lista de arquivos staged pra commit."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'],
            capture_output=True, text=True, encoding='utf-8'
        )
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        return []


def get_staged_diff(filename):
    """Retorna diff staged de um arquivo específico (só linhas adicionadas)."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--', filename],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        if result.returncode != 0:
            return ''
        # Pega só linhas que começam com '+' (adições), exceto cabeçalho
        added = [
            line[1:] for line in result.stdout.splitlines()
            if line.startswith('+') and not line.startswith('+++')
        ]
        return '\n'.join(added)
    except Exception:
        return ''


def is_allowlisted(filename):
    return any(re.search(pat, filename) for pat in ALLOWLIST_FILES)


def is_forbidden(filename):
    return any(re.search(pat, filename) for pat in FORBIDDEN_FILES)


def main():
    staged = get_staged_files()
    if not staged:
        # Nada staged — provavelmente não é commit
        sys.exit(0)

    issues = []

    # 1. Arquivos proibidos
    for f in staged:
        if is_forbidden(f) and not is_allowlisted(f):
            issues.append((f, 'arquivo proibido — NÃO commite arquivo de secrets'))

    # 2. Conteúdo dos arquivos
    for f in staged:
        if is_allowlisted(f):
            continue
        if is_forbidden(f):
            continue  # já reportado acima
        try:
            content = get_staged_diff(f)
        except Exception:
            continue
        if not content:
            continue
        for pattern, label in SECRET_PATTERNS:
            for match in re.finditer(pattern, content):
                snippet = match.group(0)
                masked = snippet[:8] + '***' + snippet[-4:] if len(snippet) > 14 else '***'
                issues.append((f, f'{label}: {masked}'))

    if issues:
        print('\n🚨 PRE-COMMIT BLOQUEADO — secrets detectados:\n', file=sys.stderr)
        for f, msg in issues:
            print(f'  ❌ {f}\n     → {msg}\n', file=sys.stderr)
        print('Pra resolver:', file=sys.stderr)
        print('  1. Remova o secret do arquivo (use variável de ambiente)', file=sys.stderr)
        print('  2. Faça unstage: git reset HEAD <arquivo>', file=sys.stderr)
        print('  3. Rote o secret expostos imediatamente (gere chave nova)', file=sys.stderr)
        print('  4. Tente commit de novo', file=sys.stderr)
        print('\nSe é falso-positivo, adicione o arquivo em ALLOWLIST_FILES de scan_secrets.py.\n', file=sys.stderr)
        sys.exit(2)  # PreToolUse: exit 2 bloqueia o tool

    sys.exit(0)


if __name__ == '__main__':
    main()
