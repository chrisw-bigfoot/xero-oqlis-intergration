from django.db import models



class Tenant(models.Model):
    name = models.CharField(max_length=150)
    logo = models.ImageField(upload_to="tenant_logo", null=True, blank=True)

    def __str__(self):
        return self.name