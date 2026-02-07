from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required



def index(request):

    return redirect("login")


def login_view(request):

    return render(request, "core/login.html")


def logout_view(request):

    return redirect("login")


@login_required
def home(request):

    return render(request, "core/home.html")