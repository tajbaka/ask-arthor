from django.db import models
from typing import Optional
import numpy as np
from numpy.typing import NDArray
from django.utils import timezone

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

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    customer_name = models.CharField(max_length=200, blank=True)
    special_instructions = models.TextField(blank=True)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)
    item_name = models.CharField(max_length=200)  # Store name in case menu item is deleted
    item_price = models.DecimalField(max_digits=6, decimal_places=2)  # Price at time of order
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Order #{self.id} - {self.quantity}x {self.item_name} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.item_name and self.menu_item:
            self.item_name = self.menu_item.name
        if not self.item_price and self.menu_item:
            self.item_price = self.menu_item.price
        self.total_amount = self.item_price * self.quantity
        super().save(*args, **kwargs) 