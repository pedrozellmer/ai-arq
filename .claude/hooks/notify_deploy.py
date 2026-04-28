# -*- coding: utf-8 -*-
"""
Notificação de deploy — roda após git push pro main.

Verifica se push foi pra main e mostra notificação no terminal com:
- Hash do commit
- O que foi alterado (resumo)
- Link pra ver o site

Pra notificação por Telegram/email, configure variáveis em .claude/settings.local.json:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- (ou) RESEND_API_KEY + EMAIL_TO

Sem essas variáveis, só mostra no terminal local (suficiente pra MVP).

Uso:
  python .claude/hooks/notify_deploy.py
"""
import os
import subprocess
import sys
import json


def get_last_commit():
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--pretty=format:%H|%s|%an|%ar'],
            capture_output=True, text=True, encoding='utf-8'
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split('|', 3)
        if len(parts) != 4:
            return None
        return {
            'hash': parts[0][:8],
            'subject': parts[1],
            'author': parts[2],
            'ago': parts[3],
        }
    except Exception:
        return None


def get_changed_files():
    try:
        result = subprocess.run(
            ['git', 'diff', '--stat', 'HEAD~1', 'HEAD'],
            capture_output=True, text=True, encoding='utf-8'
        )
        return result.stdout.strip().split('\n')[-1] if result.returncode == 0 else ''
    except Exception:
        return ''


def main():
    # Só notifica se o último comando foi push (input do CLAUDE_TOOL_INPUT contém 'git push')
    tool_input = os.environ.get('CLAUDE_TOOL_INPUT', '')
    if 'git push' not in tool_input:
        sys.exit(0)

    commit = get_last_commit()
    if not commit:
        sys.exit(0)

    stats = get_changed_files()

    msg = f"""
🚀 DEPLOY EM ANDAMENTO

Commit: {commit['hash']}
Mensagem: {commit['subject']}
Autor: {commit['author']} ({commit['ago']})
Mudanças: {stats}

⏱️  GitHub Pages publica em ~2min
🔗 https://ai.arq.br
🔗 https://github.com/pedrozellmer/ai-arq/actions (acompanhar)
"""

    print(msg, file=sys.stderr)

    # Notificação externa (se configurada)
    try:
        with open('.claude/settings.local.json', 'r', encoding='utf-8') as f:
            local = json.load(f)
        env = local.get('env', {})

        # Telegram (preferido — push rápido, custo zero)
        token = env.get('TELEGRAM_BOT_TOKEN')
        chat_id = env.get('TELEGRAM_CHAT_ID')
        if token and chat_id:
            import urllib.request, urllib.parse
            api = f'https://api.telegram.org/bot{token}/sendMessage'
            data = urllib.parse.urlencode({
                'chat_id': chat_id,
                'text': f"🚀 AI.arq deploy: {commit['subject']}\n\nCommit: {commit['hash']}\nhttps://ai.arq.br",
                'parse_mode': 'HTML',
            }).encode('utf-8')
            req = urllib.request.Request(api, data=data, method='POST')
            urllib.request.urlopen(req, timeout=5)
            print('  ✓ Telegram notificado', file=sys.stderr)
    except FileNotFoundError:
        pass  # settings.local.json não existe — só mostra no terminal
    except Exception as e:
        print(f'  ⚠️  Falha ao notificar externamente: {e}', file=sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()
