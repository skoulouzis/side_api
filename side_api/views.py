import json

from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http.response import JsonResponse, HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, render_to_response

from django.template import RequestContext

from django.core.urlresolvers import reverse

from side_api.forms import RegistrationForm


def index(request):
    return render(request, 'index.html', {request: request})


@csrf_exempt
def register(request):
    """
    API endpoint to register a new user.
    """
    #get the request's context.
    context = RequestContext(request)

    # A boolean value for telling the template whether the registration was successful.
    # Set to False initially. Code changes value to True when registration succeeds.
    registered = False

    # If it's a HTTP POST, we're interested in processing form data.
    if request.method == 'POST':
        if 'application/json' in request.META.get('HTTP_ACCEPT'):
            try:
                payload = json.loads(request.body)
            except ValueError:
                return JsonResponse({"error": "Unable to parse request body"}, status=400)

            registration_form = RegistrationForm(payload)
        else:
            registration_form = RegistrationForm(data=request.POST)

        if registration_form.is_valid():
            user = User.objects.create_user(registration_form.cleaned_data["username"],
                                            registration_form.cleaned_data["email"],
                                            registration_form.cleaned_data["password"])
            user.save()

            # Update our variable to tell the template registration was successful.
            registered = True

            return JsonResponse({"success": "User registered."}, status=201)
        else:
            return HttpResponse(registration_form.errors.as_json(), status=400, content_type="application/json")
    # Not a HTTP POST, so we render our form using a RegistrationForm instance.
    # This form will be blank, ready for user input.
    else:
        registration_form = RegistrationForm()

        # Render the template depending on the context.
        return render_to_response('register.html', {'registration_form': registration_form, 'registered': registered},
            context)


def user_login(request):
    # get the request's context.
    context = RequestContext(request)

    # If the request is a HTTP POST, try to pull out the relevant information.
    if request.method == 'POST':
        # Gather the username and password provided by the user.
        # This information is obtained from the login form.
        username = request.POST['username']
        password = request.POST['password']

        # Use Django's machinery to attempt to see if the username/password
        # combination is valid - a User object is returned if it is.
        user = authenticate(username=username, password=password)

        # If we have a User object, the details are correct.
        # If None (Python's way of representing the absence of a value), no user
        # with matching credentials was found.
        if user:
            # Is the account active? It could have been disabled.
            if user.is_active:
                # If the account is valid and active, we can log the user in.
                # We'll send the user back to the homepage.
                login(request, user)
                return HttpResponseRedirect(reverse('index'))
            else:
                # An inactive account was used - no logging in!
                return HttpResponse("Your SIDE_API account is disabled.")
        else:
            # Bad login details were provided. So we can't log the user in.
            print "Invalid login details: {0}, {1}".format(username, password)
            return HttpResponse("Invalid login details supplied.")

    # The request is not a HTTP POST, so display the login form.
    # This scenario would most likely be a HTTP GET.
    else:
        # No context variables to pass to the template system, hence the
        # blank dictionary object...
        return render_to_response('login.html', {}, context)


# Use the login_required() decorator to ensure only those logged in can access the view.
@login_required
def user_logout(request):
    # Since we know the user is logged in, we can now just log them out.
    logout(request)

    # Take the user back to the homepage.
    return HttpResponseRedirect(reverse('index'))