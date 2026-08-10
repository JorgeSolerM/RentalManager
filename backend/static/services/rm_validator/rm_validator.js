class RMValidator {

    constructor() {

        this.rules = [];

    }

    addRule(field, validator, message) {

        this.rules.push({

            field,
            validator,
            message,

        });

    }

    validate() {

        let valid = true;

        let firstInvalidField = null;

        for (const rule of this.rules) {

            const isValid = rule.validator(rule.field.value);

            if (!isValid) {

                RMNotification.error(rule.message);

                if (!firstInvalidField) {

                    firstInvalidField = rule.field;

                }

                valid = false;

            }

        }

        if (firstInvalidField) {

            firstInvalidField.focus();

        }

        return valid;

    }

}
