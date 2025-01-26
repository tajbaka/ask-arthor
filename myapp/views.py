from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import MenuItem, Order, OrderItem
from .utils import get_embedding, find_similar_items
from typing import Dict, List, Any
from django.core.exceptions import ImproperlyConfigured
import logging
import requests
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from openai import OpenAI
from django.conf import settings
from .consumers import OrderConsumer

logger = logging.getLogger(__name__)

def home(request):
    return HttpResponse("Welcome to the homepage!")

def add_menu_item(request):
    # Example item
    item = MenuItem.objects.create(
        name="Margherita Pizza",
        description="Fresh tomatoes, mozzarella, basil",
        price=12.99
    )
    # Get and store embedding
    embedding = get_embedding(f"{item.name} {item.description}")
    item.set_embedding(embedding)
    item.save()
    return JsonResponse({"status": "success"})

def search_menu(request):
    """Search menu items using embeddings"""
    try:
        query = request.GET.get('q', '')
        if not query:
            return JsonResponse({
                "status": "success",
                "found": False,
                "message": "No search query provided",
                "items": []
            })

        similar_items = find_similar_items(query)
        results = [{
            "name": item.name,
            "price": str(item.price),
            "description": item.description,
            "formatted": f"{item.name} (${item.price}) - {item.description}"
        } for item in similar_items]
        
        return JsonResponse({
            "status": "success",
            "found": bool(results),
            "items": results,
            "message": f"Found {len(results)} matching items" if results else "No matching items found"
        })
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return JsonResponse({
            "status": "error",
            "found": False,
            "message": "Search service temporarily unavailable",
            "items": []
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def update_menu(request) -> JsonResponse:
    """Update or create menu items with embeddings"""
    try:
        data: List[Dict[str, Any]] = json.loads(request.body)
        updated_items = []
        
        for item_data in data:
            item, created = MenuItem.objects.update_or_create(
                name=item_data['name'],
                defaults={
                    'description': item_data.get('description', ''),
                    'price': float(item_data['price'])
                }
            )
            
            # Generate and store embedding
            text = f"{item.name} {item.description}"
            embedding = get_embedding(text)
            item.set_embedding(embedding)
            item.save()
            
            updated_items.append({
                'name': item.name,
                'price': str(item.price),
                'description': item.description,
                'status': 'created' if created else 'updated'
            })
        
        return JsonResponse({
            'status': 'success',
            'items': updated_items
        })
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@require_http_methods(["GET"])
def get_menu(request) -> JsonResponse:
    """Get all menu items"""
    items = MenuItem.objects.all()
    menu_items = [{
        'id': item.id,
        'name': item.name,
        'price': str(item.price),
        'description': item.description
    } for item in items]
    
    return JsonResponse({
        'status': 'success',
        'items': menu_items
    })

@csrf_exempt
@require_http_methods(["POST"])
def vapi_webhook(request):
    """Handle VAPI webhook requests - Returns all menu items"""
    try:
        # Log received request
        received = json.loads(request.body)
        
        # Extract tool call ID from the received data
        tool_calls = received.get('message', {}).get('toolCalls', [])
        tool_call_id = tool_calls[0]['id'] if tool_calls else "0dca5b3f-59c3-4236-9784-84e560fb26ef"
        
        try:
            # Get all menu items
            menu_items = MenuItem.objects.all()
            
            if menu_items:
                # Format menu items into sections
                menu_text = "Here's our current menu:\n\n"
                
                # Group by categories if you have them, or just list all items
                menu_text += "\n".join(
                    f"• {item.name} (${item.price})\n  {item.description}"
                    for item in menu_items
                )
                
                menu_text += "\n\nWhat would you like to know more about?"
                response_text = menu_text
            else:
                response_text = "I apologize, but our menu is currently being updated. Please check back soon!"

            response = {
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": response_text,
                    "name": "menu"
                }]
            }
            # logger.info(f"Response: {json.dumps(response)}")
            return JsonResponse(response)
            
        except Exception as e:
            logger.error(f"Menu retrieval failed: {str(e)}")
            response_text = "I'm having trouble accessing our menu right now. Please try again in a moment."
            response = {
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": response_text,
                    "name": "menu"
                }]
            }
            logger.info(f"Error Response: {json.dumps(response)}")
            return JsonResponse(response)
            
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        response = {
            "results": [{
                "toolCallId": "0dca5b3f-59c3-4236-9784-84e560fb26ef",
                "result": "Sorry, I'm having trouble accessing the menu right now.",
                "name": "menu"
            }]
        }
        logger.info(f"Error Response: {json.dumps(response)}")
        return JsonResponse(response)

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_menu_item(request, item_id: int) -> JsonResponse:
    """Delete a menu item by ID"""
    try:
        item = MenuItem.objects.get(id=item_id)
        name = item.name  # Store name before deletion for response
        item.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': f'Successfully deleted menu item: {name}',
            'deleted_id': item_id
        })
    except MenuItem.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': f'Menu item with id {item_id} not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Delete error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@csrf_exempt
@require_http_methods(["POST"])
def replace_menu(request) -> JsonResponse:
    """Replace entire menu with new items"""
    try:
        data: List[Dict[str, Any]] = json.loads(request.body)
        
        # Delete all existing items
        MenuItem.objects.all().delete()
        
        # Create new items
        new_items = []
        for item_data in data:
            item = MenuItem.objects.create(
                name=item_data['name'],
                description=item_data.get('description', ''),
                price=float(item_data['price'])
            )
            
            # Generate and store embedding
            text = f"{item.name} {item.description}"
            embedding = get_embedding(text)
            item.set_embedding(embedding)
            item.save()
            
            new_items.append({
                'id': item.id,
                'name': item.name,
                'price': str(item.price),
                'description': item.description
            })
        
        return JsonResponse({
            'status': 'success',
            'message': f'Menu replaced with {len(new_items)} items',
            'items': new_items
        })
    
    except Exception as e:
        logger.error(f"Replace menu error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

def infer_order_from_conversation(messages) -> tuple[str, int]:
    """Use OpenAI to infer order details from conversations"""
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Format messages for OpenAI
        formatted_messages = [
            {"role": "system", "content": "You are a helpful assistant that extracts order details from conversations. Return ONLY the item name and quantity in format: 'item_name|quantity'. Example: 'Margherita Pizza|1'"},
        ]
        
        # Add conversation history
        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '')
            if role and content:
                formatted_messages.append({"role": role, "content": content})
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=formatted_messages,
            temperature=0
        )
        
        # Parse response
        result = response.choices[0].message.content.strip()
        item_name, quantity = result.split('|')
        return item_name.strip(), int(quantity)
        
    except Exception as e:
        logger.error(f"Error inferring order: {str(e)}")
        return None, 1

def infer_order_changes_from_conversation(messages) -> list:
    """Analyze conversation to infer order changes"""
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Format messages for OpenAI
        formatted_messages = [
            {"role": "system", "content": """You are a helpful assistant that extracts order changes from conversations. 
             Return a JSON array of changes, each with 'action' (add/remove/modify), 'item_name', and 'quantity'.
             Example: [{"action": "add", "item_name": "Margherita Pizza", "quantity": 2}]
             Only return the JSON array, nothing else."""},
        ]
        
        # Add conversation history
        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '')
            if role and content:
                formatted_messages.append({"role": role, "content": content})
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=formatted_messages,
            temperature=0,
            response_format={ "type": "json_object" }
        )
        
        # Parse response
        result = json.loads(response.choices[0].message.content)
        return result.get('changes', [])
        
    except Exception as e:
        logger.error(f"Error inferring order changes: {str(e)}")
        return []

@csrf_exempt
@require_http_methods(["POST"])
def vapi_order_webhook(request):
    """Handle VAPI order webhook requests - Real-time conversation-based ordering"""
    try:
        received = json.loads(request.body)
        logger.info(f"[Order Webhook] Received request: {json.dumps(received, indent=2)}")
        
        messages = received.get('messagesOpenAIFormatted', [])
        logger.info(f"[Order Webhook] Found {len(messages)} messages in conversation")
        
        tool_calls = received.get('message', {}).get('toolCalls', [])
        tool_call_id = tool_calls[0]['id'] if tool_calls else "0dca5b3f-59c3-4236-9784-84e560fb26ef"
        logger.info(f"[Order Webhook] Tool Call ID: {tool_call_id}")
        
        # Get current order or create new one
        function_args = tool_calls[0].get('function', {}).get('arguments', {}) if tool_calls else {}
        logger.info(f"[Order Webhook] Function args: {json.dumps(function_args, indent=2)}")
        
        order_id = function_args.get('order_id')
        order = None
        
        if order_id:
            logger.info(f"[Order Webhook] Attempting to find existing order #{order_id}")
            try:
                order = Order.objects.get(id=order_id)
                logger.info(f"[Order Webhook] Found existing order #{order.id}")
            except Order.DoesNotExist:
                logger.warning(f"[Order Webhook] Order #{order_id} not found")
                order_id = None
        
        if not order:
            logger.info("[Order Webhook] Creating new order")
            order = Order.objects.create(
                customer_name=function_args.get('customer_name', ''),
                special_instructions=function_args.get('special_instructions', '')
            )
            order_id = order.id
            logger.info(f"[Order Webhook] Created new order #{order.id}")
        
        # Analyze conversation to infer order changes
        logger.info("[Order Webhook] Analyzing conversation for order changes")
        inferred_changes = infer_order_changes_from_conversation(messages)
        logger.info(f"[Order Webhook] Inferred changes: {json.dumps(inferred_changes, indent=2)}")
        
        if not inferred_changes:
            logger.info("[Order Webhook] No changes inferred from conversation")
            return JsonResponse({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": "I'm listening. What would you like to order?",
                    "name": "order",
                    "order_id": order_id
                }]
            })
        
        # Process each inferred change
        response_parts = []
        order_updated = False
        
        for change in inferred_changes:
            action = change.get('action')
            item_name = change.get('item_name')
            quantity = change.get('quantity', 1)
            
            logger.info(f"[Order Webhook] Processing change: {action} {quantity}x {item_name}")
            
            if not item_name:
                logger.warning("[Order Webhook] Skipping change - no item name provided")
                continue
                
            # Find matching menu item
            menu_items = MenuItem.objects.filter(name__icontains=item_name.lower())
            if not menu_items:
                logger.info(f"[Order Webhook] No exact match for '{item_name}', trying vector search")
                menu_items = find_similar_items(item_name, threshold=0.8)
            
            if not menu_items:
                logger.warning(f"[Order Webhook] No menu items found matching '{item_name}'")
                response_parts.append(f"I couldn't find '{item_name}' on our menu.")
                continue
            
            item = menu_items[0]
            logger.info(f"[Order Webhook] Found matching item: {item.name} (${item.price})")
            
            if action == 'add':
                existing_item = order.items.filter(menu_item=item).first()
                if existing_item:
                    logger.info(f"[Order Webhook] Updating quantity of existing item {item.name}")
                    existing_item.quantity += quantity
                    existing_item.save()
                    response_parts.append(f"Updated {item.name} quantity to {existing_item.quantity}")
                else:
                    logger.info(f"[Order Webhook] Adding new item {item.name}")
                    OrderItem.objects.create(
                        order=order,
                        menu_item=item,
                        quantity=quantity,
                        item_name=item.name,
                        item_price=item.price
                    )
                    response_parts.append(f"Added {quantity}x {item.name}")
                order_updated = True
                
            elif action == 'remove':
                logger.info(f"[Order Webhook] Removing {item.name} from order")
                removed = order.items.filter(menu_item=item).delete()
                if removed[0] > 0:
                    response_parts.append(f"Removed {item.name} from your order")
                    order_updated = True
                else:
                    logger.warning(f"[Order Webhook] Item {item.name} not found in order to remove")
                    
            elif action == 'modify':
                existing_item = order.items.filter(menu_item=item).first()
                if existing_item:
                    logger.info(f"[Order Webhook] Modifying quantity of {item.name} to {quantity}")
                    existing_item.quantity = quantity
                    existing_item.save()
                    response_parts.append(f"Updated {item.name} quantity to {quantity}")
                    order_updated = True
                else:
                    logger.warning(f"[Order Webhook] Item {item.name} not found in order to modify")
                    response_parts.append(f"I couldn't find {item.name} in your order to modify")
        
        if order_updated:
            # Recalculate order total
            total = sum(item.quantity * item.item_price for item in order.items.all())
            order.total_amount = total
            order.save()
            logger.info(f"[Order Webhook] Updated order total to ${total}")
            
            # Broadcast order update via WebSocket
            logger.info("[Order Webhook] Broadcasting order update via WebSocket")
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "orders",
                {
                    "type": "orders_update",
                    "orders": async_to_sync(OrderConsumer().get_orders)()
                }
            )
        
        response_text = " ".join(response_parts) if response_parts else "Your order is unchanged."
        if order.items.exists():
            response_text += f"\nYour current order total is ${order.total_amount}"
        
        logger.info(f"[Order Webhook] Sending response: {response_text}")
        return JsonResponse({
            "results": [{
                "toolCallId": tool_call_id,
                "result": response_text,
                "name": "order",
                "order_id": order_id
            }]
        })
            
    except Exception as e:
        logger.error(f"[Order Webhook] Error: {str(e)}", exc_info=True)
        return JsonResponse({
            "results": [{
                "toolCallId": tool_call_id if 'tool_call_id' in locals() else "0dca5b3f-59c3-4236-9784-84e560fb26ef",
                "result": "Sorry, I'm having trouble processing your order right now.",
                "name": "order"
            }]
        })

@require_http_methods(["GET"])
def get_orders(request) -> JsonResponse:
    """Get all orders with pagination and filtering"""
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 10))
        status = request.GET.get('status', None)
        
        # Start with all orders
        orders = Order.objects.all()
        
        # Apply filters
        if status:
            orders = orders.filter(status=status)
            
        # Get total count before pagination
        total_count = orders.count()
        
        # Order by most recent first and paginate
        start = (page - 1) * per_page
        end = start + per_page
        orders = orders.order_by('-created_at')[start:end]
        
        orders_list = []
        for order in orders:
            order_items = [{
                'item_name': item.item_name,
                'quantity': item.quantity,
                'price': str(item.item_price),
                'special_instructions': item.special_instructions
            } for item in order.items.all()]
            
            orders_list.append({
                'id': order.id,
                'status': order.status,
                'customer_name': order.customer_name,
                'created_at': order.created_at.isoformat(),
                'total_amount': str(order.total_amount),
                'special_instructions': order.special_instructions,
                'items': order_items
            })
        
        return JsonResponse({
            'status': 'success',
            'orders': orders_list,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_items': total_count,
                'total_pages': (total_count + per_page - 1) // per_page
            }
        })
    
    except Exception as e:
        logger.error(f"Get orders error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@require_http_methods(["GET"])
def get_order(request, order_id: int) -> JsonResponse:
    """Get a specific order by ID"""
    try:
        order = Order.objects.get(id=order_id)
        
        order_items = [{
            'item_name': item.item_name,
            'quantity': item.quantity,
            'price': str(item.item_price),
            'special_instructions': item.special_instructions
        } for item in order.items.all()]
        
        return JsonResponse({
            'status': 'success',
            'order': {
                'id': order.id,
                'status': order.status,
                'customer_name': order.customer_name,
                'created_at': order.created_at.isoformat(),
                'total_amount': str(order.total_amount),
                'special_instructions': order.special_instructions,
                'items': order_items
            }
        })
    except Order.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': f'Order with id {order_id} not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Get order error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["DELETE"])
def clear_orders(request) -> JsonResponse:
    """Clear all orders from the database"""
    try:
        # Delete all orders (this will cascade delete order items)
        count = Order.objects.count()
        Order.objects.all().delete()
        
        # Broadcast empty orders list via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "orders",
            {
                "type": "orders_update",
                "orders": []
            }
        )
        
        return JsonResponse({
            'status': 'success',
            'message': f'Successfully cleared {count} orders',
            'cleared_count': count
        })
    
    except Exception as e:
        logger.error(f"Clear orders error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_order(request, order_id: int) -> JsonResponse:
    """Delete a specific order by ID"""
    try:
        order = Order.objects.get(id=order_id)
        order.delete()
        
        # Broadcast updated orders list via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "orders",
            {
                "type": "orders_update",
                "orders": async_to_sync(OrderConsumer().get_orders)()
            }
        )
        
        return JsonResponse({
            'status': 'success',
            'message': f'Successfully deleted order #{order_id}',
            'deleted_id': order_id
        })
    except Order.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': f'Order with id {order_id} not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Delete order error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)