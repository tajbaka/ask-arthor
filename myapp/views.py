from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import MenuItem, Order
from .utils import get_embedding, find_similar_items
from typing import Dict, List, Any, Optional
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model
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

@csrf_exempt
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
def vapi_menu_webhook(request):
    """Handle VAPI webhook requests - Returns all menu items"""
    try:
        received = json.loads(request.body)
        
        # Find the menu tool call
        tool_calls = received.get('message', {}).get('toolCalls', [])
        menu_tool_call = next(
            (call for call in tool_calls if call.get('function', {}).get('name') == 'menu'),
            None
        )
        tool_call_id = menu_tool_call['id'] if menu_tool_call else "0dca5b3f-59c3-4236-9784-84e560fb26ef"
        
        try:
            # Get all menu items
            menu_items = MenuItem.objects.all()
            
            if menu_items:
                # Format menu items into sections
                menu_text = "Here's our current menu:\n\n"
                
                # Group by categories if you have them, or just list all items
                menu_text += "\n".join(
                    f"• {item.name}"
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

def parse_tool_call_arguments(tool_call, tool_name):
    """Parse and validate tool call arguments"""
    function_args = tool_call.get('function', {}).get('arguments', {})
    try:
        # Handle both string and dict formats
        if isinstance(function_args, str):
            parsed_args = json.loads(function_args)
        else:
            parsed_args = function_args
            
        # Get the Order object
        order_data = parsed_args.get('Order', {})
        # Extract name and quantity
        query = order_data.get('name', '').strip()
        quantity = order_data.get('quantity', 1)
        
        logger.info(f"Parsed {tool_name} details - Item: '{query}', Quantity: {quantity}")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse arguments JSON: {e}")
        query = ''
        quantity = 1
        
    return query, quantity

def get_tool_call(received_data, tool_name):
    """Extract specific tool call from received data"""
    # Check in toolCalls array first
    tool_calls = received_data.get('message', {}).get('toolCalls', [])
    tool_call = next(
        (call for call in tool_calls if call.get('function', {}).get('name') == tool_name),
        None
    )
    
    # If not found, check in single toolCall object
    if not tool_call:
        tool_call = received_data.get('toolCall')
        if tool_call and tool_call.get('function', {}).get('name') != tool_name:
            tool_call = None
            
    return tool_call

def broadcast_order_update():
    """Broadcast order updates via WebSocket"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "orders",
        {
            "type": "orders_update",
            "orders": async_to_sync(OrderConsumer().get_orders)()
        }
    )

def create_error_response(tool_call_id, message):
    """Create error response JSON"""
    return JsonResponse({
        "results": [{
            "toolCallId": tool_call_id,
            "result": message,
            "name": "order"
        }]
    })

@csrf_exempt
@require_http_methods(["POST"])
def vapi_order_webhook(request):
    """Handle VAPI order webhook requests"""
    try:
        received = json.loads(request.body)
        
        order_tool_call = get_tool_call(received, 'addorder')
        if not order_tool_call:
            return create_error_response(
                "0dca5b3f-59c3-4236-9784-84e560fb26ef",
                "What would you like to order from our menu?"
            )
            
        tool_call_id = order_tool_call['id']
        query, quantity = parse_tool_call_arguments(order_tool_call, 'order')
        
        if not query:
            return create_error_response(
                tool_call_id,
                "What would you like to order from our menu?"
            )
            
        similar_items = find_similar_items(query)
        if not similar_items:
            return create_error_response(
                tool_call_id,
                f"I couldn't find '{query}' on our menu. Would you like to see our menu?"
            )
            
        menu_item = similar_items[0]
        
        # Create order with direct item information
        order = Order.objects.create(
            quantity=quantity,
            item_name=menu_item.name,
            item_price=menu_item.price,
            customer_name=order_tool_call.get('function', {}).get('arguments', {}).get('customer_name', '').strip(),
            special_instructions=order_tool_call.get('function', {}).get('arguments', {}).get('special_instructions', '').strip()
        )
        
        logger.info(f"Created order #{order.id} for {quantity}x {menu_item.name}")
        
        broadcast_order_update()
        
        response_text = (f"I've created order #{order.id} for {quantity}x {menu_item.name}. "
                        f"Total amount: ${order.total_amount}")
        
        return JsonResponse({
            "results": [{
                "toolCallId": tool_call_id,
                "result": response_text,
                "name": "order",
                "order_id": str(order.id),
                "quantity": quantity
            }]
        })
            
    except Exception as e:
        logger.error(f"Order webhook error: {str(e)}", exc_info=True)
        return create_error_response(
            tool_call_id if 'tool_call_id' in locals() else "0dca5b3f-59c3-4236-9784-84e560fb26ef",
            "Sorry, I'm having trouble processing your order right now."
        )

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
            orders_list.append({
                'id': order.id,
                'status': order.status,
                'customer_name': order.customer_name,
                'created_at': order.created_at.isoformat(),
                'total_amount': str(order.total_amount),
                'special_instructions': order.special_instructions,
                'item_name': order.item_name,
                'quantity': order.quantity,
                'item_price': str(order.item_price)
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
        
        return JsonResponse({
            'status': 'success',
            'order': {
                'id': order.id,
                'status': order.status,
                'customer_name': order.customer_name,
                'created_at': order.created_at.isoformat(),
                'total_amount': str(order.total_amount),
                'special_instructions': order.special_instructions,
                'item_name': order.item_name,
                'quantity': order.quantity,
                'item_price': str(order.item_price)
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

@csrf_exempt
@require_http_methods(["POST"])
def vapi_remove_order_webhook(request):
    """Handle VAPI remove order webhook requests"""
    try:
        received = json.loads(request.body)
        logger.info(f"Received remove order webhook request: {json.dumps(received, indent=2)}")
        
        remove_tool_call = get_tool_call(received, 'removeorder')
        if not remove_tool_call:
            logger.warning("No removeorder tool call found in request")
            return create_error_response(
                "0dca5b3f-59c3-4236-9784-84e560fb26ef",
                "Which order would you like to remove?"
            )
            
        tool_call_id = remove_tool_call['id']
        logger.info(f"Processing remove order tool call: {tool_call_id}")
        
        # Get the order ID from arguments
        function_args = remove_tool_call.get('function', {}).get('arguments', {})
        if isinstance(function_args, str):
            function_args = json.loads(function_args)
        
        order_data = function_args.get('Order', {})
        order_id = order_data.get('id')
        logger.info(f"Attempting to remove order #{order_id}")
        
        if not order_id:
            logger.warning("No order ID provided in request")
            return create_error_response(
                tool_call_id,
                "Which order would you like to remove?"
            )
        
        try:
            order = Order.objects.get(id=order_id)
            item_name = order.item_name
            logger.info(f"Found order #{order_id}: {item_name} x{order.quantity}")
            order.delete()
            logger.info(f"Successfully deleted order #{order_id}")
            
            broadcast_order_update()
            
            return JsonResponse({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": f"I've removed order #{order_id} ({item_name}).",
                    "name": "order",
                    "order_id": str(order_id)
                }]
            })
            
        except Order.DoesNotExist:
            logger.warning(f"Order #{order_id} not found")
            return create_error_response(
                tool_call_id,
                f"I couldn't find order #{order_id}. Would you like to see your current orders?"
            )
            
    except Exception as e:
        logger.error(f"Remove order webhook error: {str(e)}", exc_info=True)
        return create_error_response(
            tool_call_id if 'tool_call_id' in locals() else "0dca5b3f-59c3-4236-9784-84e560fb26ef",
            "Sorry, I'm having trouble removing the order right now."
        )