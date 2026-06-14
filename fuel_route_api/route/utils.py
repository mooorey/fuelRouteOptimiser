import os
import math
import requests
from django.conf import settings

MILES_PER_GALLON = 10
MAX_RANGE_MILES = 500
METERS_TO_MILES = 0.000621371
ROUTE_BUFFER_MILES = 30  
ROUTE_SAMPLE_SPACING_MILES = 5


def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_route(start, end):
    geo_url = f"https://api.openrouteservice.org/geocode/search?api_key={settings.ORS_API_KEY}&text="
    
    start_res = requests.get(geo_url + start, timeout=10).json()
    end_res = requests.get(geo_url + end, timeout=10).json()
    
    if not start_res.get('features') or not end_res.get('features'):
        raise ValueError("Could not geocode start or end location coordinates")
        
    start_coords = start_res['features'][0]['geometry']['coordinates']
    end_coords = end_res['features'][0]['geometry']['coordinates']

    url = "https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson"
    headers = {
        "Authorization": settings.ORS_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "coordinates": [start_coords, end_coords]
    }

    response = requests.post(url, json=body, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    feature = data['features'][0]
    geometry = feature['geometry']['coordinates']
    summary = feature['properties']['summary']

    return {
        'geometry': geometry,
        'distance_miles': summary['distance'] * METERS_TO_MILES,
    }

def downsample_route(geometry, spacing_miles=ROUTE_SAMPLE_SPACING_MILES):
    if not geometry:
        return []

    sampled = [geometry[0]]
    last_lon, last_lat = geometry[0]

    for lon, lat in geometry[1:]:
        if haversine(last_lat, last_lon, lat, lon) >= spacing_miles:
            sampled.append((lon, lat))
            last_lon, last_lat = lon, lat

    if sampled[-1] != tuple(geometry[-1]):
        sampled.append(tuple(geometry[-1]))

    return sampled

def assign_mile_markers(stops, geometry):
    sampled_route = downsample_route(geometry)

    cumulative = [0.0]
    for i in range(1, len(sampled_route)):
        lon1, lat1 = sampled_route[i - 1]
        lon2, lat2 = sampled_route[i]
        cumulative.append(cumulative[-1] + haversine(lat1, lon1, lat2, lon2))

    valid_stops = []

    for stop in stops:
        min_dist = float('inf')
        closest_index = 0

        for i, (lon, lat) in enumerate(sampled_route):
            d = haversine(stop['latitude'], stop['longitude'], lat, lon)
            if d < min_dist:
                min_dist = d
                closest_index = i

        if min_dist <= ROUTE_BUFFER_MILES:
            stop['mile_marker'] = round(cumulative[closest_index], 1)
            valid_stops.append(stop)

    return sorted(valid_stops, key=lambda x: x['mile_marker'])

def select_optimal_stops(stops, total_distance_miles):
    selected = []
    current_mile = 0
    safety_counter = 0
    max_iterations = int(total_distance_miles / 50) + 10

    while current_mile + MAX_RANGE_MILES < total_distance_miles:
        safety_counter += 1
        if safety_counter > max_iterations:
            break

        window_start = max(0, current_mile + 50)  
        window_end = current_mile + MAX_RANGE_MILES

        candidates = [
            s for s in stops
            if window_start <= s['mile_marker'] <= window_end
        ]

        if not candidates:
            candidates = [
                s for s in stops
                if current_mile < s['mile_marker'] <= window_end
            ]

        if not candidates:
            current_mile = window_end
            continue

        cheapest = min(candidates, key=lambda x: (x['price'], -x['mile_marker']))
        selected.append(cheapest)
        current_mile = cheapest['mile_marker']

    return selected

def calculate_fuel_cost(selected_stops, total_distance_miles):
    if not selected_stops:
        return 0.0

    total_cost = 0.0
    prev_mile = 0

    for stop in selected_stops:
        segment_miles = stop['mile_marker'] - prev_mile
        gallons = segment_miles / MILES_PER_GALLON
        total_cost += gallons * stop['price']
        prev_mile = stop['mile_marker']

    last_segment = total_distance_miles - prev_mile
    last_price = selected_stops[-1]['price']
    total_cost += (last_segment / MILES_PER_GALLON) * last_price

    return round(total_cost, 2)

def generate_route_map_html(route_geometry, fuel_stops):
    leaflet_polyline = [[pt[1], pt[0]] for pt in route_geometry]
    
    markers_js = ""
    for stop in fuel_stops:
        lat = stop['latitude']
        lon = stop['longitude']
        name = stop['name'].replace('"', '\\"')  
        city = stop['city']
        state = stop['state']
        price = stop['price']
        mile = stop['mile_marker']
        
        markers_js += f"""
        L.marker([{lat}, {lon}]).addTo(map)
            .bindPopup(`
                <div style="font-family: Arial, sans-serif;">
                    <strong style="color: #2c3e50;">{name}</strong><br>
                    <b>Location:</b> {city}, {state}<br>
                    <b>Mile Marker:</b> {mile} mi<br>
                    <b style="color: #27ae60;">Fuel Price: ${price:.3f}</b>
                </div>
            `);
        """
        
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Route Fuel Optimizer Map</title>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            html, body, #map {{ height: 100%; width: 100%; margin: 0; padding: 0; }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            // Initialize map
            var map = L.map('map');
            
            // Load beautiful, free OpenStreetMap tiles
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{s}}.png', {{
                attribution: '&copy; OpenStreetMap contributors'
            }}).addTo(map);
            
            // Draw the route line
            var polylinePoints = {leaflet_polyline};
            var polyline = L.polyline(polylinePoints, {{color: '#3498db', weight: 5, opacity: 0.8}}).addTo(map);
            
            // Inject fuel stop pins
            {markers_js}
            
            // Automatically zoom and center the map around the entire route corridor
            map.fitBounds(polyline.getBounds(), {{ padding: [30, 30] }});
        </script>
    </body>
    </html>
    """
    return html_content