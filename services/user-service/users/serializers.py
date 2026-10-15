from rest_framework import serializers

# Add service serializers here.

from django.db import transaction
from rest_framework import serializers
from .models import User, StudentProfile, ClientProfile


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=["STUDENT", "CLIENT"])

    name = serializers.CharField(required=False, max_length=255)
    phone = serializers.CharField(required=False, allow_blank=True)
    college = serializers.CharField(required=False, allow_blank=True)
    skills = serializers.CharField(required=False, allow_blank=True)
    portfolio_url = serializers.URLField(required=False, allow_blank=True)

    company_name = serializers.CharField(required=False, allow_blank=True)
    contact_person = serializers.CharField(required=False, max_length=255)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return value

    def validate(self, data):
        if data["role"] == "STUDENT" and not data.get("name", "").strip():
            raise serializers.ValidationError({
                "name": "Name is required for students."
            })

        if data["role"] == "CLIENT" and not data.get(
            "contact_person", ""
        ).strip():
            raise serializers.ValidationError({
                "contact_person": "Contact person is required for clients."
            })

        return data

    @transaction.atomic
    def create(self, validated_data):
        role = validated_data["role"]

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            role=role,
        )

        if role == "STUDENT":
            StudentProfile.objects.create(
                user=user,
                name=validated_data["name"],
                phone=validated_data.get("phone", ""),
                college=validated_data.get("college", ""),
                skills=validated_data.get("skills", ""),
                portfolio_url=validated_data.get("portfolio_url", ""),
            )
        else:
            ClientProfile.objects.create(
                user=user,
                company_name=validated_data.get("company_name", ""),
                contact_person=validated_data["contact_person"],
                phone=validated_data.get("phone", ""),
            )

        return user

class UserUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)

    def validate_email(self, value):
        value = value.lower()

        if User.objects.filter(email=value).exclude(
            pk=self.instance.pk
        ).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )

        return value

    def update(self, instance, validated_data):
        if "email" in validated_data:
            instance.email = validated_data["email"]

        instance.save()
        return instance
