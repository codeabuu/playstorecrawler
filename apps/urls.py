from django.urls import path

from apps import views


urlpatterns = [
    path("", views.index, name="index"),
    path("api/search", views.api_search, name="api-search"),
    path("api/reviews", views.api_reviews_bulk, name="api-reviews-bulk"),
    path("api/reviews/report.pdf", views.api_report_pdf, name="api-report-pdf"),
    path("api/reviews/<str:app_id>", views.api_reviews, name="api-reviews"),
]
