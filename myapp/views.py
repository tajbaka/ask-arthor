from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import MenuItem, Order, OrderItem
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

@csrf_exempt
@require_http_methods(["POST"])
def vapi_order_webhook(request):
    """Handle VAPI order webhook requests"""
    try:
        received = json.loads(request.body)
        logger.info(f"Received order: {json.dumps(received, indent=2)}")
        
        messages = received.get('messagesOpenAIFormatted', [])
        tool_calls = received.get('message', {}).get('toolCalls', [])
        
        # Find the addorder tool call
        order_tool_call = next(
            (call for call in tool_calls if call.get('function', {}).get('name') == 'addorder'),
            None
        )
        
        # Validate tool calls
        if not order_tool_call:
            logger.warning("No order tool call found in request")
            return JsonResponse({
                "results": [{
                    "toolCallId": "0dca5b3f-59c3-4236-9784-84e560fb26ef",
                    "result": "What would you like to order from our menu?",
                    "name": "order"
                }]
            })
            
        tool_call_id = order_tool_call['id']
        
        # Get function arguments
        function_args = order_tool_call.get('function', {}).get('arguments', {})
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
            
            logger.info(f"Parsed order details - Item: '{query}', Quantity: {quantity}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse arguments JSON: {e}")
            query = ''
            quantity = 1
        
        # If no query provided or need to find similar items
        if not query:
            logger.warning("No order query provided")
            return JsonResponse({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": "What would you like to order from our menu?",
                    "name": "order"
                }]
            })
            
        # Use similarity search to find matching menu item
        similar_items = find_similar_items(query)
        
        if not similar_items:
            logger.warning(f"No menu items found matching: '{query}'")
            return JsonResponse({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": f"I couldn't find '{query}' on our menu. Would you like to see our menu?",
                    "name": "order"
                }]
            })
            
        # Use the best match
        item = similar_items[0]
        logger.info(f"Found matching menu item: {item.name}")
        
        # Create order with validated data
        order: Order = Order.objects.create(
            customer_name=function_args.get('customer_name', '').strip(),
            special_instructions=function_args.get('special_instructions', '').strip()
        )
        
        # Create order item
        order_item = OrderItem.objects.create(
            order=order,
            menu_item=item,
            quantity=quantity,
            item_name=item.name,
            item_price=item.price
        )
        
        # Update order total
        order.total_amount = item.price * quantity
        order.save()
        
        logger.info(f"Created order #{order.id} with item: {order_item.item_name} x{quantity}")
        
        # Broadcast order update via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "orders",
            {
                "type": "orders_update",
                "orders": async_to_sync(OrderConsumer().get_orders)()
            }
        )
        
        response_text = (f"I've created order #{order.id} for {quantity}x {item.name}. "
                        f"Total amount: ${order.total_amount}")
        
        return JsonResponse({
            "results": [{
                "toolCallId": tool_call_id,
                "result": response_text,
                "name": "order",
                "order_id": str(order.id),
                "menu_item_id": str(item.id),
                "quantity": quantity
            }]
        })
            
    except Exception as e:
        logger.error(f"Order webhook error: {str(e)}", exc_info=True)
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

@csrf_exempt
@require_http_methods(["POST"])
def vapi_remove_order_webhook(request):
    """Handle VAPI remove order webhook requests"""
    try:
        received = json.loads(request.body)
        logger.info(f"Received remove order request: {json.dumps(received, indent=2)}")
        
        messages = received.get('messagesOpenAIFormatted', [])
        tool_calls = received.get('message', {}).get('toolCalls', [])
        
        # Find the removeorder tool call
        remove_tool_call = next(
            (call for call in tool_calls if call.get('function', {}).get('name') == 'removeorder'),
            None
        )
        
        # Validate tool calls
        if not remove_tool_call:
            logger.warning("No remove order tool call found in request")
            return JsonResponse({
                "results": [{
                    "toolCallId": "0dca5b3f-59c3-4236-9784-84e560fb26ef",
                    "result": "Which item would you like to remove from your order?",
                    "name": "order"
                }]
            })
            
        tool_call_id = remove_tool_call['id']
        
        # Get function arguments
        function_args = remove_tool_call.get('function', {}).get('arguments', {})
        if isinstance(function_args, str):
            try:
                function_args = json.loads(function_args)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse function arguments string: {function_args}")
                function_args = {}

        logger.info(f"Function arguments: {json.dumps(function_args, indent=2)}")
            
        # Extract order details - now using "Order" field directly
        query = function_args.get('Order', '').strip()
        quantity = 1  # Default quantity since it's not specified in new format
        
        if query:
            logger.info(f"Found remove request in arguments - Item: '{query}', Quantity: {quantity}")
        
        # # If no query provided, try to infer from conversation
        # if not query and messages:
        #     logger.info("No query provided, inferring from conversation...")
        #     inferred_item, inferred_quantity = infer_order_from_conversation(messages)
        #     if inferred_item:
        #         query = inferred_item
        #         quantity = inferred_quantity
        #         logger.info(f"Inferred removal: {quantity}x {inferred_item}")
        
        # Validate query
        if not query:
            logger.warning("No item specified for removal")
            return JsonResponse({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": "Which item would you like to remove from your order?",
                    "name": "order"
                }]
            })
        
        # Get current order and log its items
        current_order = Order.objects.first()
        if not current_order:
            logger.warning("No current order found")
            return JsonResponse({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": "There are no active orders to remove items from.",
                    "name": "order"
                }]
            })
            
        logger.info("Current order items:")
        for item in current_order.items.all():
            logger.info(f"- {item.item_name} (id: {item.id})")
        
        # Find matching items in the order - make case insensitive
        query = query.lower()  # Convert query to lowercase
        logger.info(f"Looking for items matching: '{query}'")
        
        # Try exact match first
        matching_items = current_order.items.filter(item_name__iexact=query)
        logger.info(f"Found {matching_items.count()} exact matches")
        
        # Try partial match if no exact matches
        if not matching_items:
            matching_items = current_order.items.filter(item_name__icontains=query)
            logger.info(f"Found {matching_items.count()} partial matches")
            
        if not matching_items:
            logger.warning(f"No items found matching: '{query}'")
            return JsonResponse({
                "results": [{
                    "toolCallId": tool_call_id,
                    "result": f"I couldn't find '{query}' in your current order. Would you like to see your order?",
                    "name": "order"
                }]
            })
            
        # Remove the first matching item
        item = matching_items[0]
        item_name = item.item_name
        logger.info(f"Removing item: {item_name} (id: {item.id})")
        
        # Delete the item
        item.delete()
        logger.info("Item deleted from database")
        
        # Verify deletion
        if not OrderItem.objects.filter(id=item.id).exists():
            logger.info("Verified item was deleted")
        else:
            logger.error("Item still exists after deletion!")
        
        # Update order total
        current_order.total_amount = sum(
            item.item_price * item.quantity 
            for item in current_order.items.all()
        )
        current_order.save()
        logger.info(f"Updated order total: ${current_order.total_amount}")
        
        # Broadcast order update via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "orders",
            {
                "type": "orders_update",
                "orders": async_to_sync(OrderConsumer().get_orders)()
            }
        )
        
        response_text = (f"I've removed {item_name} from your order. "
                       f"New total: ${current_order.total_amount}")
        
        return JsonResponse({
            "results": [{
                "toolCallId": tool_call_id,
                "result": response_text,
                "name": "order"
            }]
        })
            
    except Exception as e:
        logger.error(f"Remove order webhook error: {str(e)}", exc_info=True)
        return JsonResponse({
            "results": [{
                "toolCallId": tool_call_id if 'tool_call_id' in locals() else "0dca5b3f-59c3-4236-9784-84e560fb26ef",
                "result": "Sorry, I'm having trouble removing items from your order right now.",
                "name": "order"
            }]
        })