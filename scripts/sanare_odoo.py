"""Shared XML-RPC client for the Sanare Odoo (Odoo 19, sanare.systecgroup.info).

Credentials come from environment variables (never hardcoded in the repo):

    SANARE_ODOO_URL       (default https://sanare.systecgroup.info)
    SANARE_ODOO_DB        (default gxcgtpype1.cloudpepper.site)
    SANARE_ODOO_USER      (default admin)
    SANARE_ODOO_PASSWORD  (required)
"""
import os
import socket
import ssl
import xmlrpc.client

# A hung HTTP connection must not block a script forever (e.g. after a network
# blip) — xmlrpc.client has no timeout of its own.
socket.setdefaulttimeout(60)

URL = os.environ.get("SANARE_ODOO_URL", "https://sanare.systecgroup.info")
DB = os.environ.get("SANARE_ODOO_DB", "gxcgtpype1.cloudpepper.site")
USER = os.environ.get("SANARE_ODOO_USER", "admin")
PW = os.environ.get("SANARE_ODOO_PASSWORD", "")
UID = 2  # admin user id (always 2 in Odoo)


def models():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", context=ctx)


def call(model, method, *args):
    if not PW:
        raise SystemExit("Set SANARE_ODOO_PASSWORD before running this script.")
    return models().execute_kw(DB, UID, PW, model, method, *args)
