from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import FuelStop
from .utils import (
    get_route, downsample_route, haversine, 
    assign_mile_markers, select_optimal_stops, calculate_fuel_cost, generate_route_map_html
)

class RouteView(APIView):
    def post(self, request):
        start = request.data.get('start')
        end = request.data.get('end')

        if not start or not end:
            return Response({'error': 'Start and end required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            route = get_route(start, end)
            geometry = route['geometry'] 

            lats = [pt[1] for pt in geometry]
            lons = [pt[0] for pt in geometry]

            PADDING = 0.5 
            min_lat, max_lat = min(lats) - PADDING, max(lats) + PADDING
            min_lon, max_lon = min(lons) - PADDING, max(lons) + PADDING

            candidate_stops = FuelStop.objects.filter(
                latitude__gte=min_lat, latitude__lte=max_lat,
                longitude__gte=min_lon, longitude__lte=max_lon
            ).values('name', 'city', 'state', 'retail_price', 'latitude', 'longitude')
            
            sampled_route = downsample_route(geometry)
            nearby_stops = []

            for stop in candidate_stops:
                for lon, lat in sampled_route:
                    if haversine(stop['latitude'], stop['longitude'], lat, lon) <= 30:

                        stop['price'] = stop['retail_price'] 
                        nearby_stops.append(stop)
                        break

            marked_stops = assign_mile_markers(nearby_stops, geometry)
            optimal_stops = select_optimal_stops(marked_stops, route['distance_miles'])
            total_cost = calculate_fuel_cost(optimal_stops, route['distance_miles'])

            return Response({
                'start': start,
                'end': end,
                'total_distance_miles': round(route['distance_miles'], 1),
                'fuel_stops': optimal_stops,
                'total_fuel_cost_usd': total_cost,
                'geometry': geometry
            })

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
def route_map_preview(request):

    start = request.GET.get('start', 'Midland, TX')
    end = request.GET.get('end', 'Chicago, IL')
    
    try:
        route_data = get_route(start, end)
        geometry = route_data['geometry']
        total_distance = route_data['distance_miles']
        
        lons = [pt[0] for pt in geometry]
        lats = [pt[1] for pt in geometry]
        
        min_lat, max_lat = min(lats) - 0.5, max(lats) + 0.5
        min_lon, max_lon = min(lons) - 0.5, max(lons) + 0.5
        
        db_stops = FuelStop.objects.filter(
            latitude__gte=min_lat, latitude__lte=max_lat,
            longitude__gte=min_lon, longitude__lte=max_lon
        ).values('id', 'name', 'city', 'state', 'retail_price', 'latitude', 'longitude')
        
        candidate_stops = []
        for s in db_stops:
            s['price'] = float(s['retail_price'])
            candidate_stops.append(s)
            
        if not candidate_stops:
            return HttpResponse("No fuel stops found along this corridor corridor.", status=404)
            
        stops_with_miles = assign_mile_markers(candidate_stops, geometry)
        optimal_stops = select_optimal_stops(stops_with_miles, total_distance)
        
        html_content = generate_route_map_html(geometry, optimal_stops)
        
        return HttpResponse(html_content, content_type='text/html')
        
    except Exception as e:
        return HttpResponse(f"Error generating preview: {str(e)}", status=500)