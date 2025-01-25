from django.db import models
from typing import Optional
import numpy as np
from numpy.typing import NDArray

class MenuItem(models.Model):
    name: str = models.CharField(max_length=200)
    description: str = models.TextField(blank=True)
    price: float = models.DecimalField(max_digits=6, decimal_places=2)
    embedding = models.JSONField(null=True)  # Store embedding as JSON

    def __str__(self):
        return f"{self.name} - ${self.price}"

    def set_embedding(self, embedding_array: NDArray) -> None:
        """Store numpy array as list"""
        self.embedding = embedding_array.tolist()

    def get_embedding(self) -> Optional[NDArray]:
        """Get embedding as numpy array"""
        return np.array(self.embedding) if self.embedding else None 