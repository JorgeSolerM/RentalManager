class FlashMessage:

    @staticmethod
    def success(request, message: str):

        request.session["flash"] = {
            "type": "success",
            "message": message,
        }

    @staticmethod
    def info(request, message: str):

        request.session["flash"] = {
            "type": "info",
            "message": message,
        }

    @staticmethod
    def warning(request, message: str):

        request.session["flash"] = {
            "type": "warning",
            "message": message,
        }

    @staticmethod
    def error(request, message: str):

        request.session["flash"] = {
            "type": "error",
            "message": message,
        }

    @staticmethod
    def pop(request):

        flash = request.session.get("flash")

        if flash:

            del request.session["flash"]

        return flash
