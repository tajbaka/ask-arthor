from channels.generic.websocket import AsyncWebsocketConsumer
import json
from channels.db import database_sync_to_async
from django.apps import apps

class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """When client connects"""
        # Accept all connections for now
        await self.accept()
        
        # Add to orders group
        await self.channel_layer.group_add("orders", self.channel_name)
        
        # Send current orders
        await self.send_orders()

    async def disconnect(self, close_code):
        """When client disconnects"""
        await self.channel_layer.group_discard("orders", self.channel_name)

    @database_sync_to_async
    def get_orders(self):
        """Get all orders from database"""
        # Get Order model after apps are ready
        Order = apps.get_model('myapp', 'Order')
        orders = Order.objects.all().order_by('-created_at')
        return [{
            'id': order.id,
            'status': order.status,
            'customer_name': order.customer_name,
            'created_at': order.created_at.isoformat(),
            'total_amount': str(order.total_amount),
            'special_instructions': order.special_instructions,
            'item_name': order.item_name,
            'quantity': order.quantity,
            'item_price': str(order.item_price)
        } for order in orders]

    async def orders_update(self, event):
        """Send order updates to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'orders_update',
            'orders': event['orders']
        }))

    async def send_orders(self):
        orders = await self.get_orders()
        await self.send(text_data=json.dumps({
            'type': 'orders_update',
            'orders': orders
        })) 