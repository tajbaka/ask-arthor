"""
ASGI config for mysite project.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
django.setup()  # Set up Django before importing consumers

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path
from myapp.consumers import OrderConsumer

# Initialize Django ASGI application early
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter([
            re_path(r'ws/orders/$', OrderConsumer.as_asgi()),
        ])
    ),
}) 