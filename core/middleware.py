class SessionCartMiddleware:
    """
    Ensures that every visitor has a session key so they can 
    add items to their cart without being logged in.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # If the user is not logged in and doesn't have a session yet, create one
        if not request.user.is_authenticated and not request.session.session_key:
            request.session.create()
        
        response = self.get_response(request)
        return response