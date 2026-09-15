"""Authentication and customer-account endpoints."""

from __future__ import annotations

import contextlib
from typing import Any

from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.services import record_audit
from apps.common import spreadsheets
from apps.common.exceptions import DomainError, NotFoundError
from apps.common.permissions import HasTenantPermission
from apps.common.serializers import MessageResponseSerializer
from apps.common.views import TenantScopedMixin

from .models import Address, Role, User
from .serializers import (
    AddressSerializer,
    ChangePasswordSerializer,
    CustomerSummarySerializer,
    EmailVerificationSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PermissionSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    RoleSerializer,
    StaffUserSerializer,
    UserPermissionsSerializer,
    UserPermissionsWriteSerializer,
    UserRolesWriteSerializer,
    UserSerializer,
)
from .services import (
    anonymize_user,
    change_password,
    create_address,
    export_personal_data,
    register_customer,
    replace_direct_permissions,
    replace_roles,
    request_password_reset,
    resend_verification,
    reset_password,
    revoke_all_refresh_tokens,
    set_default_address,
    verify_email,
)


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP.

    ``X-Forwarded-For`` is only trustworthy behind our own proxy; we take the
    left-most entry and accept that a direct-to-API client could spoof it. It is
    used for rate-limit context and audit hints, never for authorization.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# =============================================================================
# Authentication
# =============================================================================
class RegisterView(TenantScopedMixin, APIView):
    permission_classes = [AllowAny]
    throttle_scope = "register"

    @extend_schema(
        request=RegisterSerializer,
        responses={201: UserSerializer},
        operation_id="auth_register",
    )
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, _raw_token = register_customer(
            tenant=self.tenant, ip=_client_ip(request), **serializer.validated_data
        )
        record_audit(
            action="account.registered",
            tenant=self.tenant,
            actor=user,
            resource=user,
            request=request,
        )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TenantScopedMixin, TokenObtainPairView):
    """Exchange credentials for an access/refresh pair."""

    permission_classes = [AllowAny]
    throttle_scope = "login"
    tenant_required = False


class RefreshView(TokenRefreshView):
    """Rotate a refresh token. The previous one is blacklisted immediately."""

    permission_classes = [AllowAny]
    throttle_scope = "login"


class LogoutView(APIView):
    """Revoke the supplied refresh token."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None, responses={205: MessageResponseSerializer}, operation_id="auth_logout"
    )
    def post(self, request: Request) -> Response:
        raw_token = request.data.get("refresh")
        if raw_token:
            # An already-expired or unknown token means the session is gone;
            # reporting an error would only confuse the client.
            with contextlib.suppress(TokenError):
                RefreshToken(raw_token).blacklist()
        else:
            revoke_all_refresh_tokens(request.user)

        record_audit(
            action="account.logout",
            tenant=getattr(request, "tenant", None),
            actor=request.user,
            resource=request.user,
            request=request,
        )
        return Response({"detail": _("Signed out.")}, status=status.HTTP_205_RESET_CONTENT)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "email_verification"

    @extend_schema(
        request=EmailVerificationSerializer,
        responses={200: MessageResponseSerializer},
        operation_id="auth_verify_email",
    )
    def post(self, request: Request) -> Response:
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = verify_email(
            raw_token=serializer.validated_data["token"],
            user_id=serializer.validated_data.get("uid"),
        )
        record_audit(
            action="account.email_verified",
            tenant=user.tenant,
            actor=user,
            resource=user,
            request=request,
        )
        return Response({"detail": _("Email address confirmed.")})


class ResendVerificationView(TenantScopedMixin, APIView):
    permission_classes = [AllowAny]
    throttle_scope = "email_verification"

    @extend_schema(
        request=ResendVerificationSerializer,
        responses={202: MessageResponseSerializer},
        operation_id="auth_resend_verification",
    )
    def post(self, request: Request) -> Response:
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resend_verification(
            tenant=self.tenant,
            email=serializer.validated_data["email"],
            ip=_client_ip(request),
        )
        # Same response whether or not the address exists.
        return Response(
            {"detail": _("If the address exists, a confirmation email is on its way.")},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetRequestView(TenantScopedMixin, APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={202: MessageResponseSerializer},
        operation_id="auth_password_reset",
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(
            tenant=self.tenant,
            email=serializer.validated_data["email"],
            ip=_client_ip(request),
        )
        return Response(
            {"detail": _("If the address exists, a reset email is on its way.")},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={200: MessageResponseSerializer},
        operation_id="auth_password_reset_confirm",
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = reset_password(
            raw_token=serializer.validated_data["token"],
            new_password=serializer.validated_data["password"],
            user_id=serializer.validated_data.get("uid"),
        )
        record_audit(
            action="account.password_reset",
            tenant=user.tenant,
            actor=user,
            resource=user,
            request=request,
        )
        return Response({"detail": _("Password updated. Please sign in again.")})


# =============================================================================
# Customer self-service
# =============================================================================
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer, operation_id="customers_me_retrieve")
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        request=UserSerializer, responses=UserSerializer, operation_id="customers_me_update"
    )
    def patch(self, request: Request) -> Response:
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        request=None,
        responses={200: MessageResponseSerializer},
        operation_id="customers_me_delete",
        description=(
            "Anonymises the account. Financial records are preserved without any "
            "link to an identifiable person (LGPD)."
        ),
    )
    def delete(self, request: Request) -> Response:
        anonymize_user(request.user, reason="self_service")
        record_audit(
            action="account.anonymized",
            tenant=getattr(request, "tenant", None),
            actor=request.user,
            resource=request.user,
            request=request,
        )
        return Response({"detail": _("Account deleted.")})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={200: MessageResponseSerializer},
        operation_id="customers_me_change_password",
    )
    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_password(
            user=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
        )
        record_audit(
            action="account.password_changed",
            tenant=getattr(request, "tenant", None),
            actor=request.user,
            resource=request.user,
            request=request,
        )
        return Response({"detail": _("Password updated. Please sign in again.")})


class DataExportView(APIView):
    """LGPD data-portability request."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict}, operation_id="customers_me_data_export")
    def get(self, request: Request) -> Response:
        record_audit(
            action="account.data_exported",
            tenant=getattr(request, "tenant", None),
            actor=request.user,
            resource=request.user,
            request=request,
        )
        return Response(export_personal_data(request.user))


class AddressViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """A customer's own delivery addresses."""

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    queryset = Address.objects.all()

    def get_queryset(self) -> Any:
        # Same guard as the other user-scoped viewsets: the schema generator
        # builds the view without a request, and filtering on an AnonymousUser
        # raises. It emitted no warning here only because `queryset` is declared,
        # so the model could still be derived — but the POST operation appeared
        # or vanished from run to run, which made the generated schema unstable.
        if getattr(self, "swagger_fake_view", False):
            return Address.objects.none()

        return super().get_queryset().filter(customer=self.request.user)

    def perform_create(self, serializer: Any) -> None:
        serializer.instance = create_address(
            customer=self.request.user, tenant=self.tenant, **serializer.validated_data
        )

    @extend_schema(request=None, responses=AddressSerializer, operation_id="addresses_set_default")
    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request: Request, pk: str | None = None) -> Response:
        address = self.get_object()
        set_default_address(customer=request.user, address=address)
        return Response(AddressSerializer(address).data)


# =============================================================================
# Merchant administration
# =============================================================================
class CustomerAdminViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Customer list for merchant staff."""

    serializer_class = CustomerSummarySerializer
    permission_classes = [HasTenantPermission]
    required_permissions = ["customers.view"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering_fields = ["created_at", "email"]
    ordering = ["-created_at"]

    @extend_schema(
        parameters=[OpenApiParameter("fmt", str, description="csv or xlsx")],
        responses={200: OpenApiTypes.BINARY},
        operation_id="admin_customers_export",
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request: Request) -> Any:
        """The customer list, filtered the same way the screen is."""
        from apps.common.exports import CUSTOMER_COLUMNS, customer_rows

        return spreadsheets.download(
            columns=CUSTOMER_COLUMNS,
            rows=customer_rows(self.filter_queryset(self.get_queryset())),
            stem="clientes",
            fmt=request.query_params.get("fmt", spreadsheets.XLSX),
        )

    def get_queryset(self) -> Any:
        from .constants import UserType

        # Search is handled by `search_fields` above, now that SearchFilter is
        # actually installed. This used to filter by hand because it wasn't —
        # customers was the one admin table whose search box worked.
        return User.objects.filter(tenant_id=self.tenant_id, user_type=UserType.CUSTOMER).order_by(
            "-created_at"
        )

    @extend_schema(responses={200: dict}, operation_id="admin_customer_stats")
    @action(detail=True, methods=["get"])
    def stats(self, request: Request, pk: str | None = None) -> Response:
        """Spend summary for one customer."""
        from apps.orders.selectors import customer_order_stats

        customer = self.get_object()
        return Response(customer_order_stats(tenant_id=self.tenant_id, customer=customer))


class StaffUserViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Merchant staff accounts and their roles."""

    serializer_class = StaffUserSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {
        "list": ["users.view"],
        "retrieve": ["users.view"],
        "default": ["users.manage"],
    }
    search_fields = ["email", "first_name", "last_name"]

    def get_queryset(self) -> Any:
        from .constants import UserType

        return (
            User.objects.filter(tenant_id=self.tenant_id)
            .exclude(user_type=UserType.CUSTOMER)
            # Serialised on every row, so joined rather than fetched per user.
            .select_related("avatar")
            .prefetch_related("roles")
            .order_by("email")
        )

    def perform_destroy(self, instance: User) -> None:
        """Deactivate instead of deleting: audit rows must keep their actor."""
        if instance.pk == self.request.user.pk:
            raise DomainError(
                _("You cannot deactivate your own account."), code="SELF_DEACTIVATION"
            )
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        revoke_all_refresh_tokens(instance)
        record_audit(
            action="user.deactivated",
            tenant=self.tenant,
            actor=self.request.user,
            resource=instance,
            request=self.request,
        )


class RoleViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Roles a merchant can tailor. System roles cannot be deleted."""

    serializer_class = RoleSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"list": ["users.view"], "default": ["users.manage"]}

    def get_queryset(self) -> Any:
        return Role.objects.filter(tenant_id=self.tenant_id).prefetch_related("permissions")

    def perform_destroy(self, instance: Role) -> None:
        if instance.is_system:
            raise DomainError(_("System roles cannot be removed."), code="SYSTEM_ROLE_PROTECTED")
        instance.delete()

    def get_object(self) -> Role:
        obj = super().get_object()
        if obj is None:
            raise NotFoundError()
        return obj


# =============================================================================
# Permission administration
# =============================================================================
class PermissionListView(TenantScopedMixin, APIView):
    """The permission catalogue, for the transfer lists in the user editor.

    Returned unpaginated: it is a fixed, small vocabulary, and the UI needs all
    of it at once to compute the "available" side of a transfer list.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = ["users.view"]

    @extend_schema(responses=PermissionSerializer(many=True), operation_id="admin_permissions_list")
    def get(self, request: Request) -> Response:
        from .models import Permission

        permissions = Permission.objects.all().order_by("code")
        return Response(PermissionSerializer(permissions, many=True).data)


class UserPermissionsView(TenantScopedMixin, APIView):
    """Read and replace one account's **direct** permission grants.

    Reading reports the two sources separately, because the UI must show which
    grants it can revoke here and which arrive through a role.
    """

    permission_classes = [HasTenantPermission]
    required_permissions = {"get": ["users.view"], "default": ["users.manage"]}

    def get_user(self, request: Request, pk: str) -> User:
        user = User.objects.filter(pk=pk, tenant_id=self.tenant_id).first()
        if user is None:
            raise NotFoundError()
        return user

    @extend_schema(
        responses=UserPermissionsSerializer, operation_id="admin_user_permissions_retrieve"
    )
    def get(self, request: Request, pk: str) -> Response:
        user = self.get_user(request, pk)
        return Response(
            {
                "direct": sorted(user.direct_permission_codes()),
                "from_roles": sorted(user.role_permission_codes()),
                "effective": sorted(user.permission_codes()),
            }
        )

    @extend_schema(
        request=UserPermissionsWriteSerializer,
        responses=UserPermissionsSerializer,
        operation_id="admin_user_permissions_replace",
    )
    def put(self, request: Request, pk: str) -> Response:
        serializer = UserPermissionsWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.get_user(request, pk)
        before = sorted(user.direct_permission_codes())
        after = replace_direct_permissions(
            user=user, codes=serializer.validated_data["codes"], granted_by=request.user
        )

        record_audit(
            action="user.permissions_changed",
            tenant=self.tenant,
            actor=request.user,
            resource=user,
            old_values={"direct": ", ".join(before)},
            new_values={"direct": ", ".join(after)},
            request=request,
        )

        return Response(
            {
                "direct": after,
                "from_roles": sorted(user.role_permission_codes()),
                "effective": sorted(user.permission_codes()),
            }
        )


class UserRolesView(TenantScopedMixin, APIView):
    """Replace the roles assigned to one account."""

    permission_classes = [HasTenantPermission]
    required_permissions = ["users.manage"]

    @extend_schema(
        request=UserRolesWriteSerializer,
        responses=StaffUserSerializer,
        operation_id="admin_user_roles_replace",
    )
    def put(self, request: Request, pk: str) -> Response:
        serializer = UserRolesWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(pk=pk, tenant_id=self.tenant_id).first()
        if user is None:
            raise NotFoundError()

        before = sorted(role.slug for role in user.roles.all())
        after = replace_roles(
            user=user, slugs=serializer.validated_data["roles"], granted_by=request.user
        )

        record_audit(
            action="user.permissions_changed",
            tenant=self.tenant,
            actor=request.user,
            resource=user,
            old_values={"roles": ", ".join(before)},
            new_values={"roles": ", ".join(after)},
            request=request,
        )

        return Response(StaffUserSerializer(user).data)
