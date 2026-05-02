from django.urls import path
from . import views

urlpatterns = [
    path('',                                       views.vendors_all,           name='vendors_all'),
    path('<int:store_id>/',                        views.vendor_list,           name='vendor_list'),
    path('<int:store_id>/add/',                    views.add_vendor,            name='add_vendor'),
    path('<int:store_id>/<int:vendor_id>/delete/', views.delete_vendor,         name='delete_vendor'),
    path('<int:store_id>/<int:vendor_id>/manage/', views.vendor_manage,         name='vendor_manage'),
    path('<int:store_id>/import/',                 views.import_vendor_invoices, name='import_vendor_invoices'),
]
