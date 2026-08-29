from rest_framework import generics

from .models import ShippingMethod
from .serializers import ShippingMethodSerializer


class ShippingMethodListView(generics.ListAPIView):
    queryset = ShippingMethod.objects.filter(is_active=True)
    serializer_class = ShippingMethodSerializer
    pagination_class = None  # small fixed list — no client needs to paginate shipping options
