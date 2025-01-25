from openai import OpenAI
import os
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from .models import MenuItem
import numpy as np
import logging

logger = logging.getLogger(__name__)

def get_client():
    """Get OpenAI client with error handling"""
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        logger.error(f"OpenAI API key not found. OPENAI_API_KEY: {api_key}")
        raise ImproperlyConfigured("OpenAI API key is not set in environment variables")
    logger.info("Successfully initialized OpenAI client")
    return OpenAI(api_key=api_key)

try:
    client = get_client()
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {str(e)}")
    raise

def get_embedding(text):
    """Get OpenAI embedding for text"""
    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return np.array(response.data[0].embedding)
    except Exception as e:
        logger.error(f"Error getting embedding: {str(e)}")
        raise ImproperlyConfigured(f"OpenAI API error: {str(e)}")

def find_similar_items(query, n=5):
    """Find n most similar menu items"""
    try:
        query_embedding = get_embedding(query)
        
        items = MenuItem.objects.all()
        if not items:
            logger.warning("No menu items found in database")
            return []
        
        similarities = []
        for item in items:
            if item.embedding:
                similarity = np.dot(query_embedding, item.get_embedding())
                similarities.append((similarity, item))
        
        if not similarities:
            logger.warning("No items with embeddings found")
            return []
            
        similarities.sort(reverse=True)
        return [item for _, item in similarities[:n]]
    except Exception as e:
        logger.error(f"Error in find_similar_items: {str(e)}")
        raise 