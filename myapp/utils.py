from openai import OpenAI
import os
import numpy as np
from django.conf import settings
from .models import MenuItem

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def get_embedding(text):
    """Get OpenAI embedding for text"""
    response = client.embeddings.create(
        model="text-embedding-ada-002",
        input=text
    )
    return np.array(response.data[0].embedding)

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