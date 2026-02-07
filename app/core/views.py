from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from user.forms import LoginForm


def index(request):
    return redirect("login")


def login_view(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect("home")
    
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.first_name or user.email}!")
            return redirect("home")
        else:
            messages.error(request, "Invalid email or password. Please try again.")
    else:
        form = LoginForm()
    
    context = {"form": form}
    return render(request, "core/login.html", context)


def logout_view(request):
    """Handle user logout"""
    if request.user.is_authenticated:
        user_name = request.user.first_name or request.user.email
        logout(request)
        messages.success(request, f"See you soon, {user_name}!")
    return redirect("login")


@login_required
def home(request):
    return render(request, "core/home.html")