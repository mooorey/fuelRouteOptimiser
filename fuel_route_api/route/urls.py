from django.urls import path
from .views import RouteView, route_map_preview

urlpatterns = [
    path('route/', RouteView.as_view(), name='route'),
    path('route/view-map/', route_map_preview, name='route_map_preview')
]