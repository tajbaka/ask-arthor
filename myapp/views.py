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
    """Handle VAPI webhook requests"""
    try:
        # Log incoming request
        logger.info("Received webhook request")
        logger.info(f"Request body: {request.body.decode()}")
        
        data = json.loads(request.body)
        message = data.get('message', {}).get('text', '')
        conversation_id = data.get('conversation_id', '')
        
        logger.info(f"Processing message: {message}")
        
        # Check if we have any menu items
        item_count = MenuItem.objects.count()
        logger.info(f"Total menu items in database: {item_count}")
        
        try:
            # Search menu items using local endpoint
            response = requests.get(
                "http://127.0.0.1:8000/menu/search/",  # Use local URL for testing
                params={"q": message},
                timeout=5
            )
            response.raise_for_status()
            menu_data = response.json()
            logger.info(f"Search response: {menu_data}")
            
            if menu_data.get("found"):
                items = menu_data["items"]
                menu_text = "\n".join(item["formatted"] for item in items)
                response_text = f"I found these menu items:\n\n{menu_text}\n\nWould you like to know more about any of these items?"
            else:
                response_text = "I couldn't find any menu items matching your request. Can I help you find something else?"

        except requests.RequestException as e:
            logger.error(f"Search request failed: {str(e)}")
            response_text = "I'm having trouble searching our menu right now. Please try again in a moment."

        logger.info(f"Sending response: {response_text}")
        return JsonResponse({
            "messages": [{
                "text": response_text,
                "conversation_id": conversation_id
            }]
        })
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return JsonResponse({
            "messages": [{
                "text": "Sorry, I'm having trouble with the menu right now."
            }]
        })