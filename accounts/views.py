
from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy

from .forms import UserManagementForm
from .models import UserProfile


# ============================================================
# LOGIN
# ============================================================

class EHIRSLoginView(LoginView):
    template_name = "accounts/login.html"

    def get_success_url(self):
        return reverse_lazy("dashboard:home")


# ============================================================
# LOGOUT
# ============================================================

class EHIRSLogoutView(LogoutView):
    next_page = reverse_lazy("accounts:login")


# ============================================================
# PROFILE HELPER
# ============================================================

def get_profile(request):
    """
    Return the logged-in user's active UserProfile.

    Returns None when:
        - user is not authenticated
        - user has no UserProfile
        - UserProfile is inactive
    """

    if not request.user.is_authenticated:
        return None

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return None

    if not profile.active:
        return None

    return profile


# ============================================================
# USER MANAGEMENT PERMISSION
# ============================================================

def require_user_manager(request):
    """
    Allow User Management for:

        Ministry Admin
        Regional Admin
        Sub-city Admin

    Facility users cannot access User Management.
    """

    profile = get_profile(request)

    if profile is None:

        messages.error(
            request,
            "Your account does not have an active user profile.",
        )

        return None

    # --------------------------------------------------------
    # MINISTRY ADMIN
    # --------------------------------------------------------

    if profile.is_ministry_admin():
        return profile

    # --------------------------------------------------------
    # REGIONAL ADMIN
    # --------------------------------------------------------

    if profile.is_region_admin():
        return profile

    # --------------------------------------------------------
    # SUB-CITY ADMIN
    # --------------------------------------------------------

    if profile.is_subcity_admin():
        return profile

    # --------------------------------------------------------
    # FACILITY USER
    # --------------------------------------------------------

    messages.error(
        request,
        "You do not have permission to access User Management.",
    )

    return None


# ============================================================
# USER MANAGEMENT
# ============================================================

@login_required
def user_management(request):
    """
    Display users that the logged-in administrator
    is allowed to manage.
    """

    manager_profile = require_user_manager(request)

    if manager_profile is None:
        return redirect("dashboard:home")

    # ========================================================
    # GET USERS USING MODEL ACCESS CONTROL
    # ========================================================

    users = manager_profile.accessible_user_profiles()

    # ========================================================
    # SEARCH
    # ========================================================

    search = request.GET.get(
        "search",
        "",
    ).strip()

    if search:

        users = users.filter(
            user__username__icontains=search
        ) | users.filter(
            user__first_name__icontains=search
        ) | users.filter(
            user__last_name__icontains=search
        ) | users.filter(
            user__email__icontains=search
        ) | users.filter(
            organization__name__icontains=search
        ) | users.filter(
            facility__name__icontains=search
        )

        users = users.distinct()

    # ========================================================
    # ROLE FILTER
    # ========================================================

    selected_role = request.GET.get(
        "role",
        "",
    ).strip()

    if selected_role:

        users = users.filter(
            role=selected_role
        )

    # ========================================================
    # STATUS FILTER
    # ========================================================

    selected_status = request.GET.get(
        "status",
        "",
    ).strip()

    if selected_status == "active":

        users = users.filter(
            active=True
        )

    elif selected_status == "inactive":

        users = users.filter(
            active=False
        )

    # ========================================================
    # ORDERING
    # ========================================================

    users = users.order_by(
        "user__first_name",
        "user__last_name",
        "user__username",
    )

    # ========================================================
    # CONTEXT
    # ========================================================

    context = {
        "profile": manager_profile,
        "users": users,
        "search": search,
        "selected_role": selected_role,
        "selected_status": selected_status,
        "role_choices": UserProfile.Role.choices,
    }

    return render(
        request,
        "accounts/user_management.html",
        context,
    )


# ============================================================
# CREATE USER
# ============================================================

@login_required
def user_create(request):

    manager_profile = require_user_manager(request)

    if manager_profile is None:
        return redirect("dashboard:home")

    if request.method == "POST":

        form = UserManagementForm(
            request.POST,
            manager_profile=manager_profile,
        )

        if form.is_valid():

            target_profile = form.save()

            messages.success(
                request,
                (
                    f"User '{target_profile.user.username}' "
                    "was created successfully."
                ),
            )

            return redirect(
                "accounts:user_management"
            )

    else:

        form = UserManagementForm(
            manager_profile=manager_profile,
        )

    context = {
        "form": form,
        "profile": manager_profile,
        "page_title": "Create User",
        "submit_text": "Create User",
        "is_edit": False,
    }

    return render(
        request,
        "accounts/user_form.html",
        context,
    )


# ============================================================
# EDIT USER
# ============================================================

@login_required
def user_edit(request, profile_id):

    manager_profile = require_user_manager(request)

    if manager_profile is None:
        return redirect("dashboard:home")

    target_profile = get_object_or_404(
        UserProfile.objects.select_related(
            "user",
            "organization",
            "facility",
        ),
        pk=profile_id,
    )

    # ========================================================
    # PERMISSION CHECK
    # ========================================================

    if not manager_profile.can_manage_user(
        target_profile
    ):

        messages.error(
            request,
            "You do not have permission to edit this user.",
        )

        return redirect(
            "accounts:user_management"
        )

    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        form = UserManagementForm(
            request.POST,
            instance=target_profile,
            manager_profile=manager_profile,
        )

        if form.is_valid():

            updated_profile = form.save()

            messages.success(
                request,
                (
                    f"User '{updated_profile.user.username}' "
                    "was updated successfully."
                ),
            )

            return redirect(
                "accounts:user_management"
            )

    # ========================================================
    # GET
    # ========================================================

    else:

        form = UserManagementForm(
            instance=target_profile,
            manager_profile=manager_profile,
        )

    context = {
        "form": form,
        "profile": manager_profile,
        "target_profile": target_profile,
        "page_title": "Edit User",
        "submit_text": "Save Changes",
        "is_edit": True,
    }

    return render(
        request,
        "accounts/user_form.html",
        context,
    )


# ============================================================
# ACTIVATE / DEACTIVATE USER
# ============================================================

@login_required
def user_toggle_active(request, profile_id):

    manager_profile = require_user_manager(request)

    if manager_profile is None:
        return redirect("dashboard:home")

    # Only POST is allowed.
    if request.method != "POST":

        return redirect(
            "accounts:user_management"
        )

    target_profile = get_object_or_404(
        UserProfile.objects.select_related(
            "user",
            "organization",
            "facility",
        ),
        pk=profile_id,
    )

    # ========================================================
    # PERMISSION CHECK
    # ========================================================

    if not manager_profile.can_manage_user(
        target_profile
    ):

        messages.error(
            request,
            "You do not have permission to change this user's status.",
        )

        return redirect(
            "accounts:user_management"
        )

    # ========================================================
    # PREVENT SELF-DEACTIVATION
    # ========================================================

    if target_profile.user_id == request.user.id:

        messages.error(
            request,
            "You cannot deactivate your own account.",
        )

        return redirect(
            "accounts:user_management"
        )

    # ========================================================
    # TOGGLE STATUS
    # ========================================================

    target_profile.active = not target_profile.active

    target_profile.save(
        update_fields=["active"]
    )

    # Keep Django User synchronized.
    target_profile.user.is_active = target_profile.active

    target_profile.user.save(
        update_fields=["is_active"]
    )

    # ========================================================
    # MESSAGE
    # ========================================================

    if target_profile.active:

        messages.success(
            request,
            (
                f"User '{target_profile.user.username}' "
                "has been activated."
            ),
        )

    else:

        messages.success(
            request,
            (
                f"User '{target_profile.user.username}' "
                "has been deactivated."
            ),
        )

    return redirect(
        "accounts:user_management"
    )


# ============================================================
# RESET PASSWORD
# ============================================================

@login_required
def user_reset_password(request, profile_id):

    manager_profile = require_user_manager(request)

    if manager_profile is None:
        return redirect("dashboard:home")

    # Only POST is allowed.
    if request.method != "POST":

        return redirect(
            "accounts:user_management"
        )

    target_profile = get_object_or_404(
        UserProfile.objects.select_related(
            "user",
            "organization",
            "facility",
        ),
        pk=profile_id,
    )

    # ========================================================
    # PERMISSION CHECK
    # ========================================================

    if not manager_profile.can_manage_user(
        target_profile
    ):

        messages.error(
            request,
            "You do not have permission to reset this user's password.",
        )

        return redirect(
            "accounts:user_management"
        )

    # ========================================================
    # PASSWORD INPUT
    # ========================================================

    new_password = (
        request.POST.get("new_password")
        or request.POST.get("password")
        or ""
    ).strip()

    confirm_password = (
        request.POST.get("confirm_password")
        or request.POST.get("password_confirm")
        or ""
    ).strip()

    # ========================================================
    # VALIDATION
    # ========================================================

    if not new_password:

        messages.error(
            request,
            "Please enter a new password.",
        )

        return redirect(
            "accounts:user_management"
        )

    if len(new_password) < 8:

        messages.error(
            request,
            "The password must contain at least 8 characters.",
        )

        return redirect(
            "accounts:user_management"
        )

    if new_password != confirm_password:

        messages.error(
            request,
            "The passwords do not match.",
        )

        return redirect(
            "accounts:user_management"
        )

    # ========================================================
    # SET PASSWORD
    # ========================================================

    target_profile.user.set_password(
        new_password
    )

    target_profile.user.save()

    # Keep current session alive if resetting own password.
    if target_profile.user_id == request.user.id:

        update_session_auth_hash(
            request,
            target_profile.user,
        )

    messages.success(
        request,
        (
            f"Password for '{target_profile.user.username}' "
            "has been reset successfully."
        ),
    )

    return redirect(
        "accounts:user_management"
    )