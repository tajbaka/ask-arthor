from openai import OpenAI
import os
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from .models import MenuItem
import numpy as np

if not settings.OPENAI_API_KEY:
    raise ImproperlyConfigured("OpenAI API key is not set")

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def get_embedding(text):
    """Get OpenAI embedding for text"""
    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return np.array(response.data[0].embedding)
    except Exception as e:
        print(f"Error getting embedding: {e}")
        raise

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