class RMSwitch {

    static init() {

        const switches = document.querySelectorAll(".rm-switch-input");

        switches.forEach((element) => {

            element.addEventListener("change", (event) => {

                element.dispatchEvent(

                    new CustomEvent("rm-switch-change", {

                        bubbles: true,

                        detail: {

                            checked: event.target.checked

                        }

                    })

                );

            });

        });

    }

}

document.addEventListener(

    "DOMContentLoaded",

    () => RMSwitch.init()

);
