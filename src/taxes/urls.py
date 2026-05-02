from django.urls import path
from . import views

urlpatterns = [
    path('',              views.tax_dashboard, name='tax_dashboard'),
    path('profile/save/', views.save_profile,  name='tax_save_profile'),
]
