from django.urls import path
from . import views

urlpatterns = [
    path('', views.store_list, name='store_list'),
    path('add/', views.add_store, name='add_store'),
    path('confirm-group/', views.confirm_group, name='confirm_group'),
    path('<int:store_id>/', views.store_detail, name='store_detail'),
    path('<int:store_id>/import/', views.import_amazon_csv, name='import_amazon_csv'),
    path('<int:store_id>/bulk/', views.bulk_transactions, name='bulk_transactions'),
    path('<int:store_id>/delete/', views.delete_store, name='delete_store'),
    path('<int:store_id>/group/', views.group_store, name='group_store'),
    path('<int:store_id>/ungroup/', views.ungroup_store, name='ungroup_store'),
    path('group/<int:group_id>/rename/', views.rename_group, name='rename_group'),
]
