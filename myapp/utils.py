from openai import OpenAI
import os
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from .models import MenuItem
import numpy as np

def get_client():
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise ImproperlyConfigured("OpenAI API key is not set")
    return OpenAI(api_key=api_key)

client = get_client()

def get_embedding(text):
    """Get OpenAI embedding for text"""
    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return np.array(response.data[0].embedding)
    except Exception as e:
        print(f"Error getting embedding: {str(e)}")
        raise ImproperlyConfigured(f"OpenAI API error: {str(e)}")

def find_similar_items(query, n=5):
    """Find n most similar menu items"""
    query_embedding = get_embedding(query)
    
    # Get all menu items
    items = MenuItem.objects.all()
    
    # Calculate similarities
    similarities = []
    for item in items:
        if item.embedding:
            similarity = np.dot(query_embedding, item.get_embedding())
            similarities.append((similarity, item))
    
    # Sort by similarity
    similarities.sort(reverse=True)
    return [item for _, item in similarities[:n]] 