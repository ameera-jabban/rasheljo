from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Promotion


class PromotionDetailView(generics.RetrieveAPIView):
    queryset = Promotion.objects.filter(is_active=True)
    serializer_class = None
    lookup_field = "slug"

    def get_serializer_class(self):
        from .serializers import PromotionSerializer
        return PromotionSerializer
