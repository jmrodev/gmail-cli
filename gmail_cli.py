#!/usr/bin/env python3
"""
Gmail CLI — Herramienta integral para consultar, buscar y enviar correos con Gmail.
Combina la API oficial de Google (OAuth2) para lectura y SMTP para envío rápido con adjuntos.
"""
import os
import sys
import json
import base64
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "gmail"
TOKEN_PATH = CONFIG_DIR / "token.json"
CLIENT_SECRET_PATH = CONFIG_DIR / "client_secret.json"
ENV_PATH = CONFIG_DIR / "config.env"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"]

def _load_env():
    paths = [Path.cwd() / ".env", ENV_PATH]
    for p in paths:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

def get_service():
    """Autentica o renueva sesión con Gmail API."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                print(f"❌ Falta el archivo OAuth de Google en {CLIENT_SECRET_PATH}")
                print("   Descargalo desde Google Cloud Console como Desktop App.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def search_emails(query, max_results=15):
    """Busca correos por consulta estilo Gmail."""
    svc = get_service()
    resp = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    msgs = resp.get("messages", [])
    print(f"\n🔍 Resultados para '{query}' ({len(msgs)} encontrados):")
    for m in msgs:
        full = svc.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])}
        print(f"  [{m['id']}] {headers.get('date', '')[:16]} | {headers.get('from', '')[:30]}")
        print(f"      📌 {headers.get('subject', '(Sin asunto)')}")
        print(f"      ↳ {full.get('snippet', '')[:100]}\n")

def read_email(msg_id):
    """Lee el cuerpo completo de un mensaje."""
    svc = get_service()
    full = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])}
    print(f"\n📨 Asunto : {headers.get('subject')}")
    print(f"👤 De     : {headers.get('from')}")
    print(f"📅 Fecha  : {headers.get('date')}")
    print("-" * 60)
    
    def extract_text(payload):
        body = payload.get("body", {})
        if body.get("data"):
            return base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="replace")
        for p in payload.get("parts", []):
            t = extract_text(p)
            if t: return t
        return ""

    body = extract_text(full.get("payload", {}))
    print(body[:4000])

def send_email(to, subject, body, attachment=None):
    """Envía un correo mediante SMTP o Gmail API."""
    user = os.environ.get("EMAIL_SMTP_USER") or os.environ.get("GMAIL_USER")
    pwd = os.environ.get("EMAIL_SMTP_PASS")
    if not user or not pwd:
        print("❌ Faltan EMAIL_SMTP_USER / EMAIL_SMTP_PASS en .env o en ~/.config/gmail/config.env")
        sys.exit(1)

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment and os.path.exists(attachment):
        with open(attachment, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(attachment))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attachment)}"'
        msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls(context=context)
        server.login(user, pwd)
        server.sendmail(user, [to], msg.as_string())
    print(f"✅ Correo enviado con éxito a {to}!")

USAGE = """
Uso: gmail-cli <comando> [args...]

Comandos:
  search     "<query>" [max]            Busca correos (ej. "from:profe is:unread")
  read       <message_id>               Lee el contenido completo de un email
  send       <to> "<subject>" "<body>" [adjunto] Envía un email con o sin archivo adjunto
"""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(0)
    cmd = sys.argv[1].lower()
    if cmd == "search" and len(sys.argv) >= 3:
        search_emails(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 15)
    elif cmd == "read" and len(sys.argv) >= 3:
        read_email(sys.argv[2])
    elif cmd == "send" and len(sys.argv) >= 5:
        att = sys.argv[5] if len(sys.argv) > 5 else None
        send_email(sys.argv[2], sys.argv[3], sys.argv[4], att)
    else:
        print(USAGE)
