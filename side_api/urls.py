"""side_api URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import include, url
from django.contrib import admin
from rest_framework_nested import routers
from rest_framework.authtoken.views import obtain_auth_token

import views
from api.views import UserViewSet, ApplicationViewSet, ComponentViewSet, ComponentTypeViewSet, InstanceViewSet, ApplicationGraphView, ComponentGraphView, SwitchDocumentViewSet, model_form_upload

router = routers.DefaultRouter(trailing_slash=False)
router.register("users", UserViewSet, base_name="user")
router.register("switchapps", ApplicationViewSet, base_name="switchapps")
router.register("switchcomponents", ComponentViewSet, base_name="switchcomponents")
router.register("switchcomponenttypes", ComponentTypeViewSet, base_name="switchcomponenttypes")
router.register("switchcomponentinstances", InstanceViewSet, base_name="switchcomponentinstances")
router.register("switchdocuments", SwitchDocumentViewSet, base_name="switchdocuments")

urlpatterns = [
    url(r'^admin/', include(admin.site.urls)),
    url(r'^$', views.index, name='index'),
    url(r'^api/', include(router.urls)),
    url(r'^api-auth-token/', obtain_auth_token),
    url(r'^api-register/', views.register, name='register'),
    url(r'^api/switchapps/(?P<pk>[^/.]+)/graph', ApplicationGraphView.as_view()),
    url(r'^api/switchcomponents/(?P<pk>[^/.]+)/graph', ComponentGraphView.as_view()),
    url(r'^login/$', views.user_login, name='login'),
    url(r'^logout/$', views.user_logout, name='logout'),
    url(r'^uploads/form/$', model_form_upload, name='model_form_upload'),
]
