# management/commands/import_fuel_stops.py
import csv
import re
import time
from django.core.management.base import BaseCommand
from geopy.geocoders import Nominatim
from route.models import FuelStop  # Adjust import path

class Command(BaseCommand):
    help = "Pre-geocodes and seeds fuel stops from the CSV file."

    def handle(self, *args, **options):
        # Using a distinct user agent prevents getting flagged as a generic scraper
        geolocator = Nominatim(user_agent="fuel_route_seeder_unique_app_xyz", timeout=10)
        csv_path = 'fuel-prices-for-be-assessment.csv'
        
        # In-memory cache to store coordinates for cities we already found
        # Format: {("Guymon", "OK"): (latitude, longitude)}
        city_cache = {}
        
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                opis_id = int(row['OPIS Truckstop ID'])
                
                # Avoid duplicate work if already imported (safe to restart!)
                if FuelStop.objects.filter(opis_id=opis_id).exists():
                    continue

                raw_address = row['Address'].strip()
                city = row['City'].strip()
                state = row['State'].strip()
                price = float(row['Retail Price'])
                name = row['Truckstop Name'].strip()

                # Clean address: Convert "I-44, EXIT 283 & US-69" -> "I-44 & US-69"
                cleaned_addr = re.sub(r',\s*EXIT\s+[\w-]+', '', raw_address, flags=re.IGNORECASE)
                cleaned_addr = re.sub(r'EXIT\s+[\w-]+\s*&\s*', '', cleaned_addr, flags=re.IGNORECASE)
                
                cache_key = (city, state)
                lat, lon = None, None

                # OPTIMIZATION: Check if we have already geocoded this city center
                if cache_key in city_cache:
                    lat, lon = city_cache[cache_key]
                else:
                    # Query 1: Try the intersection first
                    query = f"{cleaned_addr}, {city}, {state}, USA"
                    location = None
                    try:
                        location = geolocator.geocode(query)
                        time.sleep(1.0) # Respect rate limits during network call
                    except Exception:
                        pass

                    # Query 2: Fall back to City Center if intersection fails
                    if not location:
                        try:
                            fallback_query = f"{city}, {state}, USA"
                            location = geolocator.geocode(fallback_query)
                            time.sleep(1.0) # Respect rate limits during network call
                        except Exception:
                            continue

                    if location:
                        lat, lon = location.latitude, location.longitude
                        # Save to cache so the next truckstop in this city gets coordinates instantly
                        city_cache[cache_key] = (lat, lon)

                if lat and lon:
                    FuelStop.objects.create(
                        opis_id=opis_id,
                        name=name,
                        address=raw_address,
                        city=city,
                        state=state,
                        retail_price=price,
                        latitude=lat,
                        longitude=lon
                    )
                    self.stdout.write(self.style.SUCCESS(f"Imported {name} in {city}, {state}"))