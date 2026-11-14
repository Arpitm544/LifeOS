import ssl
from pathlib import Path

import certifi


def database_ssl_context():
    context = ssl.create_default_context(cafile=certifi.where())
    certificate = Path(__file__).resolve().parents[1] / "supabase-ca.crt"
    if certificate.is_file():
        context.load_verify_locations(cafile=str(certificate))
    return context
