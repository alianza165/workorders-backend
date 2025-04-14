from rest_framework import viewsets, permissions
from django.contrib.auth.models import User
from .models import Profile, Department
from .serializers import UserSerializer, ProfileSerializer, DepartmentSerializer, UserCreateSerializer

class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

class UserRegistrationViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]  # Allow registration without auth
    
    def get_permissions(self):
        if self.action == 'create':
            return [permission() for permission in [permissions.AllowAny]]
        return [permission() for permission in self.permission_classes]