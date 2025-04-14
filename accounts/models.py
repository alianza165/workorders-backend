from django.db import models
from django.contrib.auth.models import User
from PIL import Image
 

class Department(models.Model):
    department = models.CharField(max_length=50)

    def __str__(self):
        return self.department


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    is_manager = models.BooleanField(default=False)
    is_production = models.BooleanField(default=False)
    is_utilities = models.BooleanField(default=False)
    is_purchase = models.BooleanField(default=False)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    mobile_number = models.CharField(max_length=30, blank=True)
    image = models.ImageField(default='default.jpg', upload_to='profile_pics')

    def __str__(self):
        return f'{self.user.username} Profile'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        img = Image.open(self.image.path)

        if img.height > 300 or img.width > 300:
            output_size = (300, 300)
            img.thumbnail(output_size)
            img.save(self.image.path)
