# Generated by Django 5.1.5 on 2025-01-26 05:24

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('confirmed', 'Confirmed'), ('preparing', 'Preparing'), ('ready', 'Ready'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('customer_name', models.CharField(blank=True, max_length=200)),
                ('special_instructions', models.TextField(blank=True)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
            ],
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('item_name', models.CharField(max_length=200)),
                ('item_price', models.DecimalField(decimal_places=2, max_digits=6)),
                ('special_instructions', models.TextField(blank=True)),
                ('menu_item', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='myapp.menuitem')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='myapp.order')),
            ],
        ),
    ]
