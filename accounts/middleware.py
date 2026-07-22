from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone
from django.contrib import messages



class UserActivityMiddleware:
    """
    Combines Online Status and Session Timeout into one efficient pass.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now_dt = timezone.now()
            now_ts = now_dt.timestamp()
            user = request.user
            last_activity = request.session.get('last_activity')

            # 1. CHECK FOR TIMEOUT (30 Minutes)
            if last_activity:
                elapsed = now_ts - last_activity
                if elapsed > 1800:
                    user.is_online = False
                    user.save(update_fields=['is_online'])
                    logout(request)
                    messages.info(request, "Logged out due to inactivity.")
                    # Redirect to login to break any potential dashboard loops
                    return redirect('accounts:login')

            # 2. UPDATE ONLINE STATUS (Only if needed to save DB hits)
            # We only update 'is_online' if it's currently False
            if not user.is_online:
                user.is_online = True
                user.save(update_fields=['is_online'])

            # 3. UPDATE LAST LOGIN HEARTBEAT (Only every 5 minutes)
            # This prevents saving to the database on every single click
            last_login_ts = user.last_login.timestamp() if user.last_login else 0
            if now_ts - last_login_ts > 300:  # 5 minutes
                user.last_login = now_dt
                user.save(update_fields=['last_login'])

            # 4. UPDATE SESSION TIMESTAMP
            request.session['last_activity'] = now_ts

        return self.get_response(request)