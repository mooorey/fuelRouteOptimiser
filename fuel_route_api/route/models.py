from django.db import models

# Create your models here.
class FuelStop(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=10)
    retail_price = models.FloatField()
    latitude = models.FloatField(db_index=True) 
    longitude = models.FloatField(db_index=True)

    def __str__(self):
        return f"{self.name} - {self.city}, {self.state} (${self.retail_price})"