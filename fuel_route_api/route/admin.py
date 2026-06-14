from django.contrib import admin
from .models import FuelStop
# Register your models here.

@admin.register(FuelStop)
class FuelStopAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'state', 'retail_price', 'latitude', 'longitude')