from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Order
import json

class OrderConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        """When client connects"""
        # Accept all connections for now
        await self.accept()
        
        # Add to orders group
        await self.channel_layer.group_add("orders", self.channel_name)
        
        # Send current orders
        orders = await self.get_orders()
        await self.send_json({
            'type': 'orders_list',
            'orders': orders
        })

    async def disconnect(self, close_code):
        """When client disconnects"""
        await self.channel_layer.group_discard("orders", self.channel_name)

    @database_sync_to_async
    def get_orders(self):
        """Get all orders from database"""
        orders = Order.objects.all().order_by('-created_at')
        return [{
            'id': order.id,
            'status': order.status,
            'customer_name': order.customer_name,
            'created_at': order.created_at.isoformat(),
            'total_amount': str(order.total_amount),
            'special_instructions': order.special_instructions,
            'items': [{
                'item_name': item.item_name,
                'quantity': item.quantity,
                'price': str(item.item_price),
                'special_instructions': item.special_instructions
            } for item in order.items.all()]
        } for order in orders]

    async def orders_update(self, event):
        """Send order updates to WebSocket"""
        await self.send_json(event) 