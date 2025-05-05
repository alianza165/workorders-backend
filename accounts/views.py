from rest_framework import viewsets, permissions
from django.contrib.auth.models import User
from .models import Profile, Department
from .serializers import UserSerializer, ProfileSerializer, DepartmentSerializer, UserCreateSerializer
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.response import Response

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


class CustomAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data,
                                         context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        
        # Get the user's profile
        profile = user.profile
        print(user.username)
        
        return Response({
            'token': token.key,
            'user_id': user.pk,
            'email': user.email,
            'username': user.username,
            'profile': {
                'is_manager': profile.is_manager,
                'is_production': profile.is_production,
                'is_utilities': profile.is_utilities,
                'is_purchase': profile.is_purchase,
                'department': profile.department.department,
                'mobile_number': profile.mobile_number,
                'image': profile.image.url if profile.image else None
            }
        })