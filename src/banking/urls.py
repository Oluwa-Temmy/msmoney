from django.urls import path
from . import views

urlpatterns = [
    path('',                    views.account_list,    name='account_list'),
    path('add/',                views.add_account,     name='add_account_bank'),
    path('<int:pk>/',           views.account_detail,  name='account_detail'),
    path('<int:pk>/delete/',    views.delete_account,  name='delete_account'),
    path('<int:pk>/import/',    views.import_statement, name='import_statement'),
    path('<int:pk>/confirm/',   views.import_confirm,  name='import_confirm'),
]
