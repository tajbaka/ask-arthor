from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import MenuItem
from .utils import get_embedding, find_similar_items
from typing import Dict, List, Any
from django.core.exceptions import ImproperlyConfigured
import logging
import requests

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
        # Log raw request for debugging
        logger.info("=== Webhook Request Details ===")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Body: {request.body.decode()}")
        logger.info("============================")
        
        data = json.loads(request.body)
        tool_call_id = data.get('toolCallId', '')
        
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

            logger.info(f"Found {len(menu_items)} menu items")
            
        except Exception as e:
            logger.error(f"Menu retrieval failed: {str(e)}")
            response_text = "I'm having trouble accessing our menu right now. Please try again in a moment."

        logger.info(f"Sending response: {response_text}")
        return JsonResponse({
            "results": [{
                "toolCallId": tool_call_id,
                "result": response_text
            }]
        })
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        logger.exception("Full traceback:")
        return JsonResponse({
            "results": [{
                "toolCallId": data.get('toolCallId', ''),
                "result": "Sorry, I'm having trouble accessing the menu right now."
            }]
        })