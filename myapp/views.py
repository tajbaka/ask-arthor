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

@csrf_exempt
@require_http_methods(["POST"])
def vapi_order_webhook(request):
    """Handle VAPI order webhook requests"""
    try:
        received = json.loads(request.body)
        logger.info(f"Received order: {json.dumps(received, indent=2)}")
        
        # Extract the last user message to get the order details
        messages = received.get('messagesOpenAIFormatted', [])
        last_user_message = next((msg['content'] for msg in reversed(messages) 
                                if msg.get('role') == 'user'), '')
        
        tool_calls = received.get('message', {}).get('toolCalls', [])
        tool_call_id = tool_calls[0]['id'] if tool_calls else "0dca5b3f-59c3-4236-9784-84e560fb26ef"
        
        # Try to get query from arguments or last user message
        function_args = tool_calls[0].get('function', {}).get('arguments', {}) if tool_calls else {}
        query = function_args.get('query', '') or last_user_message
        
        logger.info(f"Looking for menu item matching: '{query}'")
        
        if query:
            # Create a new order
            order = Order.objects.create(
                customer_name=function_args.get('customer_name', '')
            )
            
            # Try to find matching menu item with fuzzy matching
            menu_items = MenuItem.objects.filter(name__icontains='margherita')  # Handle common spelling
            if not menu_items:
                menu_items = MenuItem.objects.filter(name__icontains='margarita')  # Alternative spelling
                
            logger.info(f"Found {menu_items.count()} matching menu items")
            
            if menu_items:
                item = menu_items[0]
                logger.info(f"Selected menu item: {item.name} (${item.price})")
                
                # Create order item
                order_item = OrderItem.objects.create(
                    order=order,
                    menu_item=item,
                    quantity=function_args.get('quantity', 1),
                    item_name=item.name,
                    item_price=item.price
                )
                
                # Update order total
                order.total_amount = item.price * function_args.get('quantity', 1)
                order.save()
                
                logger.info(f"Created order #{order.id} with item: {order_item.item_name} x{order_item.quantity}")
                
                response_text = (f"I've created order #{order.id} for {item.name}. "
                               f"Total amount: ${order.total_amount}")
            else:
                logger.warning(f"No menu items found matching: '{query}'")
                response_text = f"I couldn't find '{query}' on our menu. Would you like to see our menu?"
        else:
            response_text = ("I don't see any specific order details. "
                           "What would you like to order? You can tell me the name of the item.")
        
        response = {
            "results": [{
                "toolCallId": tool_call_id,
                "result": response_text,
                "name": "order"
            }]
        }
        
        return JsonResponse(response)
            
    except Exception as e:
        logger.error(f"Order webhook error: {str(e)}")
        response = {
            "results": [{
                "toolCallId": "0dca5b3f-59c3-4236-9784-84e560fb26ef",
                "result": "Sorry, I'm having trouble processing your order right now.",
                "name": "order"
            }]
        }
        return JsonResponse(response)

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