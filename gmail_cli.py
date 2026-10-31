#!/usr/bin/env python3
"""
Gmail CLI — Herramienta integral basada en la API Oficial de Gmail v1.
Soporta:
  - Búsqueda nativa con operadores Gmail (users.messages.list)
  - Lectura detallada de headers y cuerpo (users.messages.get)
  - Gestión de etiquetas / Labels (users.labels.list / users.messages.modify)
  - Mover a papelera y restaurar (users.messages.trash / users.messages.untrash)
  - Gestión de borradores / Drafts (users.drafts.list / users.drafts.create / users.drafts.send)
  - Envío de correos con formato texto/HTML y adjuntos multipart (users.messages.send / SMTP)
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

SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.labels"
]

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

def list_labels():
    """Lista todas las etiquetas de la cuenta (users.labels.list)."""
    svc = get_service()
    resp = svc.users().labels().list(userId="me").execute()
    labels = resp.get("labels", [])
    print(f"\n🏷️ Etiquetas de Gmail ({len(labels)}):")
    print(f"   {'ID':<25} | {'Nombre':<20} | Tipo")
    print("   " + "-" * 55)
    for l in labels:
        print(f"   {l.get('id'):<25} | {l.get('name'):<20} | {l.get('type')}")
    return labels

def search_emails(query, max_results=15):
    """Busca correos por consulta estilo Gmail."""
    svc = get_service()
    resp = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    msgs = resp.get("messages", [])
    print(f"\n🔍 Resultados para '{query}' ({len(msgs)} encontrados):")
    for m in msgs:
        full = svc.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])}
        labels = ",".join(full.get("labelIds", []))
        print(f"  [{m['id']}] {headers.get('date', '')[:16]} | {headers.get('from', '')[:30]}")
        print(f"      📌 {headers.get('subject', '(Sin asunto)')} [Labels: {labels}]")
        print(f"      ↳ {full.get('snippet', '')[:100]}\n")

def read_email(msg_id):
    """Lee el cuerpo completo de un mensaje."""
    svc = get_service()
    full = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])}
    print(f"\n📨 Asunto : {headers.get('subject')}")
    print(f"👤 De     : {headers.get('from')}")
    print(f"📅 Fecha  : {headers.get('date')}")
    print(f"🏷️ Labels : {', '.join(full.get('labelIds', []))}")
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

def trash_email(msg_id):
    """Mueve un mensaje a la papelera (users.messages.trash)."""
    svc = get_service()
    svc.users().messages().trash(userId="me", id=msg_id).execute()
    print(f"🗑️ Mensaje {msg_id} movido a la papelera.")

def untrash_email(msg_id):
    """Restaura un mensaje de la papelera (users.messages.untrash)."""
    svc = get_service()
    svc.users().messages().untrash(userId="me", id=msg_id).execute()
    print(f"♻️ Mensaje {msg_id} restaurado de la papelera.")

def modify_labels(msg_id, add_labels=None, remove_labels=None):
    """Agrega o quita etiquetas de un mensaje (users.messages.modify)."""
    svc = get_service()
    body = {}
    if add_labels:
        body["addLabelIds"] = [l.strip() for l in add_labels.split(",")]
    if remove_labels:
        body["removeLabelIds"] = [l.strip() for l in remove_labels.split(",")]
    res = svc.users().messages().modify(userId="me", id=msg_id, body=body).execute()
    print(f"✅ Etiquetas actualizadas para {msg_id}: {res.get('labelIds')}")

def list_drafts():
    """Lista todos los borradores guardados (users.drafts.list)."""
    svc = get_service()
    resp = svc.users().drafts().list(userId="me").execute()
    drafts = resp.get("drafts", [])
    print(f"\n📝 Borradores guardados ({len(drafts)}):")
    for d in drafts:
        m = d.get("message", {})
        snippet = m.get("snippet", "(Sin contenido)")
        print(f"  [Draft ID: {d.get('id')}] Mensaje ID: {m.get('id')} ↳ {snippet[:80]}")
    return drafts

def create_draft(to, subject, body):
    """Crea un nuevo borrador en Gmail sin enviarlo (users.drafts.create)."""
    svc = get_service()
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to
    msg["Subject"] = subject
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    draft = svc.users().drafts().create(userId="me", body={"message": {"raw": raw_message}}).execute()
    print(f"✅ Borrador creado con éxito (ID: {draft.get('id')}) para {to}.")
    return draft

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

Búsqueda y Lectura:
  search     "<query>" [max]            Busca correos (ej. "from:profe is:unread")
  read       <message_id>               Lee el contenido completo de un email
  labels                                Lista todas las etiquetas de la cuenta

Borradores (Drafts):
  drafts                                Lista todos los borradores guardados (users.drafts.list)
  draft      <to> "<subject>" "<body>"  Crea un borrador sin enviarlo (users.drafts.create)

Organización y Papelera:
  trash      <message_id>               Mueve un correo a la papelera
  untrash    <message_id>               Recupera un correo de la papelera
  tag        <id> <+LABEL,-LABEL>       Modifica etiquetas (ej: tag 18f... +STARRED,-UNREAD)

Envío:
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
    elif cmd == "labels":
        list_labels()
    elif cmd == "drafts":
        list_drafts()
    elif cmd == "draft" and len(sys.argv) >= 5:
        create_draft(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "trash" and len(sys.argv) >= 3:
        trash_email(sys.argv[2])
    elif cmd == "untrash" and len(sys.argv) >= 3:
        untrash_email(sys.argv[2])
    elif cmd == "tag" and len(sys.argv) >= 4:
        tags = sys.argv[3]
        add = ",".join([t[1:] for t in tags.split(",") if t.startswith("+")])
        rem = ",".join([t[1:] for t in tags.split(",") if t.startswith("-")])
        modify_labels(sys.argv[2], add_labels=add, remove_labels=rem)
    elif cmd == "send" and len(sys.argv) >= 5:
        att = sys.argv[5] if len(sys.argv) > 5 else None
        send_email(sys.argv[2], sys.argv[3], sys.argv[4], att)
    else:
        print(USAGE)
