import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client

c = Client(HTTP_HOST="localhost")
r = c.get("/")
html = r.content.decode()
print("status", r.status_code)
print("has select", 'id="niche"' in html)
print("has any-niche", "Any niche" in html)
print("options", html.count("<option"))
