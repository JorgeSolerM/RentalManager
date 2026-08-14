const RMPageNotification = {

    show(
        successMessages = {},
        errorMessages = {},
    ) {

        const params = new URLSearchParams(
            window.location.search
        );

        const success = params.get(
            "success"
        );

        const error = params.get(
            "error"
        );

        if (
            success &&
            successMessages[success]
        ) {

            RMNotification.success(
                successMessages[success]
            );

        }

        if (
            error &&
            errorMessages[error]
        ) {

            RMNotification.error(
                errorMessages[error]
            );

        }

        if (
            !success &&
            !error
        ) {

            return;

        }

        params.delete(
            "success"
        );

        params.delete(
            "error"
        );

        const query = params.toString();

        const url = query
            ? `${window.location.pathname}?${query}`
            : window.location.pathname;

        history.replaceState(
            {},
            "",
            url
        );

    }

};
