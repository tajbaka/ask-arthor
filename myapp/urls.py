from django.urls import path
from . import views

app_name = 'myapp'

urlpatterns = [
    path('', views.home, name='home'),
    path('menu/', views.get_menu, name='get_menu'),
    path('menu/update/', views.update_menu, name='update_menu'),
    path('menu/search/', views.search_menu, name='search_menu'),
    path('vapi/webhook/', views.vapi_webhook, name='vapi_webhook'),
    path('vapi/order/', views.vapi_order_webhook, name='vapi_order_webhook'),
    path('menu/<int:item_id>/', views.delete_menu_item, name='delete_menu_item'),
    path('menu/replace/', views.replace_menu, name='replace_menu'),
    path('orders/', views.get_orders, name='get_orders'),
]