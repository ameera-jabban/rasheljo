from rest_framework import generics, permissions
from rest_framework.response import Response

from .models import Review
from .serializers import ReviewCreateSerializer, ReviewSerializer


class ReviewListCreateView(generics.ListCreateAPIView):
    """GET /api/v1/reviews/?product= — matches the API spec exactly."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        return ReviewCreateSerializer if self.request.method == "POST" else ReviewSerializer

    def get_queryset(self):
        qs = Review.objects.filter(is_approved=True).select_related("user")
        product_id = self.request.query_params.get("product")
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs

    def create(self, request, *args, **kwargs):
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        review = write_serializer.save()
        # Respond with the read shape (includes is_verified_purchase, user_name)
        # rather than echoing back the write-only input fields.
        read_data = ReviewSerializer(review, context=self.get_serializer_context()).data
        return Response(read_data, status=201)
