from django.contrib import admin
from django.urls import path, include
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from myapp.routing import websocket_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('myapp.urls')),
]

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter(websocket_urlpatterns),
})

# Add error handlers
handler404 = 'django.views.defaults.page_not_found'
handler500 = 'django.views.defaults.server_error'
handler403 = 'django.views.defaults.permission_denied'
handler400 = 'django.views.defaults.bad_request'